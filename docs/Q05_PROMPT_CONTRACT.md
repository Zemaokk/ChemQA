# Q05：统一提示输入与证据编号

## 问题与验收标准

此前 `ChemicalQAExpert` 取回 `list[dict]`，生成器却声明 `context: str`，随后将列表直接插入提示模板，得到 Python 对象表示。输入没有明确的字段语义、版本及空证据格式。Q01 已要求完整片段 ID，但新回答的后处理仍默认兼容局部编号及来源别名，输入与引用约定没有完整贯通。

本项验收标准：提示词中的证据是可独立解析的 JSON，全文及科学字符不变；每条证据的引用标记对应唯一完整 `chunk_id`；生成、格式化、引用统计及保存记录使用同一份证据快照；空证据明确表示；新链路拒绝非规范引用，历史解析保留兼容入口；通过拦截 HTTP 的实际请求构造验证，无需外部 API。

## 输入约定

上下文版本为 `chemqa-evidence-v1`，提示版本为 `chemqa-evidence-prompt-v1`。上下文结构：

```json
{
  "context_version": "chemqa-evidence-v1",
  "evidence_count": 1,
  "evidence": [
    {
      "citation": "[Ref chunk_<完整64位SHA256>]",
      "chunk_id": "chunk_<完整64位SHA256>",
      "doc_id": "doc_<完整64位SHA256>",
      "source_title": "paper.pdf",
      "location_status": "located",
      "page_numbers": [2, 3],
      "text": "完整片段文本"
    }
  ]
}
```

示例 ID 是结构占位符，实际输入始终使用验证过的完整 ID。

- 接收规范或嵌套的片段字典列表，先验证身份与位置，按身份去重并保留检索顺序、来源别名；不截断片段正文。
- JSON 转义引号、换行等特殊字符，保留 Unicode 科学字符。文献标题、文献身份及物理页码用于定位；正文才是证据内容。
- 生成提示不发送完整本地路径、局部片段序号、全部内部元数据或重复的原文跨度；完整来源与 Q02 原文跨度仍保存在证据 sidecar 中。
- 未定位的片段使用 `location_status: "unavailable"`、空页码数组及明确原因，不猜测页码。
- `None` 和空列表都序列化为 `evidence_count: 0`、`evidence: []`，不把 `None` 当正文。
- 提示明确区分证据数据与指令；正文中出现的引用编号、指令或 JSON 字样不创建新的证据对象或引用授权。JSON 结构与提示说明不等于已验证的模型抗注入能力。

生成器接受片段字典列表、`None` 或 `PreparedPrompt`。不再接受不带可验证身份的原始字符串，也不会将已有 JSON 字符串再次隐式包装成正文。手动调用生成器时应使用检索的 `return_dict_list=True`；检索默认字符串模式用于查看同一版本的证据 JSON，空结果也返回显式空 JSON。

## 快照与引用规则

`prepare_prompt` 生成冻结的 `PreparedPrompt`，记录最终提示、序列化上下文及完整证据快照；证据以 JSON 字符串保存，消费者取出的字典是独立副本。后续修改原始列表或返回的副本不会改变已经准备好的输入。生成器收到准备好的输入时原样发送提示，并检查问题一致性。

新问答链路只接受输入清单里的 `[Ref 完整chunk_id]`：

- 生成提示要求逐字使用 `citation` 字段，禁止局部编号、来源名、文献 ID 或裸数字引用，也不让模型自行编参考文献列表。
- 格式化及引用统计都显式使用 `allow_legacy=False`，仅完整片段 ID 能计为有效引用。
- 局部编号、来源别名、裸 `[1]` 等数字标记以及未知 ID 不会转换成有效证据引用；正文保留可见的“未解析引用”提示，并写入未解析记录。裸数字方括号在此严格模式下按不合约的引用标记处理。
- 数字参考文献编号由系统按文献身份后处理生成。同篇文献的不同片段仍分别保留 `chunk_id`，可以对应同一个显示用文献编号。
- 历史调用 `resolve_citations`、`ResponseFormatter`、`CitationAnalyzer` 默认保留旧的唯一别名解析行为；手动核查新答案时应显式传 `allow_legacy=False`。历史答案文件不改写。

新 `.evidence.json` 增加 `generation_input`：提示/上下文版本、模板 SHA-256、领域、最终提示全文、证据 JSON、允许引用的完整 ID 列表及规范引用策略。最终保存的提示与实际 API 消息内容一致，原有 `evidence_map` 继续保存完整证据与原文位置。

## 验证

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m scripts.validate_q05 --report docs/Q05_VALIDATION.json
```

新增 10 项 Q05 测试，连同前面阶段共 **51 项**。覆盖科学字符/引号/换行/花括号 JSON 往返、域及问题插值、嵌套记录与去重、快照独立性、跨页/未定位数据、空证据、错误输入在 API 前拒绝、准备好的提示原样发送、严格/历史引用解析、检索字符串入口及最终保存链路。

真实验收使用当前索引检索两条示例问题，每次 10 个片段，经过真实提示构造和真实 API payload 构造；全部 HTTP 请求由本地模拟替代，外部 API 请求数为 **0**。模拟回答包含一个真实输入 ID 及三个无效标记，验证生成输入、保存记录、格式化与引用统计一致。索引及片段文件 SHA-256 均不变。详细记录见 [Q05_VALIDATION.json](Q05_VALIDATION.json)。

## 未解决的范围

本项验证输入与引用映射，不验证模型遵守提示的效果或事实性主张是否被原文支持。未进行真实模型调用，也没有对答案质量作结论。证据不足时的回答边界属于 Q06；API 错误状态属于 Q07；生成输入 token 预算、每次输出的独立命名与其他复现工作仍需后续处理。本次保留原回答章节结构及现有输出路径。
