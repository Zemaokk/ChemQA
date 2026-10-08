# Q06.5-H：固定候选重排

日期：2026-10-08。状态：已完成工程验收，候选流程启用重排；产品默认仍不切换，下一项 Q06.5-I。

## 范围与决定

在 G 已选的混合检索前 50 个候选上，比较原顺序与 Qwen3-Reranker-0.6B 重排顺序。20 个开发查询共 1,000 对输入，18 个可回答题计入召回指标，2 个范围内证据不足题不计入这些指标；6 个预留题未执行。复用 G 的查询向量、候选文本、chunk_id/doc_id 和原文位置，没有扩充候选池、重新编码 embedding 或调用生成 API。

固定门槛在运行前写入 [配置](../config/q065h_reranker.json)：完整锚点召回@10必须严格提高，字符覆盖@5与标注文献召回@10不下降，每题 50 候选的新增重排耗时中位数不超过 15 秒。不进行参数扫描。本轮全部满足，发布 `enabled: true` 的独立候选配置。该结果仅支持在本机开发候选流程采用重排，开发标注仍为 AI 草稿、待领域人工复核，不等同于科学回答准确率或泛化验证。

## 固定模型与输入

- 模型：`Qwen/Qwen3-Reranker-0.6B`，revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`，仅加载本地缓存，禁用远程代码。
- 使用缓存模型自带的完整聊天模板；system 放固定 instruction，query/document 放原始问题与原文片段。模板 SHA-256 记录在模型 manifest 中。[模型官方说明](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- 独立输入上限 1,024 tokens，包含完整模板、instruction、问题与文献。先无截断编码，再逐 token 对比模型实际预处理结果；超限或内容变化直接报错。本轮实际范围 174–632 tokens，共 554,042 tokens，超限 0、截断 0。
- batch 4；本轮 Apple M5 / 16 GB 上实际 MPS、float16。显式 CPU 使用 float32；遇到 MPS 资源问题报错，由操作者明确选择 CPU 重跑，不自动混用精度。
- 输出为 `yes logit - no logit`，排序时越高越靠前；不是概率、余弦相似度或科学可信度。同分保持 G 的原候选顺序。返回结果保留原检索分数、原排名、原文元数据与 token 数。

## 开发集结果

按题宏平均，保留既有评分口径，指标见 [完整结果](Q06_5H_FULL.json)。MRR 只观察前 10 条内的首个完整锚点。

| 指标 | G 原顺序 | H 重排 |
| --- | ---: | ---: |
| 完整锚点召回@1 | 26.85% | 60.19% |
| 完整锚点召回@5 | 51.85% | 78.70% |
| 完整锚点召回@10 | 70.37% | 85.19% |
| 字符覆盖@5 | 51.85% | 78.70% |
| 标注文献召回@10 | 94.44% | 100.00% |
| 全部锚点完整的题目比例@10 | 61.11% | 77.78% |
| 首个完整锚点 MRR@10 | 0.4568 | 0.7657 |

完整锚点召回@10提高 14.81 个百分点。改善题为 D08、D10、D15、D17，没有题在这一指标上退步。仍有 D11、D15、D16、D18 未取全标注锚点，详见 [逐题缺口](Q06_5H_FAILURES.json)。标注文献命中不代表该文献内所需片段完整。候选池完全相同，因此 @50 的完整锚点召回上限仍为 G 的 85.19%；本轮提升来自把池内已有证据提前，不能修补候选池之外的缺口。G 的语言不匹配和单篇集中风险仍需保留记录，不能据此宣称已解决。

## 本机开销与边界

模型加载耗时见完整结果；每题 50 候选重排中位数 **7.62 秒**、P95 **7.95 秒**，20 题累计 **152.47 秒**。计时包括模板检查、分批前向、分数回收和 MPS 缓存清理，不含 embedding/混合召回、预检全部模板、模型加载或生成。它是本机单次顺序运行的观测，不能作为其他设备或并发服务的延迟承诺。

进程 RSS 高水位为 1,981,038,592 bytes（约 1.85 GiB），不代表完整统一内存/GPU 分配峰值。每批清理缓存后检查 MPS driver allocation，超过 6 GiB 则失败；本轮未触发。该检查不是连续峰值采样，不能推断瞬时峰值小于 6 GiB。

## 使用与复现

本次发布目录：

```text
output/rerank_runs/20261007T235201-2192dcdcee6346d3855ff0ef7431e0c9/
```

目录中的 `run.json` 校验分数矩阵、逐题排名、模型与运行配置。它绑定 G 的 ready run；G 再绑定 F 的二进制索引与 BM25 索引。输出由 `.gitignore` 排除，仓库保留摘要和验证记录。清理本地产物后需按 C→E→F→G→H 重建对应候选。

原始检索示例（从仓库根目录运行，缓存需已存在）：

```python
from config.settings import configure_paths, settings
from src.knowledge_base.retriever import Retriever

settings.EMBEDDING_PROFILE = "config/q065e_embedding.json"
configure_paths(index_dir="output/indexes/20261007T050945-4456434906334000aac1efefcb869097")
retriever = Retriever(
    reranker_profile="output/rerank_runs/20261007T235201-2192dcdcee6346d3855ff0ef7431e0c9/reranker_profile.json"
)
hits = retriever.search("你的问题", top_k=10)
```

实际应用需可访问 MPS，或使用 CPU。每次启用重排先取固定 50 个候选，再返回所需前 k 条，k不得超过50；0条请求不编码。配置关闭时不加载重排模型，直接沿用 G。`retrieval_profile` 与 `reranker_profile` 互斥。显式候选配置只支持 raw search；`retrieve_relevant_context` 会拒绝未经校准的上下文选择，生成侧证据数量与预算交 Q06.5-I。

```bash
HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLCONFIGDIR=/private/tmp/chemqa-matplotlib MPLBACKEND=Agg \
  .venv/bin/python -m scripts.validate_q065h run --device mps

HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLCONFIGDIR=/private/tmp/chemqa-matplotlib MPLBACKEND=Agg \
  .venv/bin/python -m scripts.validate_q065h replay \
  --candidate output/rerank_runs/20261007T235201-2192dcdcee6346d3855ff0ef7431e0c9

HF_HUB_OFFLINE=1 HF_HOME=models/huggingface MPLCONFIGDIR=/private/tmp/chemqa-matplotlib MPLBACKEND=Agg \
  .venv/bin/python -m scripts.validate_q065h runtime --device mps \
  --candidate output/rerank_runs/20261007T235201-2192dcdcee6346d3855ff0ef7431e0c9
```

`run` 每次创建新目录；`replay` 验证文件及冻结分数、排名和指标，不运行模型；`runtime` 使用冻结查询向量，经公开 Retriever 原始检索入口重算 D01，并比较真实重排排名与分数。

## 验证与回退

212 项回归通过（新增 13 项），涵盖模板超限、等长 token 篡改、非有限分数、重复/超量候选、稳定同分、采纳门槛、profile 校验和原始分数隔离。Ruff、格式、Git diff 与锁定离线环境检查通过；当前源码密钥模式审计无发现。

[冻结回放](Q06_5H_REPLAY.json) 的全部排名与指标一致；[真实 MPS 检查](Q06_5H_RUNTIME.json) 的公开入口 D01 前10一致、重复模型分数最大差为0，未经校准的上下文阈值被拒绝。[验收汇总](Q06_5H_VALIDATION.json) 记录文件哈希与来源保持情况。旧 JSON、E/F/G 候选、默认设置和依赖均保留；回退到 G 使用原 `retrieval_profile`，回退到正式默认则不传显式 profile。没有新的网络生成请求或预留题执行。
