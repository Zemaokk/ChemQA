# Q10-A 开发题领域复核清单

本清单由冻结 dev.json 派生，便于人工阅读；不是已通过的人工评分。26 题的领域复核目前全部 pending。请核对事实、条件、单位、反应体系和原文证据层级；分歧保留到裁决。修改权威 JSON 时建立新版本与 manifest，并重跑基线，不直接覆盖已冻结结果。预留题本清单不展开。

复核记录需填写复核者标识、日期、核查来源、同意/分歧及理由。逐字核查不能代替领域判断；尤其检查“摘要未给出”是否被误扩展为“全文不存在”。

## D01 · single_fact

Kawajiri（2025）的苄醇电氧化中，TFE 扮演什么角色，主要帮助处理哪类底物？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: TFE 是氢原子转移（HAT）介体。（证据 e1）

- p2: 帮助氧化难以在电极表面直接氧化的缺电子底物。（证据 e1）


边界：

- 不能把 TFE 仅称为惰性溶剂，也不能将本文转写为苯甲醇加氢。


**e1** · Kawajiri et al. (2025) · DOI `10.1021/acs.orglett.5c01138` · PDF 物理页 1 · 字符 [390, 595)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Kawajiri 等 - 2025 - Electrochemical oxidation of benzyl alcohols via hydrogen atom transfer mediated by 2,2,2-trifluoroethanol.pdf>)


```text
We found that trifluoroethanol plays a role as a hydrogen atom transfer (HAT)
mediator, enabling the oxidation of electron-deficient substrates that are difficult
to directly oxidize on electrode surfaces.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D02 · conditions

Kawajiri（2025）氧化 4-甲氧基苄醇的标准电解条件是什么？列出电极、电流、溶剂和主要添加物用量。

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 0.5 mmol 底物；n-Bu4N·BF4 0.1 equiv；NaOMe 0.5 equiv（28% MeOH 溶液）。（证据 e1）

- p2: MeCN 7 mL 与 TFE 0.7 mL；室温、恒电流 20 mA。（证据 e1）

- p3: 不分隔电解池；GC 阳极和 Pt 片阴极；该条件下报告 93% 收率。（证据 e1）


边界：

- 20 mA 是电流，不得改写为 20 mA cm−2。

- 不能把 93% 收率称为法拉第效率。


**e1** · Kawajiri et al. (2025) · DOI `10.1021/acs.orglett.5c01138` · PDF 物理页 2 · 字符 [251, 788)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Kawajiri 等 - 2025 - Electrochemical oxidation of benzyl alcohols via hydrogen atom transfer mediated by 2,2,2-trifluoroethanol.pdf>)


```text
4-Methoxybenzyl
alcohol (1a) was used as the model substrate on a 0.5 mmol
scale. The standard conditions are as follows: 1a and n-Bu4N·
BF4 (0.1 equiv) and NaOMe (0.5 equiv, 28% in MeOH
solution) were added to a cosolvent of acetonitrile (7 mL) and
TFE (0.7 mL). Electrolysis of this mixture was conducted at a
constant current of 20 mA at room temperature. An undivided
cell setup was used with a glassy carbon (GC) anode and a
platinum plate (Pt) cathode. As a result, 4-methoxybenzalde-
hyde (2a) was obtained in 93% yield (entry 1).
```


人工复核者/日期：待填写；判断与理由：待填写。

## D03 · single_fact

In Lu (2025), which reagent supplies the primary alkyl radicals, and are additional oxidants or supporting electrolytes required?

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 季铵羧酸盐提供烷基自由基。（证据 e1）

- p2: 该体系不需要额外氧化剂或电解质。（证据 e1）


边界：

- 不需要额外电解质不等于体系不存在离子。


**e1** · Lu et al. (2025) · DOI `10.1002/anie.202506639` · PDF 物理页 1 · 字符 [438, 589)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Lu 等 - 2025 - Metal‐free electrochemistry‐driven decarboxylative primary alkyl‐alkoxylation of olefins.pdf>)


```text
The reaction employs quaternary
ammonium carboxylates as the source of alkyl radicals
and does not require additional oxidizing agents or
electrolytes.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D04 · mechanism

Lu（2025）的烯烃脱羧烷基-烷氧基化中，羧酸根和烯烃哪一个先发生阳极氧化，之后怎样形成自由基？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 作者的初步机理研究认为羧酸根氧化电位低于烯烃，先被阳极氧化。（证据 e1）

- p2: 随后脱羧形成烷基自由基；应保留初步机理研究的证据层级。（证据 e1）


边界：

- 不得称为已直接观测了所有机理中间体。


**e1** · Lu et al. (2025) · DOI `10.1002/anie.202506639` · PDF 物理页 1 · 字符 [1054, 1367)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Lu 等 - 2025 - Metal‐free electrochemistry‐driven decarboxylative primary alkyl‐alkoxylation of olefins.pdf>)


```text
Preliminary mechanis-
tic studies have demonstrated that the reaction is enabled
by the lower oxidation potential of the carboxylate anion
compared to that of the oleﬁn. The anodic oxidation of
the carboxylate anion occurs prior to the oxidation of
the oleﬁn, followed by decarboxylation to obtain alkyl
radicals.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D05 · mechanism

How does Song (2025) promote Ni-H formation, and what roles does the proton source play in the proposed selectivity control?

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 采用带悬挂胺基的双功能配体促进 Ni-H 形成。（证据 e1）

- p2: 计算研究提出质子源可通过氢键、直接质子化悬挂胺或促进质子脱金属过程调控选择性。（证据 e2）


边界：

- 不能把计算提出的作用一律说成直接实验观测，也不能把策略说成避免 Ni-H 形成。


**e1** · Song et al. (2025) · DOI `10.1021/jacs.5c03821` · PDF 物理页 1 · 字符 [877, 1007)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Song 等 - 2025 - Proton-modulated nickel hydride electrocatalysis for the hydrogenation of unsaturated bonds and olefin isomerization.pdf>)


```text
Here, we
pursued an alternative approach by designing a bifunctional ligand
with a pendant amine moiety to promote Ni−H formation.
```


**e2** · Song et al. (2025) · DOI `10.1021/jacs.5c03821` · PDF 物理页 1 · 字符 [1495, 1729)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Song 等 - 2025 - Proton-modulated nickel hydride electrocatalysis for the hydrogenation of unsaturated bonds and olefin isomerization.pdf>)


```text
Computational studies revealed the crucial,
noninnocent role of the proton source in modulating metal hydride selectivity, either through hydrogen bonding, direct protonation
of the pendant amine, or facilitation of protodemetalation.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D06 · single_fact

Which starting-material classes and heterocycle are involved in Huang (2025) cathodic oxygen-reduction-enabled Rh-catalyzed (5+1) annulation?

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 烯基苯酚与烯烃反应。（证据 e1）

- p2: 生成有价值的 2-取代 2H-色烯；Rh 催化形式 (5+1) 环化。（证据 e1）


边界：

- 不能用引言中常见的炔烃环化代替本文烯烃体系。


**e1** · Huang et al. (2025) · DOI `10.1038/s41467-025-59405-x` · PDF 物理页 1 · 字符 [452, 658)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Huang 等 - 2025 - Cathodic oxygen reduction-enabled rhodium-catalyzed (5 + 1) C–HO–H annulation inspired by fuel cells.pdf>)


```text
In this study, we report a cathodic oxygen
reduction-enabled rhodium catalyzed (5 + 1) annulation reaction between
readily available alkenylphenols and alkenes, yielding valuable 2-substituted
2H-chromenes.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D07 · system_boundary

Huang（2025）的 Rh 环化是否通过阳极直接氧化催化剂完成再生？分别说明阳极和阴极的作用。

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 使用牺牲阳极以保护底物避免过氧化。（证据 e1）

- p2: 阴极还原氧，与 Rh(I) 再生过程耦合；区别于阳极直接氧化催化剂的路线。（证据 e1）


边界：

- 不能将阴极氧还原混同为阴极有机底物加氢。


**e1** · Huang et al. (2025) · DOI `10.1038/s41467-025-59405-x` · PDF 物理页 1 · 字符 [659, 916)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Huang 等 - 2025 - Cathodic oxygen reduction-enabled rhodium-catalyzed (5 + 1) C–HO–H annulation inspired by fuel cells.pdf>)


```text
Unlike existing methods that involve direct oxidation of cata-
lysts at the anode, our protocol uses a sacriﬁcial anode to protect the substrate
from overoxidation, while the cathode reduces oxygen, coupling with the RhI.
to regenerate the rhodium catalyst.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D08 · numeric

Liu（2025）的 NiFe-sc-PBA 在 500 和 1000 mA cm−2 下分别需要多少电位？说明参比标尺，勿与整槽电压混用。

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 500 mA cm−2 对应 1.484 V；1000 mA cm−2 对应 1.625 V。（证据 e1）

- p2: 文中默认电位相对 RHE；这些是电极电位，不是整槽电压。（证据 e2, e1）


边界：

- 不能交换两组数值，也不能将 RHE 改为 Ag/AgCl。


**e1** · Liu et al. (2025) · DOI `10.1038/s41467-025-58203-9` · PDF 物理页 2 · 字符 [4015, 4137)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf>)


```text
achieving low applied potentials of 1.484 and 1.625 V to reach current
densities (j) of 500 and 1000 mA cm−2,respectively,
```


**e2** · Liu et al. (2025) · DOI `10.1038/s41467-025-58203-9` · PDF 物理页 1 · 字符 [1998, 2096)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf>)


```text
1.23 V versus reversible hydrogen electrode, vs.
RHE; all potentials are vs. RHE if not mentioned)
```


人工复核者/日期：待填写；判断与理由：待填写。

## D09 · numeric

For Liu (2025) NiFe-sc-PBA coupled flow electrolysis, what switching current densities and continuous operating duration are reported?

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 耦合流动体系在可切换的 1.0 或 1.5 A cm−2 下运行。（证据 e1）

- p2: 报告连续超过 500 h 无性能衰减；这是本文给定体系和条件下的结果。（证据 e1）


边界：

- 不能用独立电极 50 h 结果替代耦合系统 500 h，也不能外推为任意电流下永久稳定。


**e1** · Liu et al. (2025) · DOI `10.1038/s41467-025-58203-9` · PDF 物理页 1 · 字符 [1596, 1765)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf>)


```text
The coupled system can continuously
operate at stepwise ampere-level current densities (switchable 1.0 or
1.5 A cm−2) for over 500 hours without performance degradation.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D10 · mechanism

Liu（2025）如何解释乙二醇抑制 NiFe-sc-PBA 重构？区分结构表征和分子动力学各支持什么。

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 原位/操作中表征支持 EG 氧化期间 Ni(II) 位点稳定。（证据 e1）

- p2: MD 显示 EG 倾向聚集于表面，作者据此解释对 OH 诱导重构的抑制。（证据 e1）


边界：

- MD 的表面富集不能直接当作真实质子转移、完整电子转移路径或任意底物下稳定性的证明。


**e1** · Liu et al. (2025) · DOI `10.1038/s41467-025-58203-9` · PDF 物理页 1 · 字符 [1054, 1344)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf>)


```text
Our in situ/operando characterizations demonstrate
the robustness of Ni(II) sites during EG electrooxidation. Molecular dynamics
simulations further illustrate that EG molecule tends to accumulate on the
NiFe-sc-PBA surface, preventing hydroxyl-induced reconstruction in alkaline
solutions.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D11 · numeric

Mi（2025）的甲苯电氧化中，低电流与流动体系分别报告了什么苯甲醛法拉第效率和电流密度？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 25 mA cm−2 下苯甲醛 FE 为 86 ± 1%。（证据 e1）

- p2: 流动体系在 200 mA cm−2 下 FE 为 60 ± 4%。（证据 e1）


边界：

- 不能把 86% 和 200 mA cm−2 拼成同一工况；需保留不确定度。


**e1** · Mi et al. (2025) · DOI `10.1038/s41467-025-58733-2` · PDF 物理页 1 · 字符 [854, 1258)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Mi 等 - 2025 - CoOx clusters-decorated IrO2 electrocatalyst activates NO3- mediator for benzylic C-H activation.pdf>)


```text
Our
strategy is demonstrated through the selective oxidation of toluene to ben-
zaldehyde with high Faradaic efﬁciency of 86( ±1)% at 25 mA/cm2, a factor of >3
times higher than the bare electrocatalyst. The electrocatalyst:mediator
assembly is operated stably for 100 h, with minimal decline in performance.
When translated into a ﬂow system, a Faradaic efﬁciency of 60( ±4)% at
200 mA/cm2 was achieved.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D12 · numeric

In Lin (2025), what propylene oxide production rate and stability duration are reported for the Ag/V liquid-free MEA?

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: Ag/V 集成 MEA 的 PO 产率为 227 μmol h−1。（证据 e1）

- p2: 该产率维持 78 h；此数值未按电极面积归一化。（证据 e1）


边界：

- 不得把 μmol h−1 改为 μmol cm−2 h−1。


**e1** · Lin et al. (2025) · DOI `10.1038/s41467-025-58486-y` · PDF 物理页 1 · 字符 [1088, 1234)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Lin 等 - 2025 - V activated electro-epoxidation catalyst in membrane electrode assembly system for the production of propylene oxide.pdf>)


```text
The MEA reactor, integrated with
the developed Ag/V catalyst, can maintain a stable production rate of PO at 227
μmol/h over a period of 78 hours.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D13 · numeric

Han（2025）用 LM-PdCu 脉冲电催化升级 PET 制乙醇酸，报告了哪些 FE、面产率和循环稳定性指标？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: GA FE >92%，适用文中报告的宽电位窗口。（证据 e1）

- p2: 面产率达 0.475 mmol cm−2 h−1；循环稳定性超过 20 次。（证据 e1）


边界：

- 超过 20 次循环不能改写为连续超过 20 h；FE 与产率分开报告。


**e1** · Han et al. (2025) · DOI `10.1038/s41467-025-58813-3` · PDF 物理页 1 · 字符 [1126, 1334)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Han 等 - 2025 - Pulsed electrosynthesis of glycolic acid through polyethylene terephthalate upcycling over a mesoporous PdCu catalyst.pdf>)


```text
This strategy thus delivers GA Faraday efﬁciency of >92% in wide potential
windows, yield rate of reaching 0.475 mmol cm–2 h–1, and cycling stability of
exceeding 20 cycles for electrocatalytic PET upcycling.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D14 · numeric

Fan（2025）Mo-Ni2P@Ni12P5 双电极流动槽的电流密度、己二酸收率及 H2 法拉第效率各是多少？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 双电极流动槽电流密度 >230 mA cm−2。（证据 e1）

- p2: 己二酸收率 85.7%；H2 FE 100%，二者是不同指标。（证据 e1）


边界：

- 85.7% 不得改为己二酸 FE；100% 不能套用为己二酸收率。


**e1** · Fan et al. (2025) · DOI `10.1002/adma.202502523` · PDF 物理页 1 · 字符 [1434, 1593)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Fan 等 - 2025 - Doping Mo triggers charge distribution optimization and P vacancy of Ni2 P@Ni12 P5 heterojunction for industrial electrocatalytic production of adipic acid and H2.pdf>)


```text
Consequently,
a two-electrode ﬂow electrolyzer achieves industrial current density (>230 mA
cm−2) with 85.7% AA yield, 100% Faradaic eﬃciency of H2 production.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D15 · system_boundary

Li（2025）配对 CO2 还原和甲醛脱氢的甲酸盐 FE 约 190%，它对应哪两个半反应，能否当成单一阴极 FE？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: MEA 中阴极为 Rh/In2O3 上 CO2 还原，阳极为 CuAg/CF 上甲醛氧化脱氢，两极协同产甲酸盐。（证据 e1）

- p2: 约 190% 是配对/双极甲酸盐指标，报告电压区间 2.1–2.5 V；不是单一阴极超过 100% 的 FE。（证据 e2, e1）


边界：

- 不得把配对指标当成单电极 FE，也不能把阳极产氢误写到阴极。


**e1** · Li et al. (2025) · DOI `10.1038/s41467-025-60008-9` · PDF 物理页 5 · 字符 [1977, 2349)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Ampere-level co-electrosynthesis of formate from CO2 reduction paired with formaldehyde dehydrogenation reactions.pdf>)


```text
We are thus motivated to design a reaction system by pairing
CO2RR with FOR that driven by the EOD mechanism (CO2RR//FOR),
anticipating a dual production of HCOO−at both poles of the elec-
trolyzer with high current densities under low cell voltages (Fig. 4a).
CO2RR//FOR was performed in an MEA cell by using CuAg/CF as the
anode and the Rh/In2O3 catalyst as the cathode.
```


**e2** · Li et al. (2025) · DOI `10.1038/s41467-025-60008-9` · PDF 物理页 5 · 字符 [3141, 3456)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Ampere-level co-electrosynthesis of formate from CO2 reduction paired with formaldehyde dehydrogenation reactions.pdf>)


```text
On the other hand, the CO2RR//FOR
system can achieve HCOO−FEs of ~190% at cell voltages ranging from
2.1 to 2.5 V (Fig. 4c and Supplementary Fig. 27). A peak HCOO−for-
mation rate is ramped up to 52.0 mmol h−1 cm−2 (Fig. 4d), along with
pure H2 simultaneously produced at the anode with a rate of
17.9 mmol h−1 cm−2
```


人工复核者/日期：待填写；判断与理由：待填写。

## D16 · comparison

比较 Jiang（2025）的 NiOOH 乙二醇氧化与 Liu（2025）的 Ni(II) PBA 路线：各自如何讨论析氧与重构？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: Jiang 研究 β-NiMxOOH（M=Ni,Co,Fe,Cu），原位方法定量跟踪 OER 等副反应。（证据 e1, e2）

- p2: Liu 研究保持稳定 Ni(II) 的 NiFe-sc-PBA，并以表征及 MD 讨论抑制重构。（证据 e3）

- p3: 不同催化剂状态与工况不能仅据摘要数值直接排名优劣。（证据 e1, e3）


边界：

- 不能将两篇统一描述为必须先重构为 NiOOH 才能活化。


**e1** · Jiang et al. (2025) · DOI `10.1021/jacs.5c00325` · PDF 物理页 1 · 字符 [731, 926)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Jiang 等 - 2025 - Unraveling side reactions in paired CO2 electrolysis at operando conditions a case study of ethylene glycol oxidation.pdf>)


```text
Herein, we examined the oxidation of ethylene glycol (EG), one of
the simplest polyols, as a model reaction on a series of nickel
oxyhydroxide model catalysts (β-NiMxOOH, M = Ni, Co, Fe, and
Cu).
```


**e2** · Jiang et al. (2025) · DOI `10.1021/jacs.5c00325` · PDF 物理页 1 · 字符 [1123, 1329)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Jiang 等 - 2025 - Unraveling side reactions in paired CO2 electrolysis at operando conditions a case study of ethylene glycol oxidation.pdf>)


```text
we obtained the potential-resolved and quantitative
information on various side reactions comprising the OER,
overoxidation to CO/CO2, catalyst dissolution, and CO2 evolution from electrolyte decarbonation.
```


**e3** · Liu et al. (2025) · DOI `10.1038/s41467-025-58203-9` · PDF 物理页 1 · 字符 [810, 1344)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf>)


```text
Here, we present unique Ni(II) sites in Prussian blue ana-
logue (NiFe-sc-PBA) that serve as stable, efﬁcient and selective active sites for
ethylene glycol (EG) electrooxidation to formic acid, particularly at ampere-
level current densities. Our in situ/operando characterizations demonstrate
the robustness of Ni(II) sites during EG electrooxidation. Molecular dynamics
simulations further illustrate that EG molecule tends to accumulate on the
NiFe-sc-PBA surface, preventing hydroxyl-induced reconstruction in alkaline
solutions.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D17 · comparison

Compare the HAT mediators and organic feedstocks in Kawajiri (2025) benzyl-alcohol oxidation and Mi (2025) benzylic C-H oxidation.

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: Kawajiri 以 TFE 为 HAT 介体，处理苄醇氧化。（证据 e1）

- p2: Mi 由 CoOx/IrO2 活化 NO3− 产生自由基以抽取苄位 C-H 的氢，示范甲苯到苯甲醛。（证据 e2, e3）


边界：

- 两篇目标均可为醛，不代表其起始底物、介体或反应体系相同。


**e1** · Kawajiri et al. (2025) · DOI `10.1021/acs.orglett.5c01138` · PDF 物理页 1 · 字符 [390, 595)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Kawajiri 等 - 2025 - Electrochemical oxidation of benzyl alcohols via hydrogen atom transfer mediated by 2,2,2-trifluoroethanol.pdf>)


```text
We found that trifluoroethanol plays a role as a hydrogen atom transfer (HAT)
mediator, enabling the oxidation of electron-deficient substrates that are difficult
to directly oxidize on electrode surfaces.
```


**e2** · Mi et al. (2025) · DOI `10.1038/s41467-025-58733-2` · PDF 物理页 1 · 字符 [498, 719)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Mi 等 - 2025 - CoOx clusters-decorated IrO2 electrocatalyst activates NO3- mediator for benzylic C-H activation.pdf>)


```text
Here, we introduce an electrocatalyst:mediator assembly
in which CoOx clusters-decorated IrO2 electrocatalyst activates NO3
- mediator
to a highly reactive radical capable of abstracting a hydrogen atom from
benzylic C-H.
```


**e3** · Mi et al. (2025) · DOI `10.1038/s41467-025-58733-2` · PDF 物理页 1 · 字符 [854, 997)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Mi 等 - 2025 - CoOx clusters-decorated IrO2 electrocatalyst activates NO3- mediator for benzylic C-H activation.pdf>)


```text
Our
strategy is demonstrated through the selective oxidation of toluene to ben-
zaldehyde with high Faradaic efﬁciency of 86( ±1)% at 25 mA/cm2
```


人工复核者/日期：待填写；判断与理由：待填写。

## D18 · comparison

Han（2025）的 PET 升级与 Fan（2025）的环己醇氧化分别生成什么酸？请说明为何不能直接比较两篇百分数。

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: Han：LM-PdCu 脉冲电催化 PET 来源体系制 GA（乙醇酸），报告 FE >92%。（证据 e1, e2）

- p2: Fan：Mo 掺杂 Ni2P@Ni12P5 将环己醇氧化为 AA（己二酸），85.7% 为 AA 收率，100% 为 H2 FE。（证据 e3, e4）

- p3: 不同原料、产物和指标定义，不能据百分数直接比较催化选择性。（证据 e2, e4）


边界：

- 不能将 GA 与 AA 混用，也不能把 yield 当 FE。


**e1** · Han et al. (2025) · DOI `10.1038/s41467-025-58813-3` · PDF 物理页 1 · 字符 [520, 814)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Han 等 - 2025 - Pulsed electrosynthesis of glycolic acid through polyethylene terephthalate upcycling over a mesoporous PdCu catalyst.pdf>)


```text
In
this work, pulsed electrocatalysis is employed to engineer chemisorption
properties on a lamellar mesoporous PdCu (LM-PdCu) catalyst, which delivers
high activity and stability for selective electrosynthesis of high value-added
glycolic acid (GA) from PET upcycling under ambient conditions.
```


**e2** · Han et al. (2025) · DOI `10.1038/s41467-025-58813-3` · PDF 物理页 1 · 字符 [1126, 1334)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Han 等 - 2025 - Pulsed electrosynthesis of glycolic acid through polyethylene terephthalate upcycling over a mesoporous PdCu catalyst.pdf>)


```text
This strategy thus delivers GA Faraday efﬁciency of >92% in wide potential
windows, yield rate of reaching 0.475 mmol cm–2 h–1, and cycling stability of
exceeding 20 cycles for electrocatalytic PET upcycling.
```


**e3** · Fan et al. (2025) · DOI `10.1002/adma.202502523` · PDF 物理页 1 · 字符 [519, 758)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Fan 等 - 2025 - Doping Mo triggers charge distribution optimization and P vacancy of Ni2 P@Ni12 P5 heterojunction for industrial electrocatalytic production of adipic acid and H2.pdf>)


```text
Herein, a robust Mo-doped Ni2P@Ni12P5 heterojunction with
more P vacancies on Ni foam is proposed for accomplishing simultaneous
electrooxidation of cyclohexanol (CHAOR) to AA and hydrogen evolution
reaction (HER) at large current density.
```


**e4** · Fan et al. (2025) · DOI `10.1002/adma.202502523` · PDF 物理页 1 · 字符 [1434, 1593)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Fan 等 - 2025 - Doping Mo triggers charge distribution optimization and P vacancy of Ni2 P@Ni12 P5 heterojunction for industrial electrocatalytic production of adipic acid and H2.pdf>)


```text
Consequently,
a two-electrode ﬂow electrolyzer achieves industrial current density (>230 mA
cm−2) with 85.7% AA yield, 100% Faradaic eﬃciency of H2 production.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D19 · insufficient_evidence

仅根据 Jiang（2025）论文摘要，能否给出其每吨产品的分离成本、所用电价及完整经济性模型？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 摘要只提供受控配对体系能耗降低 21.1%（考虑分离）的相对结论。（证据 e1）

- p2: 所限定的摘要不足以给出吨产品分离成本、电价和完整经济模型；需查正文/SI及相应参数，不能猜数值。（证据 e1）


边界：

- 不得把相对能耗降低转写为同等成本下降或虚构电价；不声称整个语料没有经济分析。


**e1** · Jiang et al. (2025) · DOI `10.1021/jacs.5c00325` · PDF 物理页 1 · 字符 [1728, 1979)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Jiang 等 - 2025 - Unraveling side reactions in paired CO2 electrolysis at operando conditions a case study of ethylene glycol oxidation.pdf>)


```text
Importantly, paired
electrolysis can easily suffer from higher energy consumption than the conventional counterpart, provided side reactions are
unregulated. Yet the modulated one consumed 21.1% less energy even when product separation was considered.
```


人工复核者/日期：待填写；判断与理由：待填写。

## D20 · insufficient_evidence

仅依据 Lin（2025）论文摘要，能否量化其 liquid-free MEA 出口环氧丙烷的纯度及水含量？

状态：AI 原文草案；人工领域复核待完成。

回答要点：

- p1: 摘要给出 227 μmol h−1 和 78 h 稳定性。（证据 e1）

- p2: 这些指标不是出口 PO 纯度或含水量；给定摘要不足以量化两者，需另查分析数据。（证据 e1）


边界：

- 不得把 liquid-free 理解为测得零水含量或 100% PO 纯度；不将摘要范围外信息说成全库不存在。


**e1** · Lin et al. (2025) · DOI `10.1038/s41467-025-58486-y` · PDF 物理页 1 · 字符 [1088, 1234)


[原始 PDF](</Users/zemaochen/projects/ChemQA/data/raw_papers/Lin 等 - 2025 - V activated electro-epoxidation catalyst in membrane electrode assembly system for the production of propylene oxide.pdf>)


```text
The MEA reactor, integrated with
the developed Ag/V catalyst, can maintain a stable production rate of PO at 227
μmol/h over a period of 78 hours.
```


人工复核者/日期：待填写；判断与理由：待填写。
