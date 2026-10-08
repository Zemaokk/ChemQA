# Q06.5-B：生成接口与参数迁移

状态：实现与真实执行验收完成，133 项回归及 Ruff 检查通过；科学回答质量尚未人工评审。下一项为 Q06.5-C。

本轮保留 Chat Completions 协议和现有检索证据，迁移生成配置并建立真实生成基线。不更换本地 embedding、分块、索引或依赖锁。

## 问题与配置

原实现默认 `deepseek-reasoner`、输出上限 30,000 tokens、固定 60 秒超时，未显式指定思考模式。第三方平台的模型别名和参数支持需要实际验证，不能从官方模型名直接推定。

[并行科技平台文档](https://ai.paratera.com/document/llm/modalAbility/text) 说明兼容对话入口与通用输出预算，但当前公开正文没有明确给出截图中 Flash 别名的思考参数。[DeepSeek 官方参数文档](https://api-docs.deepseek.com/api/create-chat-completion/) 提供 `thinking.type`；本轮将其作为待验证参数，再通过实际第三方请求核实行为。[官方思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/) 也指出思考模式的采样参数限制，因此开启思考时不发送 temperature、penalty 或 top_p。

| 项目 | 本机采用配置 |
|---|---|
| 接口 | `https://llmapi.paratera.com/v1/chat/completions` |
| 模型 | 平台模型列表中的 `DeepSeek-V4-Flash` |
| 模式 | `thinking: {"type": "disabled"}`，`stream: false` |
| 输出请求上限 | `max_tokens: 4096` |
| 采样 | 非思考模式 `temperature: 0.3`，其余采样字段不发送 |
| 超时 | 建连 10 秒、读取 120 秒；读取超时不是整次运行的总时间上限 |
| 应用重试 | 默认最多 3 次尝试，仅瞬态网络错误、429、指定 5xx 和资源不足可重试，等待 1/2 秒；可配置 1–5 次，退避上限 8 秒 |
| 基线协议 | 每个开发题 1 次尝试、1 次运行，失败也保留；不自动重试和挑选答案 |

环境变量沿用 `DEEPSEEK_*` 名称以兼容现有入口。仓库无环境覆盖时使用官方 `deepseek-flash`；本机忽略的 `.env` 使用第三方别名。官方入口未使用本机第三方密钥测试，不将本次兼容性结论推广到其他供应商。新模型/模式组合应重新烟测，不会遇到不支持参数就静默移除开关或自动换模型。

返回的 `DeepSeek-V4-Flash` 是供应商声明的模型名，不能证明其底层权重版本或 revision。关闭思考时仍可能在可见答案中给出推导；本轮验证的是独立 reasoning 字段和返回 token 统计的差异，并非证明模型内部没有任何推理。

`max_tokens` 是发出的请求字段，不能当作费用预算或保证所有第三方模型对 reasoning 的计算方式相同。若后续试验较长思考任务，应预先固定例如 8k 的输出上限，另建候选实验；此次 512-token 思考探针仅核验开关，不是困难题质量比较。Pro 未运行，也未依据这批结果评出最优模型。

## 调用与记录

`GenerationResult` 保持成功、无证据、失败、截断的独立状态；增加去除密钥和端点的参数快照、独立思考内容是否出现及字符数。保留 provider 返回的 prompt/completion/total tokens、可用的 reasoning/cache token 明细；缺失字段不补零。原始思考文本不落盘。

每次尝试记录状态、错误类型、HTTP 状态、结束原因、请求/返回模型、响应 ID、用量和耗时；最终 usage 只对应最后一次尝试，累计消耗应查看 attempt_history，不能漏掉此前失败请求的已返回用量。超时可能发生在服务端已处理请求之后，重试可能产生额外计费；本次基线固定单次避免将重试混入比较。

HTTP 错误不暴露原始错误正文；参数无效在发请求前停止。禁止跟随重定向。`length` 保留隔离的 partial_content，不能作为正常答案。空证据继续在本地停止，`request_sent=false`、attempts=0，无需有效凭据。

## 本轮真实验证

初步使用两次不含文献的小请求确认模型列表及开关；随后通过更新后的处理器运行三项烟测：关闭/开启思考各一次，以及 max_tokens=1 强制截断。详见 [前置探针](Q06_5B_PREFLIGHT.json) 与 [处理器烟测](Q06_5B_SMOKE.json)。关闭时 reasoning tokens 为 0；开启时返回独立 reasoning_content 和正数 reasoning tokens；强制截断记为 truncated。空证据对照未发请求。

真实开发基线复用 Q10-A 已冻结的 20 个问题与其实际检索上下文，保持完整提示版本，不把标准回答/原文标注塞入提示。各题可能取回不相关的文章，仍保留现有检索结果以建立真实系统参照；没有用标注答案修补召回。预留题不运行。

发送前生成 [待发送范围](Q06_5B_SEND_SCOPE.md) 与 [输入清单](Q06_5B_PREVIEW.json)，包括 20 个完整提示与 83 份实际取回 PDF 的身份及来源名。自动审批曾因具体文献片段发往第三方的授权范围不明确而阻止批量请求；用户随后明确批准按预览范围发送。发送前逐题核对哈希、提示内容与配置，未发送整份 PDF、标准答案或预留题。

完整生成输入与回答保存在独立的忽略输出目录，基线记录保留逐题提示 SHA-256、实际参数、执行结果及手工评分空模板。回答质量仍未人工评分，Q10-A 标注的领域复核也仍待完成；不能把 HTTP/stop 成功率写成科学准确率。正式随机比较与独立保留集评估属于 Q10-B。

供应商未提供本次采用别名的已核实价格表，费用为 null；token 数是接口返回的用量，不能以官方价格推定第三方账单，也不能将未知费用写成零。

## 重复运行

```bash
# 离线单元测试
uv run --locked python -m unittest discover -s tests -q
uv run --locked ruff check .
uv run --locked ruff format --check .
# 本地准备完整待发送输入；不发送请求
uv run --locked python -m scripts.validate_q065b --prepare --report output/q065b_preview.json
# 三个小请求，验证模式与截断；--live 明确触发可能计费的请求
uv run --locked python -m scripts.validate_q065b --live --smoke --report output/q065b_smoke.json
# 检查预览并确认发送范围后，将路径换为预览报告中的 artifact_directory
uv run --locked python -m scripts.validate_q065b --live --prepared-input output/q065b_previews/<run-id> --report output/q065b_baseline.json
```

需要 Q10-A 实际检索运行目录及原始 PDF/索引。新环境若只有源码快照，先按 Q10-A 文档准备数据并重新建立检索报告，通过 `--retrieval-report` 指定该报告。输入或配置变化会拒绝沿用旧预览，须重新准备与检查；命令默认不发送请求。每次创建独立目录，历史 Q06.5-A、Q10-A 记录均不覆盖。

回退时可在本地恢复旧模型别名及预算/模式配置，但旧配置的接口有效性和回答质量不由新基线保证。保留 `DeepSeek-V3.2-Instruct` 旧别名记录供选择，不自动 fallback。检索索引保持可复用。

## 实际基线汇总

[基线记录](Q06_5B_BASELINE.json) 与 [验收记录](Q06_5B_VALIDATION.json)：20/20 题 status=success、finish_reason=stop，每题单次，无失败/截断/重试；返回模型均为平台别名 `DeepSeek-V4-Flash`，reasoning tokens 均为 0。预留题请求为 0，空证据对照请求为 0。原索引与处理后语料哈希不变。

供应商报告开发基线输入 81,120 tokens、输出 24,252 tokens、合计 105,372 tokens；这是 20 个请求的用量，不包含 2 次前置探针及 3 次处理器烟测，费用仍为未知。全部真实生成请求共 25 次。逐题回答入口见 [回答复核清单](Q06_5B_ANSWER_REVIEW.md)。
