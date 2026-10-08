# Q06.5-B 生成基线待发送范围

状态：本地准备后，用户明确批准按此预览范围发送；批量基线已完成，20/20 正常结束，见 [基线记录](Q06_5B_BASELINE.json)。以下链接保留发送前的完整快照，实际发送状态以生成基线记录为准。

目的地：`https://llmapi.paratera.com/v1/chat/completions`。内容为 20 个固定开发问题及 Q10-A 实际检索出的原文片段、来源名、文献/片段身份和页码；不含密钥以外的账户资料，密钥只用于鉴权，不放入提示；不含回答要点/gold 标注和预留题。

每题单次，Flash 显式关闭思考，最多 4096 输出 tokens，温度 0.3。由第三方平台处理这些文本，可能产生费用；目前没有可信的该别名价格表，费用记为未知。

[全部准备输入与哈希清单](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/protocol.json>)

## 问题及实际提示预览

- [D01 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D01.json>)：Kawajiri（2025）的苄醇电氧化中，TFE 扮演什么角色，主要帮助处理哪类底物？

- [D02 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D02.json>)：Kawajiri（2025）氧化 4-甲氧基苄醇的标准电解条件是什么？列出电极、电流、溶剂和主要添加物用量。

- [D03 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D03.json>)：In Lu (2025), which reagent supplies the primary alkyl radicals, and are additional oxidants or supporting electrolytes required?

- [D04 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D04.json>)：Lu（2025）的烯烃脱羧烷基-烷氧基化中，羧酸根和烯烃哪一个先发生阳极氧化，之后怎样形成自由基？

- [D05 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D05.json>)：How does Song (2025) promote Ni-H formation, and what roles does the proton source play in the proposed selectivity control?

- [D06 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D06.json>)：Which starting-material classes and heterocycle are involved in Huang (2025) cathodic oxygen-reduction-enabled Rh-catalyzed (5+1) annulation?

- [D07 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D07.json>)：Huang（2025）的 Rh 环化是否通过阳极直接氧化催化剂完成再生？分别说明阳极和阴极的作用。

- [D08 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D08.json>)：Liu（2025）的 NiFe-sc-PBA 在 500 和 1000 mA cm−2 下分别需要多少电位？说明参比标尺，勿与整槽电压混用。

- [D09 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D09.json>)：For Liu (2025) NiFe-sc-PBA coupled flow electrolysis, what switching current densities and continuous operating duration are reported?

- [D10 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D10.json>)：Liu（2025）如何解释乙二醇抑制 NiFe-sc-PBA 重构？区分结构表征和分子动力学各支持什么。

- [D11 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D11.json>)：Mi（2025）的甲苯电氧化中，低电流与流动体系分别报告了什么苯甲醛法拉第效率和电流密度？

- [D12 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D12.json>)：In Lin (2025), what propylene oxide production rate and stability duration are reported for the Ag/V liquid-free MEA?

- [D13 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D13.json>)：Han（2025）用 LM-PdCu 脉冲电催化升级 PET 制乙醇酸，报告了哪些 FE、面产率和循环稳定性指标？

- [D14 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D14.json>)：Fan（2025）Mo-Ni2P@Ni12P5 双电极流动槽的电流密度、己二酸收率及 H2 法拉第效率各是多少？

- [D15 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D15.json>)：Li（2025）配对 CO2 还原和甲醛脱氢的甲酸盐 FE 约 190%，它对应哪两个半反应，能否当成单一阴极 FE？

- [D16 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D16.json>)：比较 Jiang（2025）的 NiOOH 乙二醇氧化与 Liu（2025）的 Ni(II) PBA 路线：各自如何讨论析氧与重构？

- [D17 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D17.json>)：Compare the HAT mediators and organic feedstocks in Kawajiri (2025) benzyl-alcohol oxidation and Mi (2025) benzylic C-H oxidation.

- [D18 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D18.json>)：Han（2025）的 PET 升级与 Fan（2025）的环己醇氧化分别生成什么酸？请说明为何不能直接比较两篇百分数。

- [D19 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D19.json>)：仅根据 Jiang（2025）论文摘要，能否给出其每吨产品的分离成本、所用电价及完整经济性模型？

- [D20 完整输入](</Users/zemaochen/projects/ChemQA/output/q065b_previews/20261007T012843-cab5ece4c5124f4297556864994be589/D20.json>)：仅依据 Lin（2025）论文摘要，能否量化其 liquid-free MEA 出口环氧丙烷的纯度及水含量？


## 检索证据涉及 83 份 PDF

这是实际取回证据的来源清单，包含可能不相关的检索结果；不会额外发送 PDF 整文件。

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Cai 等 - 2025 - Bromide-mediated membraneless electrosynthesis of ethylene carbonate from CO2 and ethylene.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Cao 等 - 2025 - Activating surface oxygen in cemo‐doped ni oxyhydroxide for synergistically enhancing furfural oxidation and hydrogen evolution at ampere‐level current densities.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Cha 等 - 2025 - Interfacial lithium cations catalyze biomimetic aerobic oxygenation via short‐range electrostatic interaction.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Cheng 等 - 2025 - Metal-organic double layer to stabilize selective multi-carbon electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Cheng 等 - 2025 - Structure sensitivity and catalyst restructuring for CO2 electro-reduction on copper.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Chi 等 - 2025 - Acidic CO2 electrolysis with near‐ideal selectivity and carbon efficiency enabled by overcoming its inherent trade‐off.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Chico-Mesa 等 - 2025 - Insights into catalytic activity and selectivity of 5-hydroxymethylfurfural oxidation on gold single-crystal electrodes.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Chuang 等 - 2025 - Exploring electrochemical C(sp3 )–H oxidation over fe complexes ligand effect on the rate–bond dissociation energy relationship and reaction mechanism.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Dong 等 - 2025 - Interlayer-bonded NiMoO2 electrocatalyst for efficient hydrogen evolution reaction with stability over 6000 h at 1000 mA cm−2.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Fan 等 - 2025 - Doping Mo triggers charge distribution optimization and P vacancy of Ni2 P@Ni12 P5 heterojunction for industrial electrocatalytic production of adipic acid and H2.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Fan 等 - 2025 - Doping Mo triggers charge distribution optimization and P vacancy of Ni2 P@Ni12 P5 heterojunction for industrial electrocatalytic production of adipic acid and H2_1.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Feng 等 - 2025 - Triple synergy engineering via metal‐free dual‐atom incorporation for self‐sustaining acidic ammonia electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Fu 等 - 2025 - High‐performance Cu6 Sn5 alloy electrocatalysts for formaldehyde oxidative dehydrogenation and bipolar hydrogen production.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Gao 等 - 2025 - Unveiling the solvation chemistry and surface effects on CO2 reduction reaction pathways in nonaqueous Li–CO2 batteries.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Guan 等 - 2025 - Cathode–anode synergy electrosynthesis of propanamide via a bipolar C–N coupling reaction.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Gui 等 - 2025 - Retreat in order to advance dual-electrode refinery of 5-hydroxymethylfurfural toward 2,5-furandicarboxylic acid with high carbon efficiency.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Guo 等 - 2025 - Selective CO electroreduction to multicarbon oxygenates over atomically dispersed cu–ag sites in alkaline membrane electrode assembly electrolyzer.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Han 等 - 2025 - Pulsed electrosynthesis of glycolic acid through polyethylene terephthalate upcycling over a mesoporous PdCu catalyst.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Hu 等 - 2025 - Electronic structure and interfacial microenvironment engineering over the ni(OH)2 nanoarray for boosted electrocatalytic upcycling of polyethylene terephthalate 2.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Huang 等 - 2025 - Cathodic oxygen reduction-enabled rhodium-catalyzed (5 + 1) C–HO–H annulation inspired by fuel cells.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Huang和Xu - 2025 - Scalable and practical electrooxidation of electron‐deficient methylarenes to access aromatic aldehydes.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Jia 等 - 2025 - Advancing electrocatalyst discovery through the lens of data science state of the art and perspectives.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Jia 等 - 2025 - Closed-loop framework for discovering stable and low-cost bifunctional metal oxide catalysts for efficient electrocatalytic water splitting in acid.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Jiang 等 - 2025 - Unraveling side reactions in paired CO2 electrolysis at operando conditions a case study of ethylene glycol oxidation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Kang 等 - 2025 - Boosting current density of electrocatalytic CO2 reduction using metal–enzyme hybrid cathodes.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Kawajiri 等 - 2025 - Electrochemical oxidation of benzyl alcohols via hydrogen atom transfer mediated by 2,2,2-trifluoroethanol.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Kim 等 - 2025 - Facet‐controlled growth of molybdenum phosphide single crystals for efficient hydrogen peroxide synthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - A pH-dependent microkinetic modeling guided synthesis of porous dual-atom catalysts for efficient oxygen reduction in zn–air batteries.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Effects of Ni(OH)2 structures on the electrochemical conversion of KA oil.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Electrifying amine carbon capture with robust redox-tunable acids.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Non-isothermal CO2 electrolysis enables simultaneous enhanced electrochemical and anti-precipitation performance.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Li 等 - 2025 - Strong electronic interactions of the abundant CuCe interfaces stabilized Cu2 O for efficient CO2 electroreduction to C2+ products under large current density.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Lin 等 - 2025 - V activated electro-epoxidation catalyst in membrane electrode assembly system for the production of propylene oxide.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Electrochemical lattice engineering of bismuthene for selective glycine synthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Enhanced p–d orbital coupling in unconventional phase RhSb alloy nanoflowers for efficient ammonia electrosynthesis in neutral media.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Enhancing C─C bond cleavage of glycerol electrooxidation through spin‐selective electron donation in pd–PdS2 –cox heterostructural nanosheets.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Liu 等 - 2025 - Stable Ni(II) sites in prussian blue analogue for selective, ampere-level ethylene glycol electrooxidation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Long 等 - 2025 - Manipulation of hydrogen transfer behaviors by RhCu alloying enables an all‐in‐one sustainable “furfural‐nitrate” system.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Lu 等 - 2025 - Metal‐free electrochemistry‐driven decarboxylative primary alkyl‐alkoxylation of olefins.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Lu 等 - 2025 - Multiple secondary bond-mediated C–N coupling over N-doped carbon electrocatalysts.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Lu 等 - 2025 - Unlocking single-atom induced electronic metal-support interactions in electrocatalytic one-electron water oxidation for wastewater purification.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Luo 等 - 2025 - 2D conjugated metal–organic frameworks as electrocatalysts for boosting glycerol upgrading coupled with hydrogen production.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Luo 等 - 2025 - Photoelectrocatalytic activation of C─H bond in toluene by titanium dioxide‐supported subnanometric PtO x  clusters.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Ma 等 - 2025 - Cu supraparticles with enhanced mass transfer and abundant C-C coupling sites achieving ampere-level CO2-to-C2+ electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Mao 等 - 2025 - Phosphorus-mediated oxygen vacancy engineering in Cu2 O for highly selective CO2 electroreduction to multicarbon products.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Mi 等 - 2025 - CoOx clusters-decorated IrO2 electrocatalyst activates NO3- mediator for benzylic C-H activation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Qi 等 - 2025 - Single-atom ru-triggered lattice oxygen redox mechanism for enhanced acidic water oxidation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Qian 等 - 2025 - Elucidating the activity of electrochemical nitrate reduction high-valent anionic intermediates as kinetic gatekeepers.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Qian 等 - 2025 - Hydrophobic cation-immobilized covalent organic frameworks enable selective and stable electrosynthesis of ethylene from CO2.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Qin 等 - 2025 - Construction of atomic-scale compressive strain for oxime electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Qin 等 - 2025 - Electroreduction of diluted CO2 to multicarbon products with high carbon utilization at 800 mA cm–2 in strongly acidic media.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Shen 等 - 2025 - Corrosion protection of rare earth for kilowatt-level alkaline seawater electrolyzer.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Sheng 等 - 2025 - Electrochemical benzylic C─H sulfation beyond the O ‐sulfonation limitation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Shi 等 - 2025 - Electrocatalytic ethylene glycol to long-chain C3+ α-hydroxycarboxylic acids via cross-coupling with primary alcohols.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Si 等 - 2025 - Selective photoelectrochemical synthesis of adipic acid using single-atom Ir decorated α-Fe2O3 photoanode.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Sun 等 - 2025 - Updating the sub-nanometric cognition of reconstructed oxyhydroxide active phase for water oxidation.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wang 等 - 2025 - Interfacial water structure modulation on unconventional phase non‐precious metal alloy nanostructures for efficient nitrate electroreduction to ammonia in neutral media.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wang 等 - 2025 - Mesoporous single-crystalline particles as robust and efficient acidic oxygen evolution catalysts.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wang 等 - 2025 - Scale-up upcycling of waste polyethylene terephthalate plastics to biodegradable polyglycolic acid plastics.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wen 等 - 2025 - Constructing a localized buffer interlayer to elevate high-rate CO2 -to-C2+ electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wen 等 - 2025 - Design of twisted two-dimensional heterostructures and performance regulation descriptor for electrocatalytic ammonia production from nitric oxide.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wu 等 - 2025 - Insights into lattice oxygen and strains of oxide-derived copper for ammonia electrosynthesis from nitrate.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wu 等 - 2025 - Intermittent electrolysis enabling the enhanced efficiency and stability for nitrate reduction.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wu 等 - 2025 - Photothermal-promoted anion exchange membrane seawater electrolysis on a nickel-molybdenum-based catalyst.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Wu和Wang - 2025 - The role of protons in CO2 reduction on gold under acidic conditions.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xia 等 - 2025 - Electrochemical oxidation of nitric oxide to concentrated nitric acid with carbon-based catalysts at near-ambient conditions.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xiao 等 - 2025 - Asymmetric CO–CHO coupling over Pr single-atom alloy enables industrial-level electrosynthesis of ethylene.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xing 等 - 2025 - Efficient bicarbonate electrolysis to formate enabled via ionomer surface modification in cation exchange membrane electrolyzers.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xu 等 - 2025 - A nature-inspired solution for water management in a zero-gap CO2 electrolyzer.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xu 等 - 2025 - Strong p–d orbital hybridization in atomically ordered intermetallic Pd3 Bi metallene enables energy-efficient simultaneous electrosynthesis of a nylon-6 precursor and glycolic acid.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Xue 等 - 2025 - Simple and scalable introduction of single-atom mn on RuO2 electrocatalysts for oxygen evolution reaction with long-term activity and stability.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Yang 等 - 2025 - Ampere‐level 4000 h parallel alcohols electro‐refinery and hydrogen production.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Yang 等 - 2025 - Tailoring coordination microenvironment of nickel molecular complexes for electrooxidation of organic nucleophiles.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Yin 等 - 2025 - Copper-catalyzed C(sp3)−H amination and etherification of unactivated hydrocarbons via photoelectrochemical pathway.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhai 等 - 2025 - Modulating product selectivity in lignin electroreduction with a robust metallic glass catalyst.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhang 等 - 2025 - Efficient ammonia electrosynthesis from pure nitrate reduction via tuning bimetallic sites in redox‐active covalent organic frameworks.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhang 等 - 2025 - Electrochromic rutile with dynamically tailored surfaces in formaldehyde-mediated hydroxylamine electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhang 等 - 2025 - High-efficiency ammonia electrosynthesis from nitrate on ruthenium-induced trivalent cobalt sites.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhang 等 - 2025 - Rational ligand design of conjugated coordination polymers for efficient and selective nitrate electroreduction to ammonia.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhang 等 - 2025 - Residual ligand-functionalized ultrathin Ni(OH)2 via reconstruction for high-rate HO2− electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhao 等 - 2025 - Optimization and scaling-up of porous solid electrolyte electrochemical reactors for hydrogen peroxide electrosynthesis.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhou 等 - 2025 - Elevating nitrate reduction through the mastery of hierarchical hydrogen-bond networks.pdf

- /Users/zemaochen/projects/ChemQA/data/raw_papers/Zhu 等 - 2025 - Tuning local proton concentration and OOH intermediate generation for efficient acidic H2 O2 electrosynthesis at ampere‐level current density.pdf
