# Q10-B 本地请求范围

状态：本地预览完成；用户已明确批准按此冻结范围发送，90次正式生成已完成。预览 run.json 及请求文件保持原状。

目录：`/Users/zemaochen/projects/ChemQA/output/q10b_previews/20261008T003102-7049b4e82a524fcabd2ff19c61501b35`。
run.json SHA-256：`0bf8e1385eecadfa8f5849ae03c2605ed0e3a9f133b4498b79537884a40209ef`。

固定6个预留问题、5个方案，每个输入3次独立请求，共最多90次；每次最多4096输出 tokens，总计最多368,640输出 tokens。检索输入涉及 35 份 PDF 的片段，不发送整份 PDF、标准答案、评分点或 must_not_claim。Direct 仅发送问题与指导文字。

目的地：https://llmapi.paratera.com/v1/chat/completions。可能计费，价格和精确输入 token 数未知，不声称费用为0。

预留检索已经在固定协议下使用；后续不得用结果调参后仍称独立验收。标签与科学评分待人工复核，本次授权不代表评分已完成。

| 问题 | 方案 | 片段数 | 本地输入字节估算 | payload SHA-256 |
| --- | --- | ---: | ---: | --- |
| R01 | direct | 0 | 1153 | `18d3fa43b4f67208ed210dcf1c6d697da465807437eacf1ce1701ff352267047` |
| R01 | bm25 | 8 | 31630 | `4e7daa5ea4ee88ed5d1113b7cb1e4eebc7c442995a59e8117b5e53915f89042f` |
| R01 | dense | 9 | 31526 | `e40c1fa1e5d5ec1cea85b85c3e45b5235656b0d105c334af8cce425ffda146a2` |
| R01 | hybrid_rerank | 10 | 30689 | `bd905427fe6bd843fd5f138cbc9398db6c34ea93064c5d3070be4ed1be0e9fe3` |
| R01 | hybrid_rerank_diverse | 10 | 29811 | `80838f03bff13afc151cd3919b8bc4eb0b76802cc6ea4f0d28ae4e93f089b1d6` |
| R02 | direct | 0 | 1036 | `4cbb97d7a3b26fd47a87e8bcd86fc2de5539e640e41b9758306be9879551203f` |
| R02 | bm25 | 9 | 31851 | `8878b722332f261a46465f7abe4e114453f4ad75a2af6cc1a390615d54eb1b66` |
| R02 | dense | 10 | 31709 | `3edd77b5f3944ee3cb94a3eb444c3eaa77c132d21e0bc898ec1fb08b5c27d5df` |
| R02 | hybrid_rerank | 10 | 31706 | `471fc72f76f07f041bffe11848541cae92a52fb2572a087b51a48bb11e577171` |
| R02 | hybrid_rerank_diverse | 10 | 31706 | `471fc72f76f07f041bffe11848541cae92a52fb2572a087b51a48bb11e577171` |
| R03 | direct | 0 | 1128 | `fd5524566370f6f03f31461a600c582689c513680d48665daeaf4c191b8ca9e2` |
| R03 | bm25 | 10 | 29667 | `c4aff14ae82f93d108dfd7f407c5ebdb3d5d914aec738ae3a18745b88c3a215b` |
| R03 | dense | 10 | 31343 | `dcc76d2d82745a67d8b6e7a60b90c785e0afa7cbdcbfd84a4912c4250265b775` |
| R03 | hybrid_rerank | 10 | 27819 | `4e22613b5855202ebf2db28f699a6266e8c8abfc724f2f3bb019f73201f0619b` |
| R03 | hybrid_rerank_diverse | 10 | 28376 | `4946f9b19e240d5899d0699d3a96bf8e426897cf65c1e47385d7d1d7c645b09d` |
| R04 | direct | 0 | 1058 | `553f9a1e87de89fe53589b567441d5166b4092ed22e49637d30c70b132f9c4a2` |
| R04 | bm25 | 9 | 31305 | `b97d52f2a7eabe591a12b5b5b5b921a15cf2345dcfe952ecaaa16178febc7ee0` |
| R04 | dense | 10 | 31559 | `e3fdc5a6e781513a30169876edd655c5dc825b79178a28c7090790513fd21e12` |
| R04 | hybrid_rerank | 10 | 31909 | `11cc216f2194a68b0b1c08dd37a9689fa312badab2857c11f8b4b307762d12cb` |
| R04 | hybrid_rerank_diverse | 10 | 31044 | `cb713525a91eddd4c6183e3411c26d0170886ea7b4da97f8fb48478ab0a5188e` |
| R05 | direct | 0 | 1121 | `bc49d7a0c59a41cfe8f8f66c67d902536bcb5e021c6eca2ec13fa8e53d6a4c51` |
| R05 | bm25 | 10 | 30554 | `f2c8b5bd51fc8b9b24b7d39449567401602495eff12f3d2efe1253ad58c1baa6` |
| R05 | dense | 10 | 30039 | `b6af118896d2d4eaaf3e4af4cf58edfa2618d4794be584a6b66c1dc991be4c43` |
| R05 | hybrid_rerank | 10 | 30714 | `dd944aec070702573f89aad6222d7fdf1db72a473bdebecda14a9a32cdcd85c2` |
| R05 | hybrid_rerank_diverse | 10 | 27989 | `52ae56d2a9a737b50c69214e06c090fe296904d157f370e0d20f85c504e23fb0` |
| R06 | direct | 0 | 1057 | `8bed2388298d98d7f08ed801973394e87fe253a4320fe0002f77775cadcdbef5` |
| R06 | bm25 | 9 | 31947 | `598b8a2d250bc65ebeaf275bb8bbebb7c883c0eba8544643af71bddb411767f5` |
| R06 | dense | 10 | 31190 | `38ad3bc82347b4176f7bd7d34a8d1a63b21300a2d15f3416bfd33edac08ff22f` |
| R06 | hybrid_rerank | 10 | 31905 | `f433292a5dcbb5421c820a90b2da38741a8228783101bb2a456c45d10430992a` |
| R06 | hybrid_rerank_diverse | 10 | 30739 | `2dca3b8b56b5bcf1e658509d6f5f17c2ae3758db05b2c1c99c33a69aa2e81edd` |
