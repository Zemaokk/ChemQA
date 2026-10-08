# ChemQA：有机电催化文献问答

ChemQA 将本地 PDF 文献解析、检索和兼容 Chat Completions 的生成接口连接起来，输出可回查文献、PDF 物理页及原文片段的回答。它使用预训练模型，没有训练新的基础模型；引用可定位和接口成功均不保证科学结论正确。

截至 2026-10-08，Q06.5-J 已完成运行配置冻结与回退核验，Q10-B 已完成用户指定的助手专家评审。当前保留 MiniLM/JSON 兼容默认；Qwen 混合检索、重排与多样性选择作为显式候选。现已加入 R01 保守回答与发布前保真检查；工程验证通过，科学效果仍待独立验收，见 [修订说明](docs/R01_ANSWER_RELIABILITY.md)。完整状态见 [总计划](docs/REFACTOR_PLAN.md)。

## 从这里开始

| 目的 | 入口 |
| --- | --- |
| 安装、问答、重建和回退 | [运行手册](docs/RUNBOOK.md) |
| 阅读已有比较、核验来源和回放输入 | [评估说明](docs/EVALUATION_GUIDE.md) |
| 了解实现、实测收益及失败边界 | [技术报告](docs/TECHNICAL_REPORT.md) |
| 查看问题—回答—原文的对应示例 | [证据演示](docs/DEMO.md) |
| 查看最终配置与本地资产清单 | [当前 R01 manifest](config/r01_runtime.json)、[历史 J 冻结记录](docs/Q06_5J_FREEZE.md) |

## 安装与离线检查

使用 Python 3.12（`.python-version`）与 uv，在项目根目录运行：

```sh
uv sync --locked
uv run --locked python main.py --help
uv run --locked ruff check .
uv run --locked ruff format --check .
HF_HUB_OFFLINE=1 MPLBACKEND=Agg uv run --locked python -m unittest discover -s tests
```

`pyproject.toml` 声明依赖，`uv.lock` 固定解析结果，`requirements.txt` 为不含开发工具的锁定导出。2026-10-08 本机 Python 3.12.13 / macOS ARM64 的 263 项回归通过（含18项 R01 合成检查）；其他平台没有本轮完整运行验收记录。

安装依赖不等于准备好文献、索引与模型缓存。`data/` 中的文献、片段与索引只在本地保留，不再纳入新的源码提交；Q09 无历史源码快照排除这些文件和模型缓存，须另行提供获准使用的 PDF 与匹配索引。源码包本身不能还原本机冻结实验目录。第一次准备模型需要访问模型托管服务；`HF_HUB_OFFLINE=1` 仅在缓存齐全后使用。详见运行手册。

本机 R01 清单所列资产齐全时可只校验文件，不加载模型、不调用生成 API：

```sh
uv run --locked python main.py --runtime-profile legacy --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank_diverse --check-runtime
```

这些命令检查本地 manifest 绑定的源码、配置、依赖与索引；缺失或变更会报错。搬迁、重建或修改源码后需重新验证并发布新 manifest，不能静默把新产物当原实验。

## 配置与问答

```sh
cp .env.example .env
```

在本地 `.env` 填写自己的密钥。环境变量优先于 `.env`，后者不纳入 Git。已验证的本地第三方生成配置如下；无需把密钥写入代码或命令记录：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://llmapi.paratera.com/v1
DEEPSEEK_MODEL=DeepSeek-V4-Flash
DEEPSEEK_THINKING=disabled
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=4096
```

`DEEPSEEK_*` 是兼容变量名。范例中的仓库通用默认是另一组 endpoint/model，本次真实评估只验证上述 Paratera 配置；其他平台需自行核验兼容性。显式冻结 profile 会固定生成地址、模型、单次尝试及预算等参数，仅保留外部密钥；无 profile 的入口遵循环境配置，默认最多尝试3次。

以下问答会把问题和检索片段发送到所选生成平台，可能计费：

```sh
# 本机冻结的兼容默认
uv run --locked python main.py --runtime-profile legacy \
  --output-dir output/manual-legacy -q "What is organic electrocatalysis?"

# 显式实验候选；须具有 manifest 中列出的本地模型/索引资产
uv run --locked python main.py --runtime-profile hybrid_rerank \
  --output-dir output/manual-candidate -q "What evidence supports this reaction mechanism?"

# 不指定 -q 时为交互问答，输入 exit 退出
uv run --locked python main.py --runtime-profile legacy
```

`hybrid_rerank_diverse` 加入每篇6片段上限与跨度去重，仅作实验对照。`--runtime-profile` 不能与 `--index-dir` 混用。使用自己重建的索引时走运行手册中的环境配置入口。

## 数据和输出

当前本地语料为181个 PDF 文件、180份不同字节身份。MiniLM/JSON 索引含26,025片段；Qwen 候选为6,960片段、1024维，使用 NumPy float32 + SQLite 存储。两种分块不同，不直接以片段数判断质量。

每次问答在 `output/qa/<UTC时间戳-UUID>/` 独立保存 `run.json`、`answer.md` 与 `answer.evidence.json`。后者保留实际提示、证据、完整 `chunk_id`、原文跨度和生成状态；失败/截断改存 `failure.json`，不发布为正常答案。发布前保真检查未通过也保存为失败，保留原始内容与诊断，不自动重试；检查通过不保证科学正确。空证据在本地返回 `no_evidence`，不发送生成请求。输出目录、模型缓存由 Git 忽略；自定义到其他位置时需另行维护忽略规则。

PDF 字节哈希定义文献身份，片段身份绑定文献、局部序号与精确文本。页码为 PDF 物理页，字符区间位于提取文本，不是页面高亮坐标。引用映射统计只回答标记是否可定位，不是 claim support precision。参见 [身份](docs/Q01_IDENTITY.md)、[位置](docs/Q02_LOCATIONS.md)、[生成约定](docs/Q05_PROMPT_CONTRACT.md)。

## 评估结果与限制

Q10-B 冻结40题（34个开发诊断题、6个预留题），在6题上比较5方案×3重复，共90次正常生成。新增14个开发题来自原有文献，没有增加独立论文样本。预留集已经一次性使用，不能据其调参后再次称为独立测试。

助手专家评审下，Direct/BM25/Dense/Hybrid+reranker/+diverse 的冻结要点宏平均分别为15.28%/77.78%/100%/100%/100%。**这是特定要点得分，不是整份回答准确率。** 三个Qwen候选仍有额外公式、工况归属或证据表述错误，R05存在题目接受范围歧义。该评审非独立人工、非盲评；六题不足以认定普遍赢家，也未比较旧默认 MiniLM 的同条件生成质量。详见 [完整评审](docs/Q10B_EXPERT_REVIEW.md)。

当前已知缺陷包括 PDF 公式/电荷符号丢失、不同优化阶段条件混合、过强的证据缺失判断。结构引用映射率100%不能消除这些缺陷。API计时未包含检索、价格未知、第三方模型只有平台别名；不报告端到端加速、费用节省或科学质量保证。

## 其他入口与分享范围

[批量脚本](qa_testing/README_qa_testing.md) 是历史使用/接口检查工具，不替代冻结评估；批量生成会发送真实请求。热力图仅可视化余弦相似度，不能解释为科学支持概率。更多命令见运行手册。

当前开发 Git 历史含用户确认已撤销的旧凭据，未重写历史。Q09 提供无 `.git` 的本地源码快照机制；不要把原开发仓库历史直接当作公开交付。快照仍会包含文档/评估中的文献摘录及本地路径，不等于获得这些材料的再分发许可，也不自带模型与索引。分享流程与扫描边界见 [Q09](docs/Q09_CREDENTIALS.md) 和运行手册；本轮未发布或推送。

仓库跟踪与上传边界见[文件策略](docs/REPOSITORY_POLICY.md)：源码、依赖锁和验证记录保留；文献、模型、索引和运行输出本地备份。停止跟踪不清除已有 Git 历史。
