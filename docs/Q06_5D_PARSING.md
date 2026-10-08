# Q06.5-D：页级解析抽样与采用决定

日期：2026-10-07。

**决定：继续采用现有 PyMuPDF `get_text("text", sort=False)` 作为 Q06.5-E 的原文来源。Docling 保留为独立实验，不加入主环境、不改默认解析、不启动全库 OCR。**

本轮完成工程抽样和助手视觉核查；研究者人工复核仍待进行。以下是对选定页面和配置的观察，不能推断全库解析准确率或问答质量提升。当前解析也有阅读顺序与图式信息缺失，保留决定不表示这些问题已解决。

## 范围与复现

在 Docling 执行前冻结 [10 篇文献、每篇 1 页的样本](Q06_5D_SAMPLE.json)。样本来自开发文献目录，覆盖 ACS、Nature Communications、Wiley 的双栏正文、跨栏图注、优化表与结构式图表；没有使用预留问题调参。每个样本记录 PDF 字节身份和物理页码。

只读扫描 181 个文件共 1,938 个物理页，以“提取文字少于 80 字符且存在嵌入图像”为启发式条件，候选为 0；这不证明全库不存在扫描或图像文字。另将 Kawajiri 第 2 页渲染为 144 dpi PNG，单独运行本机 Vision OCR 对照，不冒充真实扫描样本。

隔离依赖见 [固定版本清单](../config/q065d_requirements.txt)，公开模型固定 revision 见 [模型配置](../config/q065d_models.json)。主项目依赖与默认配置未变。Docling 使用 CPU、1 线程、标准 PDF pipeline、TableFormer accurate、表格单元格匹配；原生 PDF 关闭 OCR，图像对照开启 OcrMac 英文全页 OCR。远程服务关闭，不启用公式/代码增强、图片描述或生成模型。

```sh
# 在仓库根目录；保留独立环境，避免覆盖主环境。
uv venv --python 3.12 output/q065d_candidate/.venv
uv pip sync --python output/q065d_candidate/.venv/bin/python config/q065d_requirements.txt
HF_HUB_DISABLE_XET=1 HF_HOME=models/huggingface \
  output/q065d_candidate/.venv/bin/python -m scripts.validate_q065d --download
HF_HUB_OFFLINE=1 HF_HOME=models/huggingface \
  MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/chemqa-matplotlib \
  output/q065d_candidate/.venv/bin/python -m scripts.validate_q065d
```

下载步骤只获取公开依赖/权重，不发送文献。实际解析在本机离线运行，生成 API 请求数为 0。每次输出到新的 `output/q065d_parsing/<run>/`；完整路径、耗时、版本、权重文件校验和及原索引前后校验和见 [运行记录](Q06_5D_RUNTIME.json)。每页保存原页 PNG、PyMuPDF 原文、Docling Markdown/JSON、独立位置匹配和运行结果。PDF 原件不修改。

## 页级视觉核查

助手逐页查看了全部 10 张原页图，并与两种文本及结构化结果核对。这里记录可观察的差异；不是研究者签字的科学标注，也没有把“转换 success”当作内容验收通过。

| 文献与物理页 | 版面/阅读顺序 | 表格、科学字符与条件核查 | 本页结论 |
|---|---|---|---|
| Kawajiri，p2 | 图 1 → 双栏正文，左栏嵌表；两者均把左栏表插入跨栏延续的条件段，不能直接视作连续条件 | Docling 将 14 行优化数据结构化，首行产物 93、无 NaOMe 行 79/15 保留；正文 20 mA、TFE 0.7 mL 保留。反应结构图仍作为图片 | 表格组织有益，条件段仍被表打断 |
| Jiang，p2 | 两幅跨栏图和图注，下方双栏；Docling 正文按左右栏衔接 | 正文/图注中的 CO2、β-Ni(OH)2、pH=14 可见；图内坐标轴与催化剂图例未成为完整正文证据 | 图注可用，图内信息仍依赖原图 |
| Li，p5 | 4 面板跨栏图、跨栏图注及双栏正文；Docling 将部分面板字母/坐标独立为文本，图注仍分块 | HCOO− 在 Markdown 中变为 `HCOO -`，上下标变为基线；正文的 500、1000 mA cm−2 和 3.5 V 保留，图内曲线/坐标未完整提取 | 没有通过化学式原样保留要求 |
| Lu，p2 | 左栏 Scheme 1，右栏优化表；Docling 把表下注释接入左栏段落，脚注关系仍需处理 | Docling 得到 17 行数值表：标准 75、7 mA/6 h 为 68、3 mA/13 h 为 71，与原图所查行一致；反应结构图不转化为分子数据 | 表格有益，脚注/段落顺序不宜直接投产 |
| Huang，p3 | 页顶跨栏优化表，下方双栏；PyMuPDF 原文先正文后表，Docling 将表放到页首，较符合视觉版面 | Docling 得到 9 行数据：标准 84、75 °C 为 65、65 °C 为 63；CH3OH/CH3CN 转为基线数字，反应图仍为图片 | 这页表序改善，但字符映射仍需独立验收 |
| Liu，p2 | 密集双栏正文；Docling 将段落去换行，左右栏主体顺序与原图一致 | 1.484、1.625 V，500/1000 mA cm−2、98.5% 保留；单位指数表现为 `cm -2`，长段无法直接匹配原文连续字符 | 数值可读，不能沿用旧原文偏移 |
| Song，p4 | 页顶标作 Table 1 的底物结构图，下方脚注与双栏正文 | Docling 将底物结构区域识别为图片，未产出 table cells；原 PyMuPDF 也未完整提取结构图内的编号—产率关系 | 明确失败样例：标题含 Table 不等于可提取数值表 |
| Lin，p2 | 大幅机制/装置图，跨栏图注及短双栏正文 | Docling 输出图注和部分标签，但图中的挑战/优势列表及电极说明未完整成为文本；原 PyMuPDF 也存在布局碎片 | 无证据支持自动图式迁移 |
| Han，p2 | 双栏正文、底部 TEM 多面板与图注 | 正文 `>92%`、0.475 mmol cm−2 h−1、20 cycles 保留；Markdown 将 `>` 编码为 `&gt;`，单位指数基线化；显微图标尺不能视为完整文字证据 | 条件可核对，单位/图内信息仍需保护 |
| Fan，p2 | 密集双栏，右边缘有下载水印；Docling 仍将水印纳入 text | 232 mA cm−2、85.7%、H2 的 100% FE 保留；`Ni2P@Ni12P5` 变为 `Ni 2 P@Ni 12 P 5`，不能将其作为原样引用 | 科学检索可另做派生规范化，原文不能被改写 |

这些表格行仅为局部人工视觉比对，不构成全部单元格准确率。化学结构、图形坐标和上下标问题需要分别处理，不能通过文本长度比较得出质量结论。

## 位置映射与失败约定

现有 Q02/Q10-A 位置基准是 PyMuPDF 页面原文的字符区间。Docling 的 `prov.page_no`、bbox 和 `charspan` 保存在实验产物里；**其 charspan 属于 Docling item，不能当作旧原文字符偏移。** 多个 bbox 归属同一文本 item 时保留在同一记录，避免重复计算文字块。

10 个原生页面均返回 conversion success，输出 3 张结构化表。76 个文本 item 中，14 个能够直接逐字符唯一匹配旧原文；其余需要规范化诊断、消歧或新的多区间映射。所有导出 item 的页号与框范围检查通过，但新解析器尚未通过引用位置迁移验收。汇总、逐项失败与权限对照见 [核查记录](Q06_5D_REVIEW.json)。

本轮只接受在同一原始页面中出现一次的**逐字符相同**文字块作为直接可用的原文区间。重复数值标为 ambiguous；NFKC/去空白能匹配的情况仅标为诊断匹配，不生成原文偏移。不能匹配的块继续保留失败状态，不猜测位置。该比率衡量直接迁移兼容性，不衡量解析正确率；更完整的 bbox/词级多区间对齐尚未实现。

Docling 页面和框范围检查仅确认物理页号与框在页面内，不证明每个框覆盖正确文字，也不证明引用原文连续。完整迁移需要处理去换行、连字符、脚注、表格重复值、跨栏段落及新旧片段身份，并重新验收原文跨度。

OCR 的首次受限环境执行返回 success，却没有正文或非空单元格；在完整本机权限下离线复跑后恢复文字。这说明不能把受限环境结果直接归因于 OCR 模型能力。完整权限下仍观察到表格行号 5 → S、部分行号漏失、LiOMe 行的残余底物值 2 漏失、表头脚注乱码及化学式错误。因此记录为“可运行、内容验收未通过”，不默认开启 OCR，也不外推到其他引擎或真实扫描件。

单次完整权限运行中，10 页 Docling 合计约 6.99 s（首页面约 3.05 s，其余页面中位约 0.326 s），PyMuPDF 的 get_text 合计约 0.109 s，图像 OCR 约 27.56 s。两种计时范围不同、缓存与启动也不同，仅作本机资源观察，不能作为严格速度比较。

## 工程验证

144 项离线回归、Ruff 检查与格式检查通过，当前源码密钥模式审计为 0 命中。两次本地执行的 10 页原生 Docling Markdown 校验和全部一致；这仅验证本轮产物稳定，不表示内容正确。主依赖、默认配置、旧 processed/index 与 HEAD 的字节一致。详见 [验证记录](Q06_5D_VALIDATION.json)。

## 后续边界

Q06.5-E 可以继续，以现有 PyMuPDF 原文为固定来源，对比 embedding 与分块方案；这轮的 Docling 输出不进入默认检索索引。若后续确有表格召回需求，再单列解析迁移：原文与派生结构分离、bbox/词级跨度对齐、脚注与图式专项验收、研究者复核、新解析产物冻结，然后重新编码。不要在 E 中顺带更换解析器。

参考：[Docling pipeline 配置](https://docling-project.github.io/docling/reference/pipeline_options/)、[本机 OCR 选项](https://docling-project.github.io/docling/concepts/OCR/)、[全页 OCR 示例](https://docling-project.github.io/docling/_generated/examples/full_page_ocr/)。本机实际版本与固定权重以运行记录为准。
