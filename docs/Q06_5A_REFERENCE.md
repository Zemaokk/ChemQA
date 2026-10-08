# Q06.5-A：升级前参照与资源盘点

日期：2026-10-07

状态：已完成本地参照采集、离线回归、原目录重放与隔离恢复重放；未升级模型或依赖，未调用生成 API。

## 问题与验收标准

后续会改动模型、分块、索引和检索流程，需要先保存一份可以核查与恢复的旧配置。本项验收：

1. 保存有效的非敏感配置、依赖锁文件、源码、模型与当前索引，并用 SHA-256 校验。
2. 保存固定查询的完整检索证据、顺序、分数、查询向量及阈值筛选结果。
3. 在原目录重新编码查询并重放，在全新隔离目录恢复旧文件后再次重放。
4. 记录本机资源、现有离线回归和能力边界；不修改工作索引，不把执行一致性写成质量提升。

问题标注与评分规则归 Q10-A；运行路径和输出机制的通用重构归 Q08。本项脚本只服务于参照采集与恢复。

## 已保存内容

新增 [采集与验证脚本](../scripts/validate_q065a.py)，支持 `capture`、`verify`、`restore`。每次采集与恢复必须使用尚不存在的目标目录，避免覆盖旧参照。

本地参照目录：`output/q065a_reference_20261007/`，由现有 `/output/` 规则忽略，不加入 Git；文件总量约 846 MiB。包括：

- `source.zip`：Python 源码、测试、合成样例、`pyproject.toml`、`uv.lock`、Python 版本声明及 Git 忽略规则。
- `model/`：当前 Sentence Transformer 的独立模型文件，可脱离原下载缓存加载。
- `data/vector_db/vector_index.json` 与 `data/processed/processed_chunks.json`：当前数据的独立副本。
- `retrieval.json`：7 个查询各自的 top 10 完整原文证据、完整 ID、位置元数据与余弦分数，以及阈值筛选后的上下文摘要。
- `query_vectors.npy`：查询向量，支持独立重放向量评分。
- `config.json`、`manifest.json`：配置、资源、包版本清单、文件哈希和验证摘要。
- `unittest.log.json`、`ruff_check.log.json`、`ruff_format.log.json`、`q06.log.json`、`q06.json`：离线验证日志与 Q06 样例报告。

不复制 `.env` 或 API 密钥值。只记录是否配置密钥；恢复时生成不含凭据的环境配置。当前未配置密钥，未建立真实生成模型基线。

Git 中保留以下小型审计记录：

- [采集清单与资源记录](Q06_5A_BASELINE.json)
- [原目录重放结果](Q06_5A_REPLAY.json)
- [隔离恢复重放结果](Q06_5A_RESTORED_REPLAY.json)

## 当前配置与资源

| 项目 | 本次实际记录 |
|---|---|
| 硬件 | Apple M5，16 GB 内存，10 个逻辑 CPU |
| 架构 | arm64 |
| Python | 3.12.13 |
| 核心包 | Sentence Transformers 4.1.0；Transformers 4.57.6；PyTorch 2.14.1；NumPy 2.5.3；PyMuPDF 1.28.2 |
| Embedding | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Revision | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| 输入限制 | 128 token，包含 2 个特殊 token |
| 索引 | 180 份不同 PDF 身份，26,025 个片段，384 维 |
| 检索 | 余弦评分，top 10，稳定排序；上下文阈值 0.5 尚未校准 |
| 生成配置 | `deepseek-reasoner`，temperature 0.3，输出上限 30,000；仅保存，未实测 |
| 重放设备 | CPU，Torch 单线程；模型自动选择的设备也是 CPU |
| MPS | 构建支持 MPS；当前受限进程中 `is_available()` 为 false |
| CUDA | 当前不可用 |

硬件信息仅保存型号、芯片、内存和处理器信息，不保存设备序列号。CPU 张量运算烟测通过。MPS 记录只描述本次进程，不能据此断言主机在其他运行环境中无法使用 MPS；Q06.5-C 需进一步验证实际运行条件。

对于后续两个 0.6B 模型，16 GB 内存使峰值资源值得关注；本项没有加载候选模型，不给出“足够运行”或推理速度结论。批大小、精度与同时驻留策略由 C 的实测确定。

## 验证结果

- 63 项单元测试通过：原 Q01–Q06 的 60 项，加上本项的 3 项凭据排除、文件篡改/缺失拒绝和恢复目录覆盖拒绝检查。
- Ruff 检查及格式检查通过。
- Q06 的 8 个合成样例通过离线检查；非空证据使用模拟 HTTP，未评价真实模型语义行为。
- 7 个执行参照查询：沿用 Q04 的 5 个英文问题，补充 1 个中文问题和 1 个条件查询。问题未标注相关性或科学答案，不能当作正式评估集。
- 原目录重放和隔离目录重放均通过：重新编码的向量在 `atol=1e-7` 内一致，top 10 证据与顺序一致，分数在 `atol=1e-12` 内一致，阈值筛选结果及序列化上下文 SHA-256 一致。
- 使用保存的查询向量重新评分，top 10 身份与顺序一致。
- 当前索引和处理文件采集前后 SHA-256 不变，参照目录内全部归档文件通过完整性检查。
- 外部生成 API 请求为 0。重放入口阻止 Requests 网络请求，并以 Hugging Face 离线模式读取现有模型。

查询记录中的耗时包含重复编码及验证开销，不是标准性能基准。检索质量、证据支持和跨体系外推表现均未在本项评估。

## 重放与隔离恢复

在项目根目录执行；保持使用当前锁定环境与离线模式：

```bash
UV_CACHE_DIR=/private/tmp/chemqa-uv-cache \
HF_HUB_OFFLINE=1 MPLCONFIGDIR=/private/tmp/chemqa-matplotlib MPLBACKEND=Agg \
uv run --locked python -m scripts.validate_q065a verify \
  --bundle output/q065a_reference_20261007 \
  --report output/q065a_replay_again.json
```

恢复旧源码、模型、数据和非敏感配置到一个**全新目录**，保留当前工作目录：

```bash
UV_CACHE_DIR=/private/tmp/chemqa-uv-cache HF_HUB_OFFLINE=1 \
uv run --locked python -m scripts.validate_q065a restore \
  --bundle output/q065a_reference_20261007 \
  --destination output/q065a_restore_new
```

本次已恢复到 `output/q065a_restore_20261007/`，并在该目录运行恢复的源码与模型。使用当前 `.venv` 的同一 Python 解释器，验证命令为：

```bash
cd /Users/zemaochen/projects/ChemQA/output/q065a_restore_20261007
HF_HUB_OFFLINE=1 MPLCONFIGDIR=/private/tmp/chemqa-matplotlib MPLBACKEND=Agg \
/Users/zemaochen/projects/ChemQA/.venv/bin/python -m scripts.validate_q065a verify \
  --bundle /Users/zemaochen/projects/ChemQA/output/q065a_reference_20261007 \
  --report /Users/zemaochen/projects/ChemQA/output/q065a_restored_replay_again.json
```

以上证明了相同依赖环境下的源码、配置、模型及数据恢复。未来回退还需使用归档的 Python 版本声明、`pyproject.toml` 和 `uv.lock` 建立兼容环境；本项没有归档 Python 安装程序、依赖 wheel 或整个 `.venv`，不能保证未来无缓存、断网的新机器直接安装。

原始 PDF 未额外复制；恢复检索依靠完整索引中的原文和位置元数据。重新提取/构建文献库仍需要保留原始 PDF，不能仅凭此参照包完成。本地参照包也不是异地备份，Git 中的小型清单无法替代模型和索引文件。

## 下一项

按总计划进入 Q07，统一 API 成功/失败与截断状态。新模型选择、通用输出管理、标注问题集和质量结论留给各自后续任务。
