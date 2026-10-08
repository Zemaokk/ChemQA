# Q06.5-C：检索模型依赖与本机兼容性

状态：已完成；候选和采用后的项目环境均通过 139 项回归，Ruff 检查通过。总计划已同步，下一项为 Q06.5-D。验收明细见 [Q06_5C_VALIDATION.json](Q06_5C_VALIDATION.json)。

本项更新运行依赖并核查候选模型能否正确执行。默认检索模型仍为 multilingual MiniLM，既有索引、分块、阈值和生成配置不变。新 embedding 的效果比较归 Q06.5-E，reranker 的召回后重排比较归 Q06.5-H。

## 验收与采用依赖

先在忽略的 `output/q065c_candidate/` 内复制项目配置及锁文件，单独建立环境；现有回归、新模型 CPU/MPS 烟测和旧 MiniLM 查询兼容检查通过后，才将候选配置和锁文件复制到项目环境。未将全体依赖统一升级到最新版本。

[Sentence Transformers 6.x 迁移说明](https://sbert.net/docs/migration_guide.html) 要求 Transformers 5.x、PyTorch 2.2+、Hugging Face Hub 1.x。[PyPI 发布记录](https://pypi.org/project/sentence-transformers/6.1.0/) 确认本次采用版本。实际锁定如下：

| 包 | 原版本 | 采用版本 |
|---|---|---|
| Python | 3.12.13 | 3.12.13 |
| sentence-transformers | 4.1.0 | 6.1.0 |
| transformers | 4.57.6 | 5.19.0 |
| torch | 2.14.1 | 2.14.1 |
| huggingface-hub | 0.36.2 | 1.33.0 |
| tokenizers | 0.22.2 | 0.23.2 |
| numpy | 2.5.3 | 2.5.3 |
| HTTPX / socksio | 非旧核心依赖 | 0.28.1 / 1.0.0 |

`pyproject.toml` 将 Sentence Transformers 范围改为 `>=6.1.0,<6.2`，增加 `httpx[socks]>=0.28.1,<1`；精确版本由 `uv.lock` 固定，`requirements.txt` 从锁文件重新导出。PyTorch 已满足要求，因此保留，其他非必需包也保持原锁定版本。

新版 Hub 使用 HTTPX，最初在现有 SOCKS 代理环境下因缺失 socksio 而无法下载。增加 SOCKS extra 后恢复；没有禁用或绕过本机代理。公开权重的 Xet 下载通道另出现基础设施 401，使用官方 Hub 的 `HF_HUB_DISABLE_XET=1` HTTPS 下载选项完成。下载未使用账户 token，也未发送文献或问题。

## 固定候选与完整模板

[config/model_candidates.json](../config/model_candidates.json) 仅保存待试验模型及 revision，不改变 `settings.EMBEDDING_MODEL`：

- [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)：`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`。
- [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)：`e61197ed45024b0ed8a2d74b80b4d909f1255473`。

各快照约 1.21 GB，位于忽略的模型缓存目录。加载明确使用 `local_files_only=True`、`trust_remote_code=False`、SDPA，不安装依赖 CUDA 的 flash-attn。

初次下载筛选漏掉 `.jinja` 文件，reranker 在处理 query/document 时明确报错，未通过烟测。补齐官方 `chat_template.jinja` 后，完整模板会渲染 `<Instruct>`、`<Query>`、`<Document>` 及回答前缀，烟测显式核查问题和文档确实进入提示；记录未截断的实际 token 数并与模型预处理一致性比较。

Embedding 使用快照中的 query 指令，document 使用空指令；输出为 1024 维归一化向量。Reranker 使用 Sentence Transformers 的 `Transformer + LogitScore`，分数是 yes/no 的 logit 差，不是 embedding 余弦，也不直接作为正确概率。不能套用当前检索的 0.5 余弦阈值；后续 H 单独决定重排策略。

## 本机小输入结果与资源边界

[模型烟测](Q06_5C_RUNTIME.json) 在实际主机执行，MPS built/available 均为 true。受限工具环境曾报告 MPS unavailable，因此不能把受限环境检测当作主机硬件结论。CPU 始终完成参照计算；设备选择在 MPS 不可用时返回 CPU 并记录原因，运行时设备错误的 CPU 回退路径另有单元测试。

合成输入为一个中文问题与两条短英文文本，不读取领域文献作候选质量比较。显式输入上限设为 512 tokens，但实际 embedding 长度为 30/16/10，reranker 全模板为 96/90；模型报告的原上限均为 32,768。此次没有验证 512-token 满长度、32k 长度、大批量或并行加载。

| 项目 | Embedding | Reranker |
|---|---:|---:|
| 输出形状 | 3 × 1024 | 2 个分数 |
| CPU FP32 batch 1/2 一致性 | 通过 | 通过 |
| MPS FP32 相对 CPU 最大绝对差 | 3.24e-7 | 3.15e-5 |
| MPS FP16 相对 CPU 最大绝对差 | 2.62e-4 | 4.68e-3 |
| 进程 RSS 高水位 | 约 2.75 GiB | 约 3.83 GiB |

MPS 两种精度均返回有限值，且合成相关文本分数高于无关文本。这里的误差只是短输入数值检查，不证明近似精度对领域排名无影响；未来 E/H 仍需实测。CPU batch 1/2 已实际运行，MPS 本次只运行 batch 2。记录的耗时包括一次小输入计算，没有控制预热/缓存，不据此作加速收益结论。

RSS 是同一串行进程的高水位，包含库、分配器和此前模型操作；不能视为单个模型的纯内存需求。Apple 统一内存下也不能简单把 RSS 与 MPS allocated/driver allocated 相加。详细分配量和耗时保存在 JSON。后续从 batch 1、受控输入长度起步，依据真实资源记录逐步增加；本项未启用量化，也未决定生产使用 FP16。

## 旧模型与索引兼容性

[旧模型检查](Q06_5C_LEGACY.json) 在候选环境使用 CPU 重编码 Q10-A 的 20 个固定开发查询：与原保存查询向量最大绝对差为 0，20 题 Top-10 排名全部一致，128-token 上限及特殊 token 口径一致。原模型 revision 保留，原 26,025 行索引没有重编码或写入。

这证明本次固定查询上的运行兼容性，不构成任意输入、平台或精度下的逐位一致保证。历史 Q06.5-A、Q10-A 和 Q06.5-B 记录保留；旧默认模型也没有因候选模型成功加载而自动替换。

## 重复验证与回退

```bash
uv sync --locked
uv run --locked python -m unittest discover -s tests -q
uv run --locked ruff check .
uv run --locked ruff format --check .
# 需要联网，只下载固定公开资产；保留官方 Jinja 模板，不发送文献
HF_HUB_DISABLE_XET=1 uv run --locked python -m scripts.validate_q065c --download --report output/q065c_download.json
# 缓存准备好后离线执行；--device cpu 可明确限制为 CPU
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065c --report output/q065c_runtime.json
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065c --device cpu --report output/q065c_cpu.json
# 需要既有 Q10-A 检索运行目录及兼容索引
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065c --legacy --report output/q065c_legacy.json
```

设备错误的回退不会吞掉输入错误或 CPU 错误；回退原因与实际执行设备分别记录。`--download` 需要安装完整新版依赖，普通烟测只读取缓存，不访问生成 API。

采用前的 `pyproject.toml`、`uv.lock`、`requirements.txt` 保存在忽略的 `output/q065c_candidate/prior/`。需要回退时恢复这三份文件，再 `uv sync --locked`；这只回退依赖，不改文献、模型 revision 或索引。旧环境/原参照的更完整恢复仍见 Q06.5-A 记录。候选环境及下载权重不放入 Git。
