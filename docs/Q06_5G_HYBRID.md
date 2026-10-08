# Q06.5-G：BM25 与混合召回

日期：2026-10-07。状态：工程实现、开发集对照、回放及真实应用烟测完成。后续候选工作流选择 **Dense + BM25 等权 RRF**；产品默认 MiniLM 配置未切换，最终默认选择留给 J。下一项 H 使用本项已冻结的前 50 个候选。

## 固定范围与采纳规则

固定 F 的 NumPy/SQLite 候选：180 篇不同 PDF、6,960 个片段、Qwen3-Embedding-0.6B 的原向量、原文与位置。未重新解析、分块或编码文献，未改模型/阈值/标签，没有引入 reranker、翻译 API 或同义词词典。

在查看结果前冻结 [实验协议](../config/q065g_experiment.json)：BM25 k1=1.2、b=0.75，query term frequency 为 binary；Dense/BM25 每路取前 50，RRF 常数 60，等权，按 chunk ID 合并，同分保留原行号顺序。只有混合的完整跨度召回@10严格高于 Dense，且字符覆盖@5、已标注文献召回@10均不退步时，才在候选工作流采用混合；否则保留 Dense。不做参数扫描。

20 个开发查询均用 E 冻结的查询向量对照，其中 18 个 answerable 问题按原文跨度评分，2 个 scoped-insufficient 问题不计普通召回。6 个预留查询没有编码或排序；数据完整性验证可读取预留文件和源锚点，但不使用其结果选择配置。生成 API 请求为 0。另对 D01/D03 做两条真实模型集成检查，与受控对照分别记录。

## 关键词与分数约定

实现见 [词项与 BM25 索引](../src/knowledge_base/lexical_index.py)、[RRF/显式 profile](../src/knowledge_base/hybrid_search.py)和[检索入口](../src/knowledge_base/retriever.py)。不新增依赖。

词项处理仅操作搜索副本，原文及源位置不变：

- NFKC 规范化宽字符、上下标，并统一常见横线/负号；`H₃O⁺`/`H3O+`、`HSO₄−`/`HSO4-` 使用相同词项。
- 保留带符号数值、小数和科学计数法，例如 `−0.25` 与 `0.25` 是不同词项，`1E-3` 保留为一个数值词项；不做数值等价换算。
- 拉丁词 casefold，保留连字符整体并加入组成词；保留单位线索、希腊字符。用元素符号规则增加区分大小写的 formula alias，`Co` 与 `CO` 有不同 alias；其普通词项仍共享 `co`，不能宣称消除了全部歧义。
- 中文使用字符及相邻双字词项，没有人工词典或自动翻译。仅使用固定通用英文功能词表，不根据失败题添加词项。

这是可审计的规则 tokenizer，不是化学结构解析器。NFKC 不能完整保留上下标的化学角色；复杂电荷、科学计数法的不同写法、单位转换、断词及系统性同义词仍可能不匹配。大小写公式启发式也可能把标题中的短词识别为元素线索。保留这些限制，不改写科学原文。

BM25 采用正 IDF `log(1 + (N-df+0.5)/(df+0.5))`，分数为各唯一查询词项的 `idf * tf * (k1+1)/(tf+k1*(1-b+b*dl/avgdl))` 之和。k1/b 与 IDF 参考 [Lucene 官方 BM25 文档](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html)，本实现使用明确长度与自定义词项，不宣称与 Lucene 分数逐位相同。重复查询词不增加权重，未命中词项的行不会以零分补入结果。

RRF 使用 `sum(1/(60+rank))`，rank 从 1 开始，参考 [Elastic 官方说明](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion)。每路同一 chunk 只使用第一次出现的位置，跨路合为一个候选，保留每路原始分数、rank 和 score kind。不同论文或同论文的不同片段保留，避免错误合并来源与证据跨度。

## 索引与完整性

独立 lexical candidate 包含 `lexical.json`、`vocabulary.json` 和 `postings.npz`。记录 analyzer 版本、规则指纹、Unicode 数据版本、k1/b、行数、平均长度、词表/倒排数量及 F 的 storage/document/model 指纹。倒排保存排序后的 row IDs、term frequencies、词项 offsets 与文档长度，禁用 pickle。

发布前检查数组、词表、逐词行号唯一性、频次与文档长度一致性；加载时核查 ready 状态、全部文件校验和、规则指纹和 Dense 行映射。不同文献序列、模型或未发布索引不能混用。后续 retrieval profile 再绑定 lexical run 校验和，防止 profile 指向变化后的关键词索引。

本轮词表 64,307 项，倒排 1,005,089 项，三个 lexical 文件合计约 3.00 MiB，构建及结构验证约 1.81 秒。F 与旧 MiniLM 索引不修改；全部新索引及排名快照使用已存在的 `/output/` 忽略规则。

## 开发集对照

结果见 [完整验收](Q06_5G_FULL.json)。三行共用相同片段、相同问题、相同最终 top-k；这是不同召回策略比较，混合访问两路候选，其成本另计。

| 策略 | 完整跨度召回@5 | 完整跨度召回@10 | 字符覆盖@10 | 已标注文献召回@10 | 首个完整锚点 MRR，截断于10 |
|---|---:|---:|---:|---:|---:|
| Dense | 49.1% | 62.0% | 62.0% | 88.9% | 0.3746 |
| BM25 | 40.7% | 50.9% | 50.9% | 83.3% | 0.3708 |
| Dense + BM25 / RRF | 51.9% | 70.4% | 70.4% | 94.4% | 0.4568 |

指标为 18 题宏平均；Dense 前十排名与全部指标和 E 完全一致。混合完整跨度召回@10提高约 8.3 个百分点，且通过全部预设门槛，因此选择候选 profile 的 `mode=hybrid`。本轮没有 @10 退步题；不能据此宣称其他排名位置、未标注证据或新问题均不退步。

RRF 收益集中在 D03 和 D18：D03 完整跨度召回@10由 0 增至 1，D18 由 0 增至 0.5。仍有 7 题未覆盖全部已标注跨度：D08、D10、D11、D15、D16、D17、D18，详见 [逐题失败与变化](Q06_5G_FAILURES.json)。没有把未标注命中判为负例，也不报告 nDCG。标签仍为 AI 草案、领域复核待完成，这些不是科学问答准确率或独立测试集结论。

前 50 候选的完整跨度召回为 Dense 82.4%、BM25 71.3%、混合 85.2%。这是候选覆盖指标，与前十结果分别保存；不能用它冒充最终证据选择或回答质量。H 将固定已选混合方案前 50 的 chunk IDs 和顺序，比较重排启用/关闭，不扩充候选池。

## 语言与重复候选诊断

20 个查询中 14 个有 CJK 词项，14 个都没有 CJK 词项直接命中当前英文语料。BM25 命中依赖仍可匹配的英文词、姓名、缩写、公式及数字；这里记录的是词项覆盖现象，没有通过自动翻译解决跨语言语义问题。Dense 仍承担跨语言检索作用。

| 前十诊断，20 查询均值 | Dense | BM25 | 混合 |
|---|---:|---:|---:|
| 不同论文数 | 4.05 | 4.05 | 3.95 |
| 已命中论文的额外片段数 | 5.95 | 5.95 | 6.05 |
| 最大单篇占比 | 63.5% | 67.5% | 67.5% |
| 原文区间重叠片段对数 | 1.75 | 1.90 | 1.75 |

跨路 chunk ID 已去重，但混合没有改善单篇集中问题。同论文不同位置不等于无效重复，裁掉它们可能损失证据。本轮不加每篇上限或基于文本相似度的去重；多篇覆盖与最终上下文选择交给 I。`rankings.json` 保留两路前 50、融合前 50、每路贡献、候选交集/并集数量与逐题诊断，可追溯和重算。

## 本机开销与验证

每路取前 50、读取命中元数据，20 个冻结查询循环 5 轮，每种策略共 100 个计时样本；BLAS 线程固定为 1，使用已加载索引。单机暖态中位数/p95：Dense 1.50/1.54 ms、BM25 0.72/0.93 ms、混合 2.30/2.52 ms。混合耗时为实测串行两路加融合，不包含模型加载或查询编码，不是端到端问答延迟。参数、资源与全部数字见完整记录。

199 项回归通过，新增 21 项覆盖科学字符与有符号数值、手算 BM25、重复查询词、零分排除、坏索引/profile 拒绝、RRF 去重与同分规则、预留查询保护、门槛选择及分数边界。Ruff/格式检查、依赖与输入指纹、忽略规则及凭据模式检查见 [工程验收](Q06_5G_VALIDATION.json)。

[独立回放](Q06_5G_REPLAY.json)重新加载关键词索引和 profile，三路全部分数、排名、指标与冻结快照完全一致；公开已选 profile 使用冻结查询向量的前十检查通过。[真实运行检查](Q06_5G_RUNTIME.json)在 Qwen/MPS FP16 上重编码 D01/D03，经 `Retriever.search` 得到与快照一致的前十 chunk ID 及顺序，输出标为 `score_kind=rrf`。

## 复现与显式使用

仓库根目录、现有锁定环境和本地 F/E 产物下运行，不安装依赖、不联网调用模型接口：

```sh
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065g run
```

本轮已选 retrieval run：`output/hybrid_runs/20261007T145204-4e966c7c1ded4930a77f4e417934880c`。重跑写新目录；完整快照与 lexical 索引均被 Git 忽略，小型审计记录保留在 docs。

```sh
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065g replay \
  --candidate output/hybrid_runs/20261007T145204-4e966c7c1ded4930a77f4e417934880c

HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLBACKEND=Agg \
  MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  uv run --locked python -m scripts.validate_q065g runtime --device mps \
  --candidate output/hybrid_runs/20261007T145204-4e966c7c1ded4930a77f4e417934880c
```

在应用中显式使用 raw retrieval：

```python
from config.settings import configure_paths, settings
from src.knowledge_base.retriever import Retriever

settings.EMBEDDING_PROFILE = "config/q065e_embedding.json"
configure_paths(index_dir="output/indexes/20261007T050945-4456434906334000aac1efefcb869097")
retriever = Retriever(
    retrieval_profile="output/hybrid_runs/20261007T145204-4e966c7c1ded4930a77f4e417934880c/retrieval_profile.json"
)
results = retriever.search("查询问题", top_k=10)
```

不传 `retrieval_profile` 时保留原 Dense/旧配置行为。profile 仅用于原始检索，结果数量不得超过冻结的每路窗口 50；不会套用旧余弦阈值。显式 profile 的 `retrieve_relevant_context` 暂时拒绝调用，避免把 BM25/RRF 分数当作余弦值。上下文预算及证据选择留给 I；当前问答主入口继续使用原配置。
