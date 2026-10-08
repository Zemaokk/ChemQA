# Q06.5-J：运行冻结与回退

## 状态与验收边界

2026-10-08：工程冻结、显式回退和本轮采用决定已完成。用户指定由助手专家评审Q10-B，现已核查40题与90份回答，见 [评审报告](Q10B_EXPERT_REVIEW.md)。三种Qwen候选核心要点均完整，但存在公式补写和条件错配；小规模、非独立评审不支持质量赢家或切换默认。决定保留兼容默认和显式候选，不再以等待人工填表作为本轮阻塞；不宣称独立研究者认可。

本轮只固定已有实现及已评估参数，没有新模型、检索调参、预留题重跑或 API 请求。Q11 后续统一公开文档。

## 配置决定

| 项目 | 冻结内容 | 决定及理由 |
| --- | --- | --- |
| 当前默认检索/回退 | MiniLM，revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`；旧 JSON 索引；top 10、cosine ≥0.5 | 保留兼容配置；不代表科学质量优于候选 |
| 生成 | Paratera `https://llmapi.paratera.com/v1`，`DeepSeek-V4-Flash`，thinking disabled，temperature 0.3，max_tokens 4096，stream false | 沿用 B/Q10-B 已调用配置；未比较其他模型或思考模式，不能声称最优 |
| 请求控制 | 冻结入口单次尝试；连接 10 秒、读取 120 秒 | 与 Q10-B 单次请求约定一致；无 profile 的兼容入口仍遵循环境配置 |
| 显式候选 `hybrid_rerank` | E Qwen embedding，F NumPy/SQLite，G BM25/RRF，H Qwen reranker，Q10-B common context policy | 保留已比较方案；不因结构引用解析率 1.0 就认定科学支持正确 |
| 实验 `hybrid_rerank_diverse` | 同上，使用原 I policy | 开发集完整锚点召回由 H 的 85.19% 降至 82.41%，D08 受每篇上限影响；不采用为默认 |
| 解析 | 保留 PyMuPDF | D 的字符跨度、图式及 OCR 迁移验收未满足；不全库重解析 |
| 未采用 | FAISS；Docling 全库迁移；未实测替代模型/思考模式 | FAISS/PyTorch OpenMP 冲突；其余缺乏迁移或对照证据 |

候选 embedding revision 为 `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，1024 维，512-token 页内窗口、64-token 目标重叠。reranker revision 为 `e61197ed45024b0ed8a2d74b80b4d909f1255473`，完整模板 1024-token 上限、batch 4。G 每路 50、BM25 k1=1.2/b=0.75、RRF k=60 等权，H 只重排固定 50 候选。

common context policy 从冻结的 Q10-B 协议原样导出至 `config/q065j_context.json`：最多 10 片段、每篇 10，跨度阈值 1.0；完整请求保守字节预算 32000、输出 4096、预留 1024、总额 40000。I 保持每篇 6、跨度阈值 0.5。均保持已有排序、整片段选择、不扩展相邻片段。这不是供应商精确 token 计数。旧默认没有这一候选预算机制，未宣称具有同等超长输入保护。

## 冻结文件与可复现入口

`config/q065j_runtime.json` 记录三套 profile、生成参数、采用状态及 SHA-256：主程序、所有 src Python 源码、settings/prompts、pyproject/uv.lock、Q10-B 协议及结果、旧索引/片段，以及候选 F/G/H/BM25 索引和 manifest。密钥仅从环境或忽略的 `.env` 读取，不进入 manifest。显式运行结果保存 profile 名称、manifest SHA 和采用状态。

环境为 Python 3.12.13；锁定安装包括 Sentence Transformers 6.1.0、Transformers 5.19.0、PyTorch 2.14.1、NumPy 2.5.3、PyMuPDF 1.28.2、requests 2.34.2。依赖以 `uv.lock` 为准，使用 `uv sync --locked --offline` 验证已有缓存，首次安装可去掉 `--offline`。

在项目根目录离线检查，不加载模型、不调用 API：

```sh
.venv/bin/python main.py --runtime-profile legacy --check-runtime
.venv/bin/python main.py --runtime-profile hybrid_rerank --check-runtime
.venv/bin/python main.py --runtime-profile hybrid_rerank_diverse --check-runtime
```

检查通过后，可显式选用已冻结候选（实际提问会调用配置的平台）：

```sh
.venv/bin/python main.py --runtime-profile hybrid_rerank --output-dir output/manual-candidate
```

可执行回退入口如下；无需删除、覆盖或重建候选索引：

```sh
.venv/bin/python main.py --runtime-profile legacy --check-runtime
.venv/bin/python main.py --runtime-profile legacy --output-dir output/manual-rollback
```

该入口显式恢复旧 MiniLM/revision、JSON 索引、processed 目录及 top 10，清空候选 embedding profile，并恢复冻结生成参数；保留外部密钥。它会覆盖相关环境运行参数，拒绝同时传入 `--index-dir`，拒绝本地同名模型覆盖固定 Hub revision。缺失/漂移先停止，不能静默退到其他模型或索引。无 `--runtime-profile` 的入口仍兼容原有环境配置，不声称属于冻结运行。

## 限制与后续

- 模型权重、候选索引及实验原始产物留在本地忽略目录，源码 checkout 本身不是完整备份。迁移须保留这些目录和模型缓存；G/H 的旧 profile 含原绝对路径，搬迁后需明确重新绑定并验证，不能直接保证跨机器运行。
- Hub revision 固定检索模型；第三方生成模型只有平台别名，供应商可能更新权重，无法冻结其内部 revision。运行参数/产物可核查不等于远程生成逐字确定。
- 6 个原预留问题均可回答，规模很小且作者可见；14 个新增开发题是派生诊断题。Q10-B 不构成盲测或不足证据场景验收，API 延迟不含检索，价格未知，不能报告成本优势或科学质量排序。
- Q10-B本次助手评审已完成，原人工表保持空白。本轮决定保留默认；若以后要升级，先修复已定位缺陷、准备新验收题，并补足旧默认同条件对照。已消费的预留集不能用于调参。

## 验证

验证结果记录于 `docs/Q06_5J_VALIDATION.json`：三个 profile 的完整离线校验、回退实际模型/索引加载、回归、格式及锁定依赖检查。新增助手评审不替代独立领域研究者确认；详见评审覆盖层及本次验证记录。本轮没有提交 Git。

## 2026-10-08 收尾复核

本轮完成J的最终核验，不更换候选、提示、模型或默认。三套profile绑定文件再次通过；显式legacy实际加载MiniLM固定revision与26,025片段，并对通用烟测问题返回3条结果，生成请求参数与Q10-B协议相同。检查期间禁用网络请求，没有生成调用或预留题重排。详见 [J收尾记录](Q06_5J_CLOSEOUT.json)。

J本轮验收完成，决定仍为保留兼容默认和显式候选，不认定科学赢家。日常操作、自己的索引构建及迁移边界交由 [运行手册](RUNBOOK.md)；对外实验表述见 [技术报告](TECHNICAL_REPORT.md)。这不是重新评估Q10-B或独立人工批准。
