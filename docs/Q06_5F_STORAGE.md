# Q06.5-F：索引存储迁移

日期：2026-10-07。状态：独立候选、工程验收及回退检查完成。默认 MiniLM/JSON 配置未切换；最终默认选择留给 J，下一项 G。

## 范围与决定

本轮固定 E 的 180 篇文献、6,960 个片段及 1024 维向量，改变持久化与加载方式。没有重新解析、分块或编码文献，没有改变模型、指令、排序规则、阈值或开发标签，没有增加 BM25/reranker。20 个开发查询使用 E 冻结的查询向量作受控比较；另外对 D01 做了一次真实 Qwen/MPS 应用烟测。预留查询执行数、生成 API 请求数均为 0。

**采用 NumPy `.npy` float32 向量 + SQLite 元数据。** 按原计划先试验 FAISS IndexFlatIP：安装的 faiss-cpu 1.14.3 能与 NumPy 2.5.3 独立运行，迁移和独立排名检查也通过；但全量回归暴露其与现有 PyTorch 2.14.1 在 macOS ARM64 同进程进行计算时出现 `OpenMP Error #15`，进程以 134 退出。分别让 PyTorch/FAISS 先执行实际矩阵计算，两个顺序均复现；仅 import 的烟测不能揭示该问题。

没有使用 `KMP_DUPLICATE_LIB_OK` 绕过冲突。FAISS 未被本轮应用采用，试验及独立基准保留于 [FAISS 试验记录](Q06_5F_FAISS_TRIAL.json)，其中 structurally ready 的试验目录不代表运行时兼容性通过。最终加载器只接受 NumPy/SQLite schema，拒绝该 FAISS 目录。已移除试验依赖；`pyproject.toml`、`uv.lock`、`requirements.txt` 与本轮开始时相同。此结果限于已测试的软件组合，不表示 FAISS 在所有环境不可用。

## 存储与加载约定

实现见 [二进制后端](../src/knowledge_base/binary_index.py)、[应用入口](../src/knowledge_base/vector_store.py)与[迁移/验收脚本](../scripts/validate_q065f.py)。候选包含：

- `vectors.npy`：固定原行序的 float32 矩阵。迁移拒绝会改变数值的类型转换；加载使用只读 memory map，禁用 pickle。NumPy 的 `.npy` 与只读映射用法依据 [官方 load 文档](https://numpy.org/doc/stable/reference/generated/numpy.load.html)及 [save 文档](https://numpy.org/doc/stable/reference/generated/numpy.save.html)。
- `metadata.sqlite3`：每行保存 `row_id`、唯一 `chunk_id`、`doc_id` 与完整片段 JSON。保留文字、源文件别名、物理页/字符区间、raw text、解析版本、分块版本及所有附加字段；有 doc_id 索引供后续按文献访问。运行时只读连接，按需读取命中片段。
- `storage.json`：保存 schema、后端、维度、行数、模型/revision、query/document 指令、输入预算、归一化、分块参数、解析版本、原文校验和、文档序列/向量摘要和源 E 产物校验和。
- `run.json`：独立候选的 ready 状态及上述三个存储文件的校验和。构建先写 staging，验证后一次性发布；不覆盖旧目录。

加载先检查 ready 与所有文件校验和，再验证模型配置、向量类型/形状/有限值/单位范数、向量摘要、SQLite 完整性与版本，以及连续行号、文献/片段 ID 和完整元数据摘要。不匹配时失败，不隐式回退到同目录 JSON，不修复或重写原数据。

检索沿用原 `cosine_scores` 的 float64 运算顺序，把与查询无关的文档缩放与范数缓存一次；按分数降序排序，同分保留原行号顺序。向量文件仍是原 float32，没有近似检索、量化或候选裁剪。`score_query` 保持返回与全部文档对齐的原余弦分数。缓存会占用额外内存，完整校验也会访问全部向量；memory map 不意味着加载阶段不读数据。

`VectorStore` 仍能读取旧结构化 JSON。选择新目录必须同时指定 E 的 pinned profile；缺少 profile、模型指令不兼容或产物不是 ready 均拒绝加载。现有上下文阈值边界保留，新模型需显式选择阈值，问答主入口默认配置没有更改。

## 全库一致性与回退

完整结果见 [全库验收](Q06_5F_FULL.json)及[独立回放](Q06_5F_REPLAY.json)：

- 6,960 行完整元数据逐项相同，float32 向量逐位相同；原文跨度/输入长度验收由 E 的冻结产物继承，并由源校验和与逐项一致性保证。
- 20 个开发查询的前十 chunk ID、顺序、每题指标及汇总指标与 E 完全一致；NumPy 后端与原余弦参照的最大前十分数差为 **0**。
- 发布后重新加载再次通过全部检查，并经公开 `VectorStore.similarity_search` 使用冻结查询向量回放，前十结果一致。
- 显式重新选择 E 的 JSON 目录，原文、向量与前十排名保持一致；源 E 的六个产物文件与旧 MiniLM 索引/processed chunks 校验和均未改变。
- 真实应用烟测先执行 PyTorch CPU 矩阵运算，再加载 Qwen/MPS FP16 与新后端，对 D01 重新编码查询，前十结果与 E 一致。见 [应用运行检查](Q06_5F_RUNTIME.json)。这是一题集成检查，不是新的问答质量评估。

E 的完整证据跨度召回@10 仍为 62.0%（18 道可评分开发题宏平均），没有由存储迁移产生新的召回收益。AI 草案标签仍待研究者复核，不能写成科学问答准确率。

## 体积与开销

比较相同 6,960 行数据的单个 JSON 索引，与 NumPy/SQLite 的三个存储文件；双方均排除额外 processed 副本、查询向量、评估输出和日志。

| 指标 | E JSON | NumPy + SQLite |
|---|---:|---:|
| 存储体积 | 221.6 MiB | 61.3 MiB |
| 加载中位数 | 2.07 s | 0.37 s |
| 进程 RSS 高水位中位数 | 2,084.6 MiB | 319.3 MiB |
| 单次检索中位数 | 8.11 ms | 1.12 ms |
| 单次检索 p95 中位数 | 8.82 ms | 1.25 ms |

存储减少约 72.4%。候选写入约 0.55 秒，该时间不包括后续完整验收/回放和基准。完整数值及方法见 [性能记录](Q06_5F_BENCHMARK.json)。

每个后端分别启动 3 个新进程，均包含校验和、profile、结构验证；每进程先暖身 3 次，再对 20 个冻结查询各运行 5 轮，计 100 次单查询检索。BLAS 线程固定为 1，最终取三个进程测量值的中位数。包含余弦评分、排序及命中元数据读取，不含模型加载和查询编码。文件系统缓存未受控，RSS 为进程生命周期高水位；这是单机观察，不是冷盘或端到端问答速度承诺。

## 复现与选择

仓库根目录、现有锁定环境下运行。迁移默认从 `docs/Q06_5E_FULL.json` 读取源目录，所有模型与数据均留在本地：

```sh
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065f migrate
```

本轮已验收候选目录：`output/indexes/20261007T050945-4456434906334000aac1efefcb869097`。重跑会创建新的目录；Git 忽略全部索引/文献/模型缓存，只保存代码及小型验收记录。

```sh
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065f replay \
  --candidate output/indexes/20261007T050945-4456434906334000aac1efefcb869097

HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065f runtime --device mps \
  --candidate output/indexes/20261007T050945-4456434906334000aac1efefcb869097
```

显式选择新候选时，设置 `CHEMQA_EMBEDDING_PROFILE=config/q065e_embedding.json`，同时设置 `CHEMQA_INDEX_DIR` 为以上目录。回到 E JSON，只改变 index 目录为 `output/indexes/20261007T041905-a5b35ed389b84d0ca8ca268607b09f8b` 并保留同一 profile；回到旧 MiniLM 默认配置则同时取消这两个覆盖项。无需复制或覆盖文件。

178 项回归通过，其中 16 项新增存储检查覆盖完整数据往返、同分边界、损坏/错位/配置不匹配拒绝、只读与不可覆盖、数值精度保护、应用分支及实际 PyTorch 运算共存。Ruff 与格式检查通过；详细源码、依赖、忽略规则及凭据模式检查见 [工程验收](Q06_5F_VALIDATION.json)。
