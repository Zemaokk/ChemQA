# Q08：路径、独立运行与候选索引

日期：2026-10-07

状态：已实现；95 项单元回归通过。两页合成 PDF 的真实解析、编码、校验、候选发布和加载，以及项目外启动验证通过。验证记录见 [Q08_VALIDATION.json](Q08_VALIDATION.json)。生成结果使用模拟 HTTP，未调用真实生成 API，未重建整个文献库。

## 原问题与验收

原单次问答反复写入固定的 `answer_6.md` 和附属文件；批量脚本与热力图也使用固定输出位置。完整重建会备份并替换当前索引和处理数据。相对路径依赖启动目录，难以清楚区分旧结果、失败与候选配置。

本项要求：多次运行及候选索引互不覆盖；配置和路径入口统一；文件写入失败不发布完整结果；重建先校验、再独立发布；显式选择候选并能返回原索引。保持当前模型、提示约定、分块与相似度策略。

## 配置与启动

路径统一通过 `config.settings.resolve_path` 解析。绝对路径直接使用，`~` 展开，相对路径以项目根目录为基准。`.env` 始终从项目根目录读取；显式终端环境变量优先于 `.env`，CLI 路径选项优先于两者。相对 `HF_HOME` 在 Hugging Face 初始化前同样转成项目绝对路径。

| 变量 | 默认路径 | 用途 |
|---|---|---|
| `CHEMQA_RAW_PAPERS_DIR` | `data/raw_papers` | PDF 来源 |
| `CHEMQA_INDEX_DIR` | `data/vector_db` | 显式选择索引目录 |
| `CHEMQA_PROCESSED_DIR` | `data/processed` | 旧布局的处理数据；显式设置索引且未设置本变量时随索引目录 |
| `CHEMQA_OUTPUT_DIR` | `output` | 运行和默认候选目录的根目录 |
| `CHEMQA_MODEL_DIR` | `models` | 本地模型目录 |

主问答、两种批量脚本和热力图支持 `--index-dir`、`--output-dir`；构建器支持 `--pdf-dir`、`--destination`、`--output-dir`。`--index-dir` 同时选择候选目录内的处理数据。程序内使用 `configure_paths` 时须先配置，再初始化模型和检索器。

从项目外启动可使用项目 `.venv/bin/python` 加绝对脚本路径；使用 `-m` 时通过 `PYTHONPATH` 指定项目根目录。`uv run` 示例默认从项目根目录运行。路径语义与当前工作目录无关，但 Python 仍需要找到项目模块。

## 结果布局与发布

默认使用 UTC 时间戳加 UUID 的独立目录：

```text
output/
  qa/<run-id>/
    run.json
    answer.md                     # success / no_evidence
    answer.evidence.json
    citation_analysis.txt         # 启用且完成引用分析时
    failure.json                  # failed / truncated；没有本次正常答案
  indexes/<run-id>/
    run.json
    vector_index.json
    processed_chunks.json
  qa_batches/<session-id>/
  direct_api_batches/<session-id>/
  heatmaps/<run-id>/
    run.json
    similarity_heatmap.png
```

`run.json` 保存类型、状态、时间和允许记录的配置，包括模型/revision、检索数量、重叠长度、API 模型参数和 `uv.lock` SHA-256。单次问答和 RAG 批量会话另记实际加载索引的 SHA-256。密钥及 API endpoint 不复制到此配置快照；原始提示、生成状态与证据继续保存在单次问答附属记录中。

单次问答、候选索引、热力图先写同文件系统的 `.staging-*` 目录，必要步骤完成后再重命名发布。正常异常会清理暂存目录，不留下被标记为完整的新目录；启用引用分析时，报告写入异常也会阻止发布。指定目标已存在时明确失败。批量会话创建时记为 `running`，单文件原子替换，汇总 JSON 和文本均写完后才记为 `complete`；这个状态表示会话汇总写完，具体成功、失败、未测数量须查看 `counts`。批量运行中断后保持 `running`，不能视为完整汇总。

每次新建批量测试器即新建会话，不自动读取上一次目录；直连脚本对同一测试器内的定向重跑仍更新其会话汇总，跨会话不覆盖。旧固定输出文件全部保留，系统不再自动选择 `answer_6.md`；分析已有答案需明确传入文件路径。默认生成物继续由 `/output/` 忽略；自定义到其他目录时需自行添加对应忽略规则。

原子发布针对正常进程执行和异常，不承诺多进程同时写同一个显式目标或断电持久性。强制终止可能留下 `.staging-*` 目录，这些目录不会被自动选作候选。UUID 默认路径用于隔离普通并行运行。

## 重建、加载和回退

在项目根目录运行：

```bash
# 全库候选：校验通过后发布到 output/indexes/<run-id>，打印具体路径
uv run --locked python -m src.pipeline.vector_index_builder

# 指定来源和全新的目标；目标存在时拒绝覆盖
uv run --locked python -m src.pipeline.vector_index_builder \
  --pdf-dir data/raw_papers --destination output/indexes/my-candidate

# 显式加载候选，所有新回答仍独立保存
uv run --locked python main.py --index-dir output/indexes/my-candidate \
  --output-dir output/candidate-answers -q "electrochemical oxidation of alcohols"

# 显式返回原索引；即使 .env 选择了候选，也由 CLI 覆盖
uv run --locked python main.py --index-dir data/vector_db -q "electrochemical oxidation of alcohols"
```

重建按排序后的 PDF 路径处理，沿用 Q03 验证文本覆盖、页内原文、片段/向量对齐、模型 manifest、输入 token 上限和实际 tokenizer 输入。通过后把处理数据和索引作为同一个候选目录发布；不会自动激活或替换 `data/` 文件。构建器低层写入辅助方法须显式传入暂存目录，标准重建入口为 `run_pipeline`。

候选 `run.json` 标记 `ready` 并保存两个数据文件的 SHA-256。加载候选时检查 schema、类型、状态及两份哈希，再检查已有的片段身份和 embedding 兼容条件；被篡改或未就绪时拒绝。缺失索引明确报错，避免静默变成空证据。无 `run.json` 的现有旧索引仍可读取，读取不会隐式改写。已发布候选禁止 `VectorStore.add_documents` 和索引保存接口修改，需要重新构建另一候选。旧索引的增量保存采用原子替换并刷新已加载指纹。

## 验证与边界

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q08 \
  --report /tmp/chemqa-q08-validation.json
```

- 原 81 项加 14 项 Q08 回归：覆盖原子写入失败、暂存清理、重复目标拒绝、索引/处理数据篡改检测、候选不可变、配置优先级、启动目录变化、重复问答及批量会话隔离、配置快照不含密钥、引用报告写入失败阻止整次发布。
- 合成两页 PDF 实际产生一个跨页片段、384 维向量；Q03 校验通过，两页原文区间全部核验，无输入截断。
- 候选真实检索后，两次模拟完整响应和一次模拟 HTTP 401 各写独立目录；失败无答案，前两份答案未改变。
- 从项目外运行真实问答入口，成功加载指定候选，空密钥明确返回配置失败及退出码 1，`request_sent=false`。构建、两类批量和热力图的项目外 `--help` 入口通过。
- Q05/Q06/Q07 真实检索加模拟 HTTP 验证再次通过；历史验收 JSON 未覆盖。
- 原索引 SHA-256 为 `2d5452736fc396b28340fae3447c7bee8e0e46791bdc45e680535f9fb21b23c3`；原处理数据为 `1e59fa1b851cf432d1c77d4423823cd3ed69c7739a3ff60fb5f0bb20e1e669c5`；本次前后均相同。

此项建立结果与索引的独立保存和选择机制。配置快照用于追溯，不替代完整代码、PDF、权重与环境归档；Q06.5-A 的原始归档和验收记录仍保留。没有进行全库重建、真实 LLM 行为验证或检索质量比较，也不据此宣称准确率提升。下一项为 Q09。
