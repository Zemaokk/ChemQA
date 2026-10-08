# Q03：科学文本清洗与真实模型长度

## 问题与实际核查

Q02 完成后的 3,187 个片段仍采用 500 个空白分词、50 个词重叠；`num_tokens` 实际记录词数。旧清洗会删除 `+`、括号、`/`、`%`、`°`、Unicode 减号与不等号等字符，破坏已提取的表达式。

使用当前锁定的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`）实测：SentenceTransformer `max_seq_length` 与 tokenizer 上限均为 **128**，其中 **2** 个是特殊 token。对旧片段逐条执行不截断分词：3,168 条超过上限，token 数最小值/中位数/90 分位/最大值为 8 / 904 / 1166.4 / 1420，总计 2,941,422 tokens。此核查说明旧片段全文通常没有全部进入编码器，不能据此量化检索质量损失。

## 实现

- 清洗仅合并空白并去除首尾空白，不删除或替换已提取的其他 Unicode 字符；版本为 `whitespace-only-model-tokens-v1`。
- 使用实际模型的 tokenizer offset mapping 按输入预算切分；默认内容最多 126 tokens，加特殊 token 后最多 128。优先完整词；遇到超长无空格字符串，使用原文字符切片继续分块，避免 tokenizer decode 改写字符。
- 重叠目标为 16 个内容 token，对齐词边界时实际重叠可以有差异；每个片段重新分词核查长度，保证向前推进。没有承诺该重叠设置已经过检索效果优化。
- 新记录使用 `word_count`、`embedding_token_count`、`embedding_token_limit`、`chunk_overlap_target_tokens`；模型 token 数包含特殊 token，去除误命名字段 `num_tokens`。索引保存模型、revision、实际上限及计数口径。
- 全量构建、增量文档、查询与热力图均通过统一编码入口检查上限。超长查询明确拒绝，要求缩短；不自动截断查询。
- 新文本的原文跨度继续采用 Q02 的物理页码与提取文本字符区间；完整原文片段进入引用 sidecar。文献字节 ID 保留，文本块按新文本和序号生成新 ID。
- Q01/Q02 历史回归使用显式 `legacy=True` 重放旧清洗/词分块；Q02 迁移拒绝新版本数据，防止把新块误当旧块重放。

## 重建与验收

完整管道在临时目录生成新片段和批量向量，经校验后把旧的 processed/index 两份文件按 SHA-256 命名备份到 `output/q03_backups/`，再替换当前文件。失败于提取、编码或校验阶段时，当前文件不变。两个文件各自替换，不是跨文件事务；中途异常可从两份备份恢复。当前仍使用 JSON 索引，新片段增加后向量文件约 321 MiB、片段文件约 59 MiB；索引存储与体积优化留待后续复现/存储工作。

运行：

```bash
uv run --locked python -m src.pipeline.vector_index_builder
uv run --locked python -m scripts.validate_q03 --report docs/Q03_VALIDATION.json
# 可选：--baseline-index output/q03_backups/vector_index.<SHA256>.json
# 同时验证 PDF 文献身份集合，并复现旧片段的 token 超限统计
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m scripts.smoke_check --retrieval
```

`validate_q03` 独立重开原始 PDF，验证每个原文跨度的页码、字符区间和精确文本；按新规则重建片段；核对新字段、模型配置、向量形状与有限数值；逐批比较实际 SentenceTransformer 输入 token IDs 与不截断 tokenizer 结果；检查每份 PDF 的全部非空白提取字符都被至少一个片段覆盖。

本次生成 **26,025** 个片段，对应 **180** 份不同字节的 PDF；全部定位，共 **28,016** 个已验证原文跨度、**1,991** 个跨页片段。包含特殊 token 的长度最小/中位数/90 分位/最大值为 **23 / 127 / 128 / 128**，超限数为 **0**。覆盖全部 **7,812,098** 个非空白提取字符，逐批实际编码输入 ID 与不截断 tokenizer 结果一致。

Q1/Q2/Q3 共 32 项回归测试通过，Ruff 检查及格式检查通过。结果以 [Q03_VALIDATION.json](Q03_VALIDATION.json) 的当前文件哈希和计数为准。Q02_VALIDATION.json 是重建前的历史验收记录，其哈希与旧片段数不再代表当前索引。

## 边界

此修改保留的是 PyMuPDF **已经提取出的字符**。PDF 提取、字体编码、扫描页和阅读顺序导致的缺字、错误或公式丢失，仍需另行处理；没有引入 OCR，也不能保证原始印刷化学式已被完整识别。保留 Unicode 字符不代表模型能区分所有字符，tokenizer 仍可能产生未知 token。

本次重建改变片段粒度及向量，并保留旧索引用于基线。旧回答的 `.evidence.json` 仍指向当时片段和证据，不会改写成新 ID。没有受控问答评估，因此不宣称检索或回答质量提升；Q04 的点积/余弦一致性问题继续待处理。
