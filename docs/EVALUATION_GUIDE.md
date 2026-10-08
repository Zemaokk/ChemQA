# ChemQA 评估与回放说明

日期：2026-10-08。本指南区分已有证据、只读核验、历史实验再现及新的评估活动；不启动真实生成。

## 1. 当前评估版本

| 版本/阶段 | 样本与用途 | 当前状态 |
| --- | --- | --- |
| Q10-A | 20开发题+6预留题，来源/规则冻结 | 原始版本保留，人工身份字段未填造 |
| Q06.5-B | 原20开发题，各1次Flash非思考生成 | 历史接口/生成基线，不与Q10-B合并 |
| E/G/H/I | 原20开发查询，其中18题参与正例跨度宏平均 | 开发配置选择与失败分析，不能当独立测试 |
| Q10-B | 34开发诊断题+原6预留题；预留6题×5方案×3次 | 90次正常生成，用户指定的助手评审完成；预留已消费 |

Q10-B新增D21–D34来自已有开发文献，不增加独立论文样本。开发和预留按标注文献组分离，但作者可见，不是盲测。标注逐字来源验证与领域语义复核是两件事。原数据的人工状态仍为pending；新助手覆盖层真实记录其身份，不能把pending解释成未做助手评审，也不能反过来声称独立研究者确认。

## 2. 先阅读已有结果

| 问题 | 记录 |
| --- | --- |
| 冻结了什么模型、提示、预算与重复规则 | [Q10-B协议](../config/q10b_protocol.json)、[执行记录](Q10B_EVALUATION.md) |
| 每方案执行状态、返回usage和API计时 | [原工程汇总](Q10B_RESULTS.json)、[执行核验](Q10B_VALIDATION.json) |
| 40题标注是否有原文支持 | [助手标注覆盖层](Q10B_EXPERT_ANNOTATIONS.json) |
| 90份回答的分数和额外错误 | [助手评分覆盖层](Q10B_EXPERT_ANSWERS.json) |
| 科学结果、歧义与采用决定 | [评审报告](Q10B_EXPERT_REVIEW.md)、[结构化汇总](Q10B_EXPERT_RESULTS.json) |
| 当前配置/回退绑定哪些资产 | [J manifest](../config/q065j_runtime.json)、[J收尾](Q06_5J_CLOSEOUT.json) |

原工程汇总中的 `scientific_quality_scores=null`表示生成阶段尚未评分，并非本次助手评分丢失；本次另建版本化覆盖层，不覆盖冻结答案或原协议。其每行绑定原JSON及answer的SHA-256、question/arm/repetition和评分理由。

当前核心要点宏平均：Direct 15.28%、BM25 77.78%、Dense/H/I均100%。满分只覆盖冻结要点，不覆盖整份答案的额外主张。分维度评价与公式/条件错误见评审报告；不能把标记映射率、要点得分或接口成功率统一写成“准确率”。三次重复是同一题的生成变化，不是18个独立问题。R05接受范围有歧义，排除该题后也未区分三个Qwen候选的要点得分。

## 3. 不生成答案的来源核验

以下命令校验题库文件哈希、源PDF身份、页码及原文字符区间，不重新编码预留查询或请求生成接口；需要本地原PDF：

```sh
uv run --locked python -m scripts.validate_q10a \
  --dataset-dir evaluation/q10b --report /tmp/chemqa-q10b-source-check.json
```

该脚本名称保留Q10-A，`--dataset-dir`允许校验Q10-B版本。来源核验通过不自动批准语义标签，不会更改人工身份字段。

模型/索引资产齐全时，J文件完整性核验：

```sh
uv run --locked python main.py --runtime-profile legacy --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank_diverse --check-runtime
```

这只检查冻结文件，不重新检索，也不证明未来第三方模型输出可逐字复现。

## 4. 回放已有预览与开发结果

Q10-B预览位于忽略的本地目录，不随源码快照提供。目录齐全时：

```sh
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q10b replay \
  --candidate output/q10b_previews/20261008T003102-7049b4e82a524fcabd2ff19c61501b35
```

该命令核对30份预览的输入、提示和预算，不排序预留题，不发送HTTP。它会重写固定的 `docs/Q10B_REPLAY.json`；原冻结环境下应得到相同内容，修改后需检查差异，不能把漂移报告覆盖后继续冒充同一实验。原目录缺失时应恢复获准归档的资产，不用新预留排序替代旧快照。

Q10-A开发排名可用保存的查询向量回放；原目录从 [Q10-A基线记录](Q10A_BASELINE.json)读取，再传 `scripts.validate_q10a --replay`。E/F/G/H/I详细命令和需要的源目录见各阶段记录；有的入口重新编码**开发**查询，有的只使用冻结向量，不应混称逐字请求复现。

`validate_q10b report`读取原生成记录、核对90份输入并生成新的人工评审包，同时写固定工程汇总；它不会合并助手评分覆盖层，不是当前科学评分入口。无需为日常阅读重复执行。旧批量脚本的10题和热力图也不替代正式协议。

## 5. 指标解释

- **检索**：按PDF身份/字符区间求锚点覆盖。开发正例18题作宏平均；片段重叠不重复计分。标签非穷尽，未标注片段不自动等于不相关，不报告以此计算的传统precision/nDCG。
- **生成要点**：每项0/1/2，归一化为 `sum(scores)/(2*n_points)`；先平均同题三次，再平均六题。条件/单位、体系边界、证据支持、引用对应分别报告，不合成总科学分。
- **额外错误**：要点正确也可能有错误公式、负号、条件绑定或证据缺失断言，逐条记录。未穷举所有事实主张，claim support precision与claim citation recall保持null。
- **引用结构**：`marker_resolution_rate`是可映射标记/全部捕获标记；`context_chunk_utilization`和document utilization为上下文使用率。分母零为null，不补100%。旧 `citation_coverage`仅兼容别名，不表示科学覆盖。
- **执行**：`success`、`no_evidence`、`failed`、`truncated`分开；无显式历史状态为unverified。空证据本地说明不算模型生成成功。
- **不足判断**：六个预留题均可回答。BM25 R03在其实际上下文中有界拒答可单独评价，不能推断全库无答案或整体拒答识别能力。
- **成本/速度**：记录供应商usage，缺价格时金额null。API延迟不含检索；F存储基准不含模型加载/查询编码，二者不能当端到端速度对照。

## 6. 后续评估纪律

Q10-B预留检索/生成已有一次性消耗标记：`output/Q10B_RESERVE_CONSUMED.json`与`output/Q10B_GENERATION_STARTED.json`。不删除标记重跑，不挑选重复，不补跑出更好答案。历史授权只对应已批准预览输入，不自动授权新的第三方外发。

如果要修复公式、条件绑定或更换模型/提示/预算，应新建开发轮次，冻结新协议并准备未使用验收问题。尽可能让独立领域研究者审核题目与争议，先明确R05这类题目的接受范围，再确定分母。当前保留默认的决定不表示旧MiniLM质量优于Qwen；需要同条件对照才能比较。

本轮离线工程验证使用模拟HTTP的回归测试，不消耗真实生成额度。当前验证范围见 [Q11验收](Q11_VALIDATION.json)。

## R01 与旧评估的边界

当前产品问答采用 R01 提示/检查；Q10-B 脚本仍保留原提示以重放旧实验，不代表 R01。原90份答案与评分不改写，不以其重新调参后的分数作为独立验收。新合成测试只验证工程约束；新的科学比较需独立未用问题。见 [R01说明](R01_ANSWER_RELIABILITY.md)。
