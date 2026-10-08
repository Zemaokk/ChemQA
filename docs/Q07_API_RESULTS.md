# Q07：API 结果、失败与截断状态

日期：2026-10-07

状态：已完成结构化结果、失败隔离、有限重试与批量统计修正；81 项回归及 8 个真实检索/模拟 HTTP 场景通过。未调用真实生成模型。

## 原问题与本项验收

旧处理器将 HTTP/网络错误转换为 `API Error: ...` 等普通字符串。生成器、引用分析和输出保存无法据此区分正常回答与失败，旧批量脚本又以“没有 error 字段”或“存在 answer 字段”推断成功。旧重试依赖错误文字包含 rate limit，但实际 HTTP 错误字符串只有状态码；响应也未验证 `finish_reason`。

本项验收要求：

- 成功、空证据、失败与截断有明确状态；失败不作为答案返回。
- 限流、服务故障、超时和连接错误按明确类别执行有限重试；永久错误立即结束。
- 失败与截断不进入引用分析，不覆盖上一份正常答案；提示快照和失败状态可核查。
- 批量统计只计明确成功，空证据和历史未核实记录单列。
- Q05 引用约定、Q06 空证据停止及科学支持未核实记录继续生效。

本项保持原模型 ID、模型参数、索引与分块配置；模型接口迁移仍归 Q06.5-B，通用运行目录管理归 Q08。

## 结果接口

新增 [GenerationResult](../src/api_integration/result.py)，记录 schema 为 `chemqa-generation-result-v1`：

| status | 含义 | 可作为完整文本返回 | 计入模型调用成功 |
|---|---|---|---|
| `success` | 收到符合约定的完整非空回答 | 是 | 是；不代表科学正确 |
| `no_evidence` | Q06 的本地证据不足返回 | 是 | 否；未发 API 请求 |
| `failed` | 配置、HTTP、网络、协议或非正常结束失败 | 否 | 否 |
| `truncated` | `finish_reason=length`，输出不完整 | 否 | 否 |

同时记录 error code/message、HTTP 状态、结束原因、请求/返回模型、响应 ID、可用的 token 用量、尝试次数、每次尝试摘要、总耗时及是否进入请求尝试。

没有返回的 token 用量保持缺失，不推断为零。重试记录保留每次已收到的用量，不把最终一次的用量当作全部重试的费用。超时请求是否产生服务端用量无法由本地记录确认。

截断或其他非正常结束的文本仅保留在诊断字段 `partial_content`，结果的 `content` 为 null，不能通过正常文本接口取出。不会把 `reasoning_content` 当成最终答案。

新接口：

- `DeepSeekAPIHandler.send_request(messages)`：单次请求，返回 `GenerationResult`；缺失密钥抛出带结构化结果的配置异常。
- `DeepSeekAPIHandler.generate_result(prompt, max_attempts=3)`：统一有限重试与最终结果。
- `DeepSeekAnswerGenerator.generate_answer_result(question, context)`：包含空证据门控的结构化入口。

兼容文本接口 `generate_response`、`generate_answer` 仍在完成时返回字符串；失败或截断抛出 `APIGenerationError`，其 `.result` 可读取诊断。缺失密钥异常同时兼容 `ValueError`，保留 Q0 检查方式。无效问题/上下文等调用方输入错误继续按原方式报错，不冒充证据不足。

## 响应检查与重试

完整成功需要 HTTP 200、有效 JSON 对象、单条 completion、可用 message、明确 `finish_reason=stop` 及非空文本。缺少结束原因、仅有推理文本、空白内容或结构错误均失败。

`length` 标记截断；`content_filter`、`tool_calls`、`aborted` 等非正常结束不会作为普通答案。当前没有工具执行流程，因此工具调用响应不算完成。依据：[官方响应约定](https://api-docs.deepseek.com/api/create-chat-completion/)。

| 情况 | 重试策略 |
|---|---|
| 缺失密钥 | 不发送，不重试，attempts=0 |
| HTTP 429、500、502、503、504 | 在总尝试次数内重试 |
| Requests 超时与网络异常 | 分别记录 timeout/network，在总尝试次数内重试 |
| `insufficient_system_resource` | 在总尝试次数内重试 |
| 其他 HTTP 错误、无效响应、截断及其他结束原因 | 不自动重试 |

默认总尝试次数为 3，等待间隔 1 秒、2 秒，最后一次失败后不额外等待。批量直连脚本将原 `max_retries` 转成总次数 `max_retries + 1`，移除外层文字判断重试，避免内外两层相乘。依据：[官方错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。

当前保留每次 60 秒超时和固定退避，未在本项引入全流程时间预算或 Retry-After 调度；统一预算与参数选型由后续任务处理。HTTP 错误不读取或记录原始服务端 body，网络错误不记录原始异常文字，避免把凭据或服务端调试内容写入日志。

## 保存、命令行与批量脚本

完整回答及本地空证据返回仍保存到既有 Markdown/证据文件，证据记录新增 `generation_result`。`prompt_sent` 依据实际是否进入请求尝试，而不只依据上下文是否非空：缺密钥的非空证据请求也应为 false。

失败保存到 `output/answer_6.failure.json`，包括问题、准备的完整提示、证据身份、科学支持未核实标记和结果状态，`raw_answer` 为 null。随后抛出异常；格式化与引用分析不运行，原 `answer_6.md` 和 `.evidence.json` 不覆盖。

固定文件名仍是当前原型限制：failure 文件保存最近失败，不表示其他文件必然来自同一次运行；失败后看到的旧正常答案也不属于本次请求。独立运行目录、输出隔离与原子保存由 Q08 解决，本项未改写历史输出。

命令行单题失败退出码为 1，交互模式显示失败后继续接收问题。两套批量脚本按显式状态计数：

- `successful_tests` 只计 `success`。
- `failed_tests` 包含 failed 与 truncated，`truncated_tests` 是其中的子集。
- RAG 本地 `no_evidence` 单列，不计模型成功。
- 待运行为 pending；没有显式状态的历史记录归 unverified，不从答案长度、答案字段或缺少 error 推断成功。

旧历史答案、汇总 JSON 和历史成功率未被改写，也不能因本项实现而成为可靠质量基线。重新运行脚本汇总时，会区分新状态与历史未核实记录；正式受控比较仍属于 Q10。

## 验证与限制

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check .
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q07 --report docs/Q07_VALIDATION.json
```

- 原 63 项加新增 Q07 的 18 项，共 81 项测试通过。包含 HTTP/网络分类、有限重试、异常兼容、响应结构、截断隔离、空证据状态、答案保护、批量统计和命令行失败。
- [Q07 验证记录](Q07_VALIDATION.json) 使用真实索引检索的 10 条证据，覆盖成功、认证失败、截断、超时耗尽、限流后恢复、服务故障耗尽、空 completion 与空证据 8 个场景；HTTP 全部模拟。
- Q05 的真实检索/模拟 API 流程、Q06 的 8 个合成样例及环境烟测重新通过。旧 fixture 补充明确 stop 状态，以适配完整响应约定；没有放宽新校验来接受缺字段响应。
- 索引与处理文件 SHA-256 不变，外部生成 API 请求为 0。Q06.5-A 旧参照包及其审计文件保留。

当前没有配置真实 API 密钥，未确认旧模型 ID 的可用性、真实服务重试行为或生成质量。所有成功/失败场景是受控协议验证，不证明模型遵守科研证据边界。下一项为 Q08。
