# Q06.5-E：Embedding 与分块候选

日期：2026-10-07。

本项固定 Q06.5-D 保留的 PyMuPDF 原文，只比较 embedding 与分块配置。全库候选的结构验收、开发集指标和回放结果分别记录；默认配置的最终选择仍归 Q06.5-J。Q10-A 标签为 AI 草案、领域复核待完成，不能将这些指标写成问答准确率。

## 设计与输入约定

- 候选模型：`Qwen/Qwen3-Embedding-0.6B`，固定 revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，1024 维，float32 单位向量。
- 查询使用模型卡及固定模型配置提供的英文 `Instruct: ...\nQuery:` 前缀；文献无前缀。两者通过独立编码分支，前缀只添加一次。
- 模型能力上限为 32k，本轮将实际输入上限固定为 512 token，以控制片段范围和本机开销。完整查询指令、文献内容及特殊 token 都计入预算；本版本 tokenizer 加入 1 个特殊 token。
- 在编码前逐批检查未截断 tokenizer IDs，并与模型实际 preprocessing 的有效 IDs 比对；超限或 ID 不一致立即失败。模型内部的默认截断不能作为输入处理策略。
- MPS 使用 FP16 权重推理，CPU 使用 FP32；输出转为 float32 后再次归一化。实际设备、精度与资源写入运行记录。

实现见 [独立编码入口](../src/knowledge_base/embedding.py)、[分块实现](../src/knowledge_base/paragraph_processor.py)、[固定模型配置](../config/q065e_embedding.json)和[实验协议](../config/q065e_experiment.json)。模型用法依据 [Qwen 官方模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)。旧模型编码分支保留。

## 固定原文与位置

冻结 181 个文件、180 个不同 PDF 身份，去重后共 1,929 个物理页。每份文献保存原始页文字、PDF 身份、来源别名及原文校验和。详见 [原文冻结记录](Q06_5E_CORPUS.json)。

原文仍来自 `get_text("text", sort=False)`。另外读取同一解析器的 text blocks，只有全部块拼接与该页原文逐字符一致时才接受其边界作为段落提示；本库全部页面通过。**text block 是版面提示，不等同于语义段落。** 不改变双栏原文顺序，不拼写修正，不改写化学式或数值。

新分块仅规范空白，保留科学字符。页内窗口和 block 方案均在物理页边界停止；重叠参数是目标 token 数，词边界可使实际重叠有所变化。每个片段用 Q02 的页面局部字符区间保存精确原文，再从片段文字、文献身份和片段序号生成身份。旧索引及其片段身份保留。

block 方案优先在预算内的块末尾结束；当块末尾不足目标长度的一半时继续按 token 预算分割，避免大量极短片段。超长块也必须拆分，并保持所有非空白原文字符可追溯。

## 小样本受控对照

先冻结规则：11 篇开发证据文献，加 9 篇按 PDF 身份排序选择的干扰文献，排除预留证据文献。20 个开发问题中 18 个 answerable 问题计算跨度指标，2 个 scoped-insufficient 问题不按普通召回评分。预留查询不编码、不排序，生成 API 请求为 0。

对照包括：旧 MiniLM/旧分块、Qwen/相同旧分块、Qwen/512 页内窗口/64 重叠、Qwen/256 block/32 重叠、Qwen/512 block/64 重叠。模型对照固定片段；边界对照固定 512/64 与模型。256/32 与 512/64 比较的是联合分块配置，没有单独估计重叠量的贡献。

预设选择规则依次为：完整证据跨度召回@10、原文字符覆盖@5、较少片段数。只在胜出配置的召回@10及覆盖@10均不低于同候选库 MiniLM 时进入全库构建。

| 配置 | 片段数 | 完整跨度召回@5 | 完整跨度召回@10 | 原文字符覆盖@10 |
|---|---:|---:|---:|---:|
| MiniLM / 旧分块 | 3,024 | 0.0% | 5.6% | 10.6% |
| Qwen / 相同旧分块 | 3,024 | 15.7% | 15.7% | 38.8% |
| Qwen / 页内窗口 512 / 重叠 64 | 817 | 53.7% | 76.9% | 76.9% |
| Qwen / block 256 / 重叠 32 | 1,829 | 39.8% | 48.1% | 48.1% |
| Qwen / block 512 / 重叠 64 | 1,003 | 48.1% | 59.3% | 59.3% |

本轮选择 **512-token 页内窗口，目标重叠 64**。block 方案未胜出，保留为已评估实验；不能预设段落切分必然改善本库。Qwen 候选已通过小样本门槛，因此本轮不额外下载 BGE-M3；这不构成 Qwen 优于 BGE 的结论。

这些数字是同一受限候选库内的对照，不能与全库候选混为同一实验。相同 top-k 不代表相同总证据 token 预算；长片段可覆盖更多原文，本项结果包含这一分块配置效应，统一生成上下文预算留给 Q06.5-I。完整排名、跨度指标与 token 数见 [小样本记录](Q06_5E_PILOT.json)。没有继承旧阈值 0.5，没有报告基于非穷尽相关性标签的 nDCG，也没有评估回答质量。5 道小样本漏召回题单列于 [失败记录](Q06_5E_PILOT_FAILURES.json)，保留机制、数值与跨论文比较的已知缺口。

## 资源选择

在本机 MPS/FP16 上用 64 个完整 512-token 输入检查 batch 8/16，两者输出相同。单次编码约 7.01/7.10 秒，采样 MPS driver allocation 约 2.23/3.23 GiB，因此按预设规则保留 batch 8。RSS 高水位约 2.23 GiB。详见 [资源检查](Q06_5E_RESOURCE.json)。

这些是单次本机观察；allocator 采样值不是内存峰值，不视为严格性能基准。设备错误会中止当前构建，可显式选择 CPU 在新目录重跑，避免将不同运行精度混入同一次构建。

首次全库尝试出现分批耗时明显波动，在尚未发布时主动停止；日志与处理依据见 [运行说明](Q06_5E_RUN_NOTES.json)。后续构建每处理 64 个输入就释放未占用的 MPS 缓存，并记录清理前后 driver allocation；若清理后仍超过 6 GiB 则中止，不发布候选。这是资源约束，没有改变模型、文本、分块或 token 输入。

## 构建与复现

在仓库根目录使用现有锁定环境和本地模型缓存运行；不安装新依赖、不发起生成请求：

```sh
HF_HUB_OFFLINE=1 MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065e freeze
HF_HUB_OFFLINE=1 MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065e pilot --device mps --batch-size 8
HF_HUB_OFFLINE=1 MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065e probe --device mps
HF_HUB_OFFLINE=1 MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065e build --device mps --batch-size 8
```

每次冻结、小样本和索引构建都写入新的独立目录。主环境依赖不变；文献、模型缓存和候选索引位于本地。输出遵循现有 `/output/` 忽略规则，Git 中仅保存实现、配置和小型审计记录。

## 显式检索与阈值边界

候选索引只在全部结构验证通过后发布为 `ready`，可通过 `CHEMQA_EMBEDDING_PROFILE=config/q065e_embedding.json` 与 `CHEMQA_INDEX_DIR=<已发布候选目录>` 同时选择。`VectorStore` 会核查文件校验和、完整模型配置、指令、维度及单位归一化；不匹配时失败。`similarity_search` 使用 query 编码分支返回原始 top-k，适合本项的检索核查。

候选模型没有继承旧的上下文阈值；`retrieve_relevant_context` 要求显式选择阈值。现有问答主入口不自动使用本候选，生成阈值与最终证据选择在后续开发集实验中确定。默认配置不切换，回到原配置只需不设置候选 profile 和 index 路径。

旧通用 builder 保持原行为；新候选需用本项的 `build` 命令，以避免走旧分块/旧 manifest 验证流程。本轮继续采用现有 JSON 存储，FAISS/SQLite 等存储迁移留给 Q06.5-F。

## 全库验收与结果

全库独立候选已发布为 `ready`：180 篇不同 PDF、6,960 个片段、1024 维。6,960 个片段均逐项核对源 PDF 与字符区间，所有非空白原文字符被片段覆盖；没有超限输入，最长文献输入为 512 token，查询含指令及特殊 token 为 48–69 token。实际 preprocessing IDs 与未截断输入一致，向量有限且单位归一化。完整记录见 [全库验收](Q06_5E_FULL.json)。

| 全库配置 | 完整跨度召回@5 | 完整跨度召回@10 | 原文字符覆盖@10 | 已标注文献召回@10 |
|---|---:|---:|---:|---:|
| 旧 MiniLM / 旧分块 | 0.0% | 5.6% | 10.6% | 72.2% |
| Qwen / 页内窗口 512 / 重叠 64 | 49.1% | 62.0% | 62.0% | 88.9% |

两行均使用 180 篇全库和相同的 18 道可评分开发题，指标为逐题宏平均。这是模型与分块联合配置的差异；模型独立贡献只能参考前述固定片段对照，不能把全库差异全部归因于 embedding。相同 top-k 的总文本预算仍不同。20 个开发查询均执行，6 个预留查询未执行，生成请求为 0。

全库候选有 10/18 题召回全部已标注跨度，另 8 题仍有缺口：D03、D08、D10、D11、D15、D16、D17、D18，详见 [全库失败记录](Q06_5E_FULL_FAILURES.json)。这些缺口保留给研究者复核及 G/H 召回/重排实验；本项不据此改写标签或调试预留题。

本机 MPS/FP16、batch 8：文献编码 1,370.36 秒，20 个查询编码 0.53 秒，从分块到发布前验收约 1,417.79 秒。进程 RSS 高水位约 1.85 GiB；采样 MPS driver allocation 最大约 2.17 GiB，逐批清理后最大约 1.13 GiB。采样值不是 GPU 内存峰值，耗时为单次运行观察。JSON 索引约 221.6 MiB，继续保留现有后端；后续 F 用固定文本和向量比较存储方案。

本地候选目录：`output/indexes/20261007T041905-a5b35ed389b84d0ca8ca268607b09f8b`。目录被 Git 忽略，配置与小型验收记录随源码保存。manifest 顶层 `embedding` / `chunking` 是候选实际配置；通用 `config` 中未启用的应用默认参数不代表本候选分块。

## 回放与工程验证

重新加载候选时核查全部产物校验和和模型配置，再用同设备、同批大小重新编码 20 个开发查询：查询向量最大差异为 0，前十排名及指标完全相同；公开 `VectorStore.similarity_search` 单题检查也一致。见 [候选回放](Q06_5E_REPLAY.json)。

```sh
HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065e replay --device mps \
  --candidate output/indexes/20261007T041905-a5b35ed389b84d0ca8ca268607b09f8b
```

CPU 构建可显式使用 `--device cpu`，按 CPU/FP32 策略生成新的独立目录；本轮完整候选与逐项重编码回放验证的是 MPS/FP16，不宣称跨精度排名逐项相同。

旧 Q10-A 索引使用冻结查询向量回放，全部原始检索、上下文排名和指标保持一致，见 [旧基线回放](Q06_5E_LEGACY_REPLAY.json)。原索引及 processed chunks 的 SHA-256 与构建前一致。默认 MiniLM、依赖锁文件和既有问答路径保留。

162 项回归测试通过，包括 18 项新增检查；Ruff 检查及 67 个 Python 文件格式检查通过。新增检查覆盖输入前缀/特殊 token、超限与静默截断拒绝、Unicode 原文覆盖、manifest 不匹配、单位归一化、旧阈值隔离、预留集保护及 MPS 缓存资源约束。工作树凭据模式审计无发现（排除被忽略的本地密钥文件，不扫描 Git 历史）。见 [工程验收](Q06_5E_VALIDATION.json)与[审计记录](Q06_5E_SECRET_AUDIT.json)。

Q06.5-E 完成独立候选和工程验收，默认配置的最终选择留给 J；下一项为 Q06.5-F。
