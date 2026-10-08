# ChemQA 运行手册

日期：2026-10-08。本手册描述当前实现；历史阶段记录用于追溯，冲突时以运行 manifest、代码及本手册的当前状态为准。所有命令从项目根目录运行。

## 1. 环境与本地资产

使用 Python 3.12，运行 `uv sync --locked`。缓存已有时可用 `uv sync --locked --offline`；离线安装失败应补齐依赖缓存，不应修改锁文件绕过。`requirements.txt`由以下命令导出，不独立维护：

```sh
uv export --locked --no-dev --format requirements-txt --no-hashes --output-file requirements.txt
```

开发默认读取 `data/raw_papers`、`data/processed/processed_chunks.json` 和 `data/vector_db/vector_index.json`。本机已有资料继续保留，但 Git 不再跟踪这些目录；新源码检出需独立准备。无历史源码快照不含 `data/`、`models/`、`output/`。只有源码时先提供自己的合法PDF并构建独立索引；缺少原始PDF不能核验历史证据跨度。

模型缓存由 Hugging Face 管理；`.env.example`使用 `HF_HOME=models/huggingface`。安装依赖不会自动下载模型。首次模型加载需网络及固定revision资产，之后可设置 `HF_HUB_OFFLINE=1`。当前 R01 profile 还绑定索引/源码校验值，不是可随意搬迁的通用配置模板；所需路径与哈希见 [当前 manifest](../config/r01_runtime.json)。

| 运行方式 | 资产要求与行为 |
| --- | --- |
| `legacy` 冻结 profile | MiniLM固定revision、原26,025片段JSON和processed文件、manifest绑定源码；恢复冻结第三方生成参数 |
| `hybrid_rerank` | 固定Qwen embedding/reranker权重、F二进制索引、G词法索引和G/H运行记录；Q10-B公共选择策略 |
| `hybrid_rerank_diverse` | 同上，另用I的每篇6片段/跨度0.5策略 |
| 无profile | 环境驱动入口；支持自己的兼容索引，不保证等同原冻结实验 |

## 2. 配置、验证与生成

复制 `.env.example` 到 `.env`，填写本地密钥和成对的 Base URL/model。当前已验证的生成平台为 `https://llmapi.paratera.com/v1`，模型为 `DeepSeek-V4-Flash`，非思考、temperature 0.3、max_tokens 4096。客户端自行附加 `/chat/completions`，Base URL不要写成完整completion地址。缺少密钥时，本地检索可运行，非空证据生成明确失败。

环境变量覆盖 `.env`；相对数据、模型及输出路径按项目根解析。普通CLI `--index-dir`会同时选择索引与处理目录，`--output-dir`覆盖输出根。显式profile另固定检索/生成参数，保留外部密钥和可选输出目录，拒绝同时传 `--index-dir`；无profile入口默认最大尝试次数3，冻结入口为1。只有profile能提供J的冻结provenance。

```sh
# 只检查命令解析，不加载模型
uv run --locked python main.py --help

# 三套本地文件校验，不加载模型/调用API
uv run --locked python main.py --runtime-profile legacy --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank_diverse --check-runtime

# 通用环境烟测：需要至少一份本地PDF，不调用生成API
uv run --locked python -m scripts.smoke_check
# 缓存及默认JSON索引齐全时，另做真实本地检索
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.smoke_check --retrieval
```

`smoke_check --retrieval`面向默认JSON布局；不会替代二进制候选验收。`--check-runtime`只校验文件，不证明模型加载、远程服务可用或科学答案正确。J另记录了实际MiniLM/CPU加载和本地检索核验，见 [收尾记录](Q06_5J_CLOSEOUT.json)。

以下命令调用生成平台，输入包含问题和所选文献片段，可能计费：

```sh
uv run --locked python main.py --runtime-profile legacy \
  --output-dir output/manual-legacy -q "What is organic electrocatalysis?"
uv run --locked python main.py --runtime-profile hybrid_rerank \
  --output-dir output/manual-candidate -q "What is organic electrocatalysis?"
```

没有 `-q` 时进入交互模式，`exit`或`quit`退出。空检索不调用API；非空证据也可能不足以回答，模型判断仍需阅读原文。

## 3. 构建自己的索引

重建会读取本地PDF、加载/下载embedding权重并编码全部文本，但不会调用生成接口。先确认 `.env` 中embedding配置匹配本轮目标；普通builder不支持Qwen profile。以下明确选择旧MiniLM配置，发布到新的候选目录，目标已存在时拒绝覆盖：

```sh
CHEMQA_EMBEDDING_PROFILE= \
CHEMQA_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CHEMQA_EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
uv run --locked python -m src.pipeline.vector_index_builder \
  --pdf-dir data/raw_papers --destination output/indexes/my-minilm-candidate
```

构建先写暂存目录，核验原文覆盖、位置、身份、模型输入长度、向量/元数据和哈希后发布 `ready`。不自动覆盖当前 `data/` 或切换默认。已发布候选禁止增量修改，应另建目录。

使用自己构建的MiniLM索引，清除可能存在的Qwen profile，并通过环境驱动入口显式选择；**此命令会生成回答，不属于J冻结运行**：

```sh
CHEMQA_EMBEDDING_PROFILE= \
CHEMQA_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CHEMQA_EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
uv run --locked python main.py --index-dir output/indexes/my-minilm-candidate \
  --output-dir output/my-index-answers -q "What is organic electrocatalysis?"
```

Qwen构建走独立E入口，512-token页内窗口/64-token目标重叠，随后F迁移为NumPy/SQLite：

```sh
# 模型缓存齐全；会新建全库候选，不是日常健康检查
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065e build --device cpu --batch-size 8
# 从已记录的E源迁移，不重新编码；源路径由E验收记录确定
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065f migrate
```

E `build`创建新目录，不会自动将F默认源改成新E目录；若要迁移该新目录，按F命令的 `--source`明确指定。CPU/FP32新构建不保证与历史MPS/FP16排名逐项相同。E/F/G/H/I各自的重放参数见阶段记录： [E](Q06_5E_EMBEDDING.md)、[F](Q06_5F_STORAGE.md)、[G](Q06_5G_HYBRID.md)、[H](Q06_5H_RERANKING.md)、[I](Q06_5I_CONTEXT.md)。新索引/源码不再匹配J原哈希时，应另建经过核验的manifest；不能直接编辑旧哈希假称同一实验。Q01/Q02迁移工具仅供旧索引，不应对当前Q03数据反复应用。

## 4. 结果、批量与热力图

单次问答：`output/qa/<run-id>/`。正常回答保存 `answer.md`、`answer.evidence.json`、`run.json`及适用的引用分析。`failed`/`truncated`保存 `failure.json`，CLI单次失败退出码1。`no_evidence`为本地有界说明，不计模型生成成功。原始截断内容可留作诊断，不应当成完整回答。

候选索引：`output/indexes/<run-id>/`。批量：`output/qa_batches/`、`output/direct_api_batches/`。热力图：`output/heatmaps/`。运行ID使用UTC时间戳加UUID；批量 `complete`只表示会话汇总保存完成，仍需检查成功/失败/未测计数。自定义输出路径不自动被Git忽略。

```sh
# 查看帮助不调用API；真正运行批量命令会发送多个请求
uv run --locked python -m qa_testing.test_organic_electrocatalysis_qa --help
uv run --locked python -m qa_testing.direct_api_test --help

# 热力图：本地模型加载与相似度计算，不调用生成API
HF_HUB_OFFLINE=1 MPLBACKEND=Agg uv run --locked python -m heatmap_visualization.run_heatmap
```

批量脚本没有J的 `--runtime-profile`选项，不能假定它们沿用显式冻结profile。热力图使用索引向量的余弦分数，多查询按平均分选片段；颜色不表示证据支持概率。首次模型缓存不足时去掉离线变量并准备权重。

## 5. 回退与常见失败

冻结旧资产仍齐全时，显式回退无需删除候选或复制数据：

```sh
uv run --locked python main.py --runtime-profile legacy --check-runtime
# 以下为真实问答
uv run --locked python main.py --runtime-profile legacy -q "What is organic electrocatalysis?"
```

| 现象 | 处理 |
| --- | --- |
| `Frozen runtime file missing or changed` | 核对本机资产与manifest；源代码更新或搬迁需新验收，勿静默改哈希 |
| 离线模型加载失败 | 补齐匹配revision缓存，排除同名本地模型覆盖；profile拒绝shadow目录 |
| 索引/profile不匹配或未ready | 选择成对资产，或重新构建新目录；不隐式回退 |
| 查询超过输入上限 | 缩短查询；不依赖模型静默截断 |
| HTTP鉴权、超时或生成截断 | 查看failure的状态、attempt history及usage；不要把失败算作答案 |
| 引用可映射但公式/条件有误 | 阅读PDF原页，特别核对电荷、负号、工况归属；标记映射不能裁决科学支持 |

旧MiniLM上下文取前10并按余弦0.5过滤，阈值未校准为正确概率；Qwen重排候选按冻结顺序与预算选择，不套用旧阈值。公共候选最多10片段/每篇10，diverse最多每篇6；完整请求预算是保守UTF-8字节估算，不是供应商精确token数。旧默认没有候选全请求预算机制。

## 6. 分享与归档

```sh
uv run --locked python -m scripts.audit_secrets
uv run --locked python -m scripts.audit_secrets --staged
# 只创建本地无历史快照，不发布/推送
uv run --locked python -m scripts.prepare_source_release
```

扫描只覆盖定义的凭据模式/文本范围，不能称为全面安全证明。开发Git历史仍有已撤销旧凭据，直接推送原历史不是采用的公开路径。

源码快照排除 `.git`、`.env`、PDF/索引/权重、`output/`与历史答案目录；但会复制 `docs/`、`evaluation/`中的摘录、源路径及小型实验记录。分享前按材料权限和隐私需要筛选这些文件；“不含PDF文件”不等于“不含文献内容”。本轮仅本地检查，没有公开发布。

归档复现需另外保存获准保留的PDF、固定revision模型缓存、manifest绑定的索引/实验目录及原始回答，并验证SHA-256。生成平台权重只由别名标识，不保证未来重请求逐字相同。评估与预留集规则见 [评估说明](EVALUATION_GUIDE.md)。

## R01 修订后的运行差异

当前 CLI 与 `ChemicalQAExpert` 默认采用保守回答策略，实际提示/检查结果保存在生成输入记录中。`answer_validation` 失败表示发现可检测的额外数值、同段引用不匹配、反应式扩展或过强断言；查看 `failure.json` 的 `generation_input.answer_validation.findings` 及 `generation_result.partial_content`，回查原页或缩小问题后人工决定下一步。系统不因此自动重试。通过词法检查不等于工况归属或科学结论已验证。

本轮新的实现绑定在 R01 manifest，旧 J/Q11 验收文件属于 `6df5c64` 版本；旧 J 在当前源码上哈希不匹配是预期现象。旧行为复现应在独立检出该提交后使用原本地资产。详情见 [R01修订](R01_ANSWER_RELIABILITY.md)。
