# 冻结回答的证据对应示例

日期：2026-10-08。此例从Q10-B已有回答节选，不重新生成，不代表完整回答均正确，也不是新验收题。选择理由是展示数值、单位、来源和原始记录的连接；不是按此一例判断方案优劣。

## 问题与原回答节选

**R06 / hybrid_rerank_diverse / repetition 1**：For Shi (2025) Au-catalyzed ethylene-glycol/methanol cross-coupling to lactic acid, report the current density, productivity and FE.

下面三行逐字取自原回答，只省略原回答其他段落：

1. **电流密度：** 在单室电解池中，以 100 mA cm⁻² 的恒电流进行 EG 与 MeOH 交叉偶联制 LA。
2. **LA productivity：** 268.1 μmol cm⁻² h⁻¹。
3. **FE：** 28.7%。

原回答分别以完整 `[Ref chunk_id]`标记引用摘要/结论；后处理可生成数字引用，但完整映射和实际上下文保留在 `answer.evidence.json` 或冻结生成记录。这里不把要点得分当整份答案正确率。

## 来源、页码与原文

来源：[本地原PDF](<../data/raw_papers/Shi 等 - 2025 - Electrocatalytic ethylene glycol to long-chain C3+ α-hydroxycarboxylic acids via cross-coupling with primary alcohols.pdf>)。文献身份：`doc_8cb9cc642b939bc5d4a3dd69c06e9918bd80f485142dab4e3385d94ddccab903`。

题库锚点在PDF物理第1页，提取文本字符区间 `[1214, 1343)`：

> achieving a
> high LA productivity of 268.1 μmol cm−2 h−1 with a Faradaic efficiency of 28.7% at a constant current of 100 mA cm−2.

本份模型输入中对应的两个实际证据片段：

| chunk_id | PDF物理页 | 作用 |
| --- | --- | --- |
| `chunk_cf3586f53ffe64221b9ff471dccaf77fba8e251e817d31cce38093e30fb14358` | 1 | 摘要中的同组指标 |
| `chunk_c732d1ef46e6e0bc59132543b0e3c4dae5e704cb3c7e9ed77c743454a1aad33c` | 10 | 结论中的同组指标 |

摘要/结论中的三项数值属于Au催化EG/MeOH制LA，不能换成收率或PET瓶实验的累计面产量；最终优化的完整条件须核查正文，不能把其他片段中的中间条件直接贴到该结果。

## 如何核对

1. 查看 [冻结题目](../evaluation/q10b/reserve.json)中R06的原文锚点和指标边界。
2. 本机原始回答：[R06原记录](../output/q10b_generation/20261008T003314-1d25d4f7565e4fd7b1fab1a7512ae66f/R06-hybrid_rerank_diverse-r1.json)，JSON文件SHA-256为 `29d82e81d6831c77e525712aaa43ddfc1f1cef8d9bec08379ade4cc8ca217d7a`。`answer`是原回答，`evidence`是本次输入，`generation_input`保存提示与预算。
3. 查看 [助手逐答案评分](Q10B_EXPERT_ANSWERS.json)中同question/arm/repetition，核对原记录/答案哈希及观察项。
4. 回到PDF原页核查符号、上下标、工况与指标定义。页内字符串定位不是版面高亮，也不验证所有化学公式均抽取正确。

`output/`中的原始回答不在源码快照中，PDF也须另行提供；链接在本机资产齐全时可用。缺失时可阅读源码内的锚点/评分，但不能声称已从源码包恢复完整实验。全局质量结论仍以 [完整评审](Q10B_EXPERT_REVIEW.md)为准。
