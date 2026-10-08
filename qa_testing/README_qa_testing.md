# 有机电催化问答测试脚本-引用分析

本目录提供预设英文有机电催化问题的历史批量运行脚本，用于获取回答、检查接口状态和引用映射。它不是冻结科学质量评估入口；当前用法与复现边界见 [运行手册](../docs/RUNBOOK.md)和[评估指南](../docs/EVALUATION_GUIDE.md)。

## 脚本说明

### 测试脚本 (`test_organic_electrocatalysis_qa.py`)

**功能：** 对预设10个问题执行RAG问答；非空证据将发送真实API请求，可能计费。没有J的 `--runtime-profile` 选项，配置按环境及索引路径读取。

- 记录引用标记与上下文映射；不能用引用数量或映射率保证科学支持。

**使用方法：**
```bash
uv run --locked python -m qa_testing.test_organic_electrocatalysis_qa
# 可选：--index-dir output/indexes/<候选目录> --output-dir output/my-batches
```

## 测试问题列表

Q07 起，生成结果显式区分 `success`、`no_evidence`、`failed` 和 `truncated`。成功统计只计 `success`；空证据是本地返回，截断归失败且另列子计数，历史没有显式状态的记录归 `unverified`。存在答案字段或没有 error 字段不再用于推断成功。执行成功与引用数量均不证明科学答案正确。

失败不会保存为正常答案，RAG 批量脚本写入 `failure_XX.json`，直连脚本写入 `enhanced_failure_XX.json`。Q08 起，每次新建测试器会分别创建 `output/qa_batches/<session-id>/` 或 `output/direct_api_batches/<session-id>/`，跨会话不覆盖答案，也不自动载入旧会话汇总；旧目录保留。会话 `run.json` 初始为 `running`，汇总写完后为 `complete`，具体失败与未测数量仍须看计数。配置和保存规则见 [Q08 记录](../docs/Q08_REPRODUCIBILITY.md)，接口与重试策略见 [Q07 记录](../docs/Q07_API_RESULTS.md)。上述命令从项目根目录运行。

1. What are the key mechanisms of CO2 electroreduction on copper-based catalysts?
2. How does the coordination environment affect the performance of nickel-based electrocatalysts for alcohol oxidation?
3. What are the recent advances in electrochemical C-H functionalization of aromatic compounds?
4. How can we improve the selectivity of electrochemical reduction of carbonyl compounds?
5. What role do electrolyte additives play in organic electrocatalysis?
6. How does the surface structure of platinum catalysts influence organic molecule oxidation?
7. What are the challenges and solutions for electrochemical synthesis of heterocyclic compounds?
8. How can we achieve high current density in organic electrosynthesis?
9. What are the mechanistic insights into electrochemical oxidation of biomass-derived compounds?
10. How does the pH of electrolyte affect the reaction pathways in organic electrocatalysis?
