# Q0：环境准备与配置整理

日期：2026-10-06  
状态：完成（macOS arm64 本机验证）；尚未验证其他操作系统与在线回答 API。

## 问题与范围

原项目未固定 Python 和依赖版本；依赖误写了独立的 `fitz` 包，并包含标准库 `pathlib`；缓存和编辑器文件被 Git 跟踪；API 密钥硬编码；模型远程地址无法加载。

本项只整理运行环境、配置、忽略规则及启动说明，并验证本地执行。Q01 的数据身份、Q07 的 API 状态处理、Q08 的输出路径与重建流程等问题继续单独推进。

## 验收标准

- 能从项目声明及锁文件创建 Python 3.12 环境。
- 核心模块可导入，PDF 可读取，模型和现有索引可加载并执行检索。
- 不提供密钥时，在发起网络请求前明确报错；终端环境变量优先于项目 `.env`。
- 忽略本地环境、密钥、缓存、编辑器配置和生成输出；取消跟踪已存在的开发产物，保留本地文件。
- 保存当前文本块及索引，不重建或覆盖。

## 实际改动

- 添加 `pyproject.toml`、`.python-version`、`uv.lock`；创建 `.venv`。以 uv 为主要依赖来源，`requirements.txt` 从锁文件导出。
- 正确依赖 PyMuPDF，PDF 加载器使用 `import pymupdf as fitz`；移除独立 fitz 和 pathlib 依赖。
- `.env.example` 提供 API 和 embedding 配置；本机 `.env` 已创建，API key 留空。配置按项目路径寻找 `.env`，不依赖当前工作目录，终端变量优先。
- 在发送 API 请求前检查空密钥。此项未改造既有错误字符串或重试逻辑。
- 默认 embedding 地址修正为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，固定 revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`。自定义模型可单独配置 revision；本地模型仍可从 `models/` 加载。
- 调整导入顺序，使 `.env` 中的 Hugging Face 缓存配置在库初始化之前生效。
- 添加 `.gitignore`；32 个已跟踪的系统文件、IDE 文件和 Python 缓存已取消跟踪，本地副本保留。取消跟踪的变更已暂存，其余源代码改动未提交。
- `main.py --help` 在模型初始化前处理；README 使用项目根目录下的模块入口，并修正 FAISS 描述。
- 添加 `scripts/smoke_check.py`，提供无需回答 API 的本地检查入口。

## 验证结果

| 检查 | 结果 |
|---|---|
| `uv sync`、`uv sync --locked --offline` | 通过；CPython 3.12.13，macOS arm64 安装 45 个包 |
| `uv lock --check --offline` | 通过；锁文件与项目声明一致 |
| `uv pip check` | 通过；依赖兼容 |
| `uv run --locked python main.py --help` | 通过；未初始化 embedding 模型 |
| `uv run --locked python -m scripts.smoke_check` | 核心模块导入、单页 PDF 提取、空密钥检查通过 |
| `.env` 独立于工作目录，终端环境变量优先 | 使用临时目录与虚拟密钥验证通过 |
| `HF_HUB_OFFLINE=1 uv run --locked python -m scripts.smoke_check --retrieval` | 通过；现有索引形状 (3200, 384)，返回 3 个非空片段和有限分数 |
| 忽略规则与取消跟踪 | 通过；`.env.example`、锁文件和项目源数据仍可跟踪 |
| 处理后文本块和向量索引 SHA-256 | 与运行前一致 |
| `git diff --check` 与已暂存变更检查 | 通过 |

核心版本：NumPy 2.5.3、PyMuPDF 1.28.2、Sentence Transformers 4.1.0、PyTorch 2.14.1、Transformers 4.57.6、Matplotlib 3.11.2、Seaborn 0.13.2、Requests 2.34.2、python-dotenv 1.2.4；完整版本见锁文件。

模型缓存已下载到被忽略的 `models/huggingface/`。新机器首次运行仍需要下载依赖和模型，离线检查以缓存已存在为前提。

## 历史向量的样本兼容性检查

选取索引位置 0, 290, 581, 872, 1163, 1454, 1744, 2035, 2326, 2617, 2908, 3199，使用官方模型在 CPU 上逐条重新编码原索引中的文本。
12 个样本的余弦相似度约为 1，最大向量分量绝对差为 `5.96046448e-07`。浮点舍入可使计算出的余弦值轻微大于 1。

该结果支持这批样本与修正后模型兼容，不证明全部 3200 个向量的来源或检索效果，也不消除模型输入截断等 Q03 待核查问题。

数据校验值：

```text
processed_chunks.json: 18e1190039c0ff28ebc4c27c91d88b88c027c8cced1ec42f76b92d5c9f870cc0
vector_index.json: 9c39957e625b562b74ce352294bdec1b653e94f2f1c6acc0f6c48a428ff2e414
```

模型地址依据：[官方模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)。依赖依据：[PyMuPDF 安装说明](https://pymupdf.readthedocs.io/en/latest/installation.html)、[uv 锁定与同步说明](https://docs.astral.sh/uv/concepts/projects/sync/)。

## 未解决事项

- Q09：旧密钥仍可能存在于 Git 历史；撤销或轮换及历史处理尚未执行。
- 在线回答 API 未调用；需在 `.env` 填写自己的有效密钥后另行验证。
- Q08：既有固定输出文件名、部分相对路径与索引重建行为尚未整理。
- Q01–Q07、Q10：数据身份、引用、文本处理、检索定义、API 状态与受控评估仍按计划逐项推进。
- 本次没有运行历史批量问答，不以本地检查证明回答准确性或检索质量。

## Q0 补充：Ruff 报警修复（2026-10-06）

- Ruff 0.16.10 纳入开发依赖并锁定；项目设置 Python 3.12 目标版本与共享 logger 识别。检查和格式化针对 Python 源文件，历史回答 Markdown 保持原样；没有禁用报警规则。
- 修复未定义的 `Any`、未使用导入和变量、空 f-string、导入顺序、旧类型注解及隐式 Optional；共享配置字典显式标记 `ClassVar`。
- 模型库改为在模型加载时导入，确保 `.env` 的缓存配置先加载；类型检查使用独立导入，兼容导入排序。
- 时间戳使用本地时区的 aware datetime；ISO 时间字符串包含时区偏移，既有格式化日期仍按本地时间显示。
- 既有异常边界保留原来的返回或继续处理行为，同时记录异常堆栈；未重构 API 错误状态或批量测试成功判定。
- 清理集合生成与字典遍历写法，移除通过 Python 模块运行的入口中不必要的 shebang，并统一 Python 格式。

复验：`uv run --locked ruff check .` 全部通过，`uv run --locked ruff format --check .` 的 20 个 Python 文件全部通过；离线本地检索、辅助入口导入、`.env` 缓存配置及依赖一致性复查通过。处理后文本块及索引不变。本次仍未调用回答 API。
