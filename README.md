# Standard Answer Harness

面向授课教师(和像我一样想偷懒bushi)的**“课件口径标准答案”本地 harness和app（测试中）**。它把 PDF / Word / PPT 课件解析成课程知识库，按题目检索课件证据，再生成或辅助生成标准答案——并且在生成前先**诚实地判断课件到底能不能支撑这道题**。

它最大的特点不是“能答题”，而是**不会把模型自己的先验冒充成课件标准答案**。证据不足时它会明说；AI 可以补全，但必须告诉用户“这部分可能与资料不一致，非课件直接依据”。
(主要是防被查到用了ai🥺，由于ai可能存在的防止学生偷懒的限制，你可以装作老师...）
事实上，你可以直接告诉agent让它帮你安装....

For instructors (and those who want to slack off like me, just kidding), a local **“courseware answer key” harness**, along with an app (in testing). It parses PDF/Word/PPT courseware into a course knowledge base, retrieves courseware evidence based on the question, and then generates or assists in generating standard answers — while **honestly assessing whether the courseware can actually support the question** before generation.

Its biggest feature is not “being able to answer questions,” but rather **not passing off the model’s own priors as the courseware answer key**. When evidence is insufficient, it will state that clearly; AI can fill in the gaps, but must tell the user “this part may not be consistent with the materials and is not directly based on the courseware.”
(Mainly to avoid getting caught using AI 🥺. Given the possible restrictions AI has to prevent students from slacking off, you can pretend to be a teacher...)
In fact, you can just tell the agent to help you install it.

---

## 为什么需要它

老师批改作业要的是“按我课件的口径”，而不是“一个看起来很专业的通用答案”。常见的 AI 答题工具有两个隐患：

1. 课件是扫描版 / 公式在图片里时，文本层几乎是空的，工具却照样输出一份自信满满的答案，假装有课件依据。
2. 公式题里，模型用的是自己训练时的公式，未必和课件的变量名、记号、推导步骤一致，但输出里看不出来。

这个 harness 用一套**可机器校验的接地度契约（grounding contract）**来堵住这两个口子。

---

## 安装

```bash
pip install -r requirements.txt
```

- 核心依赖：`python-docx` / `python-pptx` / `pdfplumber` / `PyPDF2`
- `PyMuPDF` / `Pillow` 用于渲染 PDF 页图和 contact sheet。
- `openai` 是可选的：不装也能用 `build` / `diagnose` / `inspect` / `answer` 的**离线检索模式**，只是 `answer` 不会在工具内部调用模型生成连贯答案，而是给出“课件证据草稿”。用户也可以把草稿、页图和诊断结果直接交给自己的 agent 继续处理。
- `pytesseract` 只是 OCR 接口；本机还必须安装 Tesseract 可执行程序。没有 OCR 引擎时，harness 会明确提示不可用，不会假装识别成功。

---

## 核心原则

- **课件是第一标准。** 答案必须沿用课件里的公式、变量名、术语、步骤和作答格式。
- **联网/外部资料只能补充，不能覆盖课件口径。**
- **证据不足时明确标注。** AI 可以加入自己的推导和想法，但必须说明“可能与资料不一致”，不能伪装成课件原文。
- **每题必须先复述题目。** 输出不能只给答案，避免脱离题干或答非所问。
- **四类来源必须分清：** `[自动抽取]` / `[页图核对]` / `[外部资料]` / `[模型推导]`。

---

## 核心命令

## 本地极简 App

启动：

```bash
python -m streamlit run app.py
```

如果在项目根目录运行：

```bash
python -m streamlit run standard_answer_harness/app.py
```

浏览器打开本地地址后可完成：

- 上传 PDF / DOCX / PPTX / TXT / MD 课件。
- 诊断 PDF 是否为扫描/图片型。
- 生成最后页图和 contact sheet。
- 输入题目。
- 默认使用“交给 agent / 离线证据草稿”模式，不要求用户提供 OpenAI Key。
- 可选填写自己的 API Key / Base URL / Model，调用 OpenAI 或 OpenAI-compatible 服务生成完整答案。

API Key 只在本地 Streamlit 会话中使用，不写入仓库。

重要提醒：

- 如果你处理的是扫描 PDF、截图、页图核对等视觉任务，请选择**支持图片输入的模型**。
- 如果模型只支持文本输入，它只能处理 harness 抽取到的文字，不能理解渲染出来的页图。
- 不想填 key 时，直接使用默认模式，把输出的诊断、contact sheet、页图和证据草稿交给 agent 使用即可。

### 0. `diagnose-pdf` — 先判断 PDF 是文本型还是扫描型

```bash
python harness.py diagnose-pdf --pdf course.pdf
```

它会输出页数、可抽取文字页比例、抽取字符数和判定：

- `copyable-text PDF`：文本层可用，可以继续 `build`。
- `scanned/image-heavy PDF`：文本 harness 不可靠，必须走页图/OCR/人工核对流程。

这是防糊弄的第一道闸门。比如 135 页课件只有 7 页有可用文本、公式数为 0，就不能把模型公式冒充成课件标准答案。

### 0.1. `prep-pdf` — 一键准备扫描 PDF 工作区

```bash
python harness.py prep-pdf \
  --pdf course.pdf \
  --out tmp/pdfs/course_prep
```

自动完成：

- 复制到 ASCII 安全路径，避开中文路径/控制台编码问题。
- 渲染最后 1-3 页。
- 每 12 页生成一张 contact sheet。
- 写出 `prep_manifest.json`，包含页数、文本比例、最后页图片和建议下一步。

### 0.2. `homework-last-page` — 作业常在最后页

```bash
python harness.py homework-last-page --pdf course.pdf --out tmp/pdfs/homework
```

它会渲染最后页并尝试抽取题目文本。若文本层为空，会直接给出最后页 PNG 路径，要求人工核对。可选 OCR：

```bash
python harness.py homework-last-page --pdf course.pdf --ocr
```

没有 Tesseract 时会明确提示 `OCR unavailable`。

### 0.3. `locate-pages` / `ocr-pages` — 只定位和 OCR 关键页

```bash
python harness.py locate-pages --pdf course.pdf --query "Stokes 偏振 推迟势 角分布"
python harness.py ocr-pages --pdf course.pdf --pages 31,32,73-80 --out tmp/pdfs/ocr
```

原则：**不默认全量 OCR**。先定位/人工看 contact sheet，再只 OCR 关键页；这样更快，也减少 OCR 错误污染答案。

### 1. `build` — 构建课件知识库

```bash
python harness.py build \
  --materials course.pptx course_script.docx \
  --out out/course_kb.json
```

解析后会立刻打印**抽取健康度诊断**，包括每个文件“有文字的页数 / 总页数”、抽到的字符数、是否疑似扫描版。如果某个课件大部分页都没文字，会直接警告：文本接地不可靠，请改用页图核对。

扫描 PDF 需要页图证据时，可显式启用渲染：

```bash
python harness.py build \
  --materials course.pdf \
  --render-page-evidence \
  --page-evidence-dir out/page_evidence/course \
  --out out/course_kb.json
```

默认不渲染全 PDF，避免无意中把构建过程变慢。

### 2. `diagnose` — 这份课件到底能不能接地

```bash
python harness.py diagnose --kb out/course_kb.json
```

不重新解析，直接给出整体判定：

- `UNUSABLE`：一个文本块都没抽到。
- `WEAK SHELL`：文本稀疏且零公式，按图片型处理，公式题无法课件接地。
- `PARTIAL`：有文本但零公式，概念题可接地、公式/推导题不行。
- `OK`：文本和公式都有，接地可信（仍需逐题看检索质量）。

**先跑这个，再决定要不要信任答案。** 它能在你浪费时间之前告诉你“这是个空壳知识库”。

### 3. `inspect` — 看抽到了哪些公式和格式规则

```bash
python harness.py inspect --kb out/course_kb.json --limit 20
```

列出自动抽取到的公式候选和作答/格式规则，方便你判断检索质量。

### 4. `answer` — 生成标准答案（或证据草稿）

离线检索模式（不调模型，给教师用草稿）：

```bash
python harness.py answer \
  --kb out/course_kb.json \
  --questions sample_questions.md \
  --out out/answers.md
```

可选：使用自己的兼容 API 在 CLI 内生成完整答案：

```bash
export OPENAI_API_KEY="你的 key"
export STANDARD_ANSWER_MODEL="你的模型名"
python harness.py answer \
  --kb out/course_kb.json \
  --questions sample_questions.md \
  --out out/answers.md
```

这不是必需步骤。也可以不填 key，只生成离线证据草稿，然后交给 agent 继续处理。

> Windows PowerShell 用 `$env:OPENAI_API_KEY="..."`，命令续行用反引号 `` ` `` 而非 `\`。

可选 `--external-context 文件`：传入经核对的拓展资料，会被当作**次于课件**的补充材料。

---

## 接地度契约（这个 harness 的核心）

每道题在作答前都会经过 `assess_grounding`，得出三档判定，并写进答案顶部的“接地度诊断”横幅：

| 接地状态 | 含义 | 输出约束 |
|---|---|---|
| **课件接地** | 证据充足，可优先沿用课件公式与表述 | 在“依据”里列证据编号 |
| **弱接地** | 仅碎片/标题类证据 | 超出部分必须标 `[模型推导]` / `[页图核对]` |
| **未接地** | 仅模型先验，课件无可引用依据 | 允许 AI 补全，但必须声明可能与资料不一致，公式逐条标来源 |

特别地：**公式/推导题 + 知识库公式数为 0 → 直接判未接地。** 因为课件公式很可能在图片/公式对象里，没进文本层。此时仍可给 `[模型推导]`，但必须提醒可能与资料不一致。

### 硬拦截，不是橡皮图章

`compliance_check` 是一个**会失败的契约**，不是走过场。一个“未接地”却没有诚实自标的答案——比如开口就“根据课件，公式为……”——会被**拦截（block）**。但如果明确标为 `[模型推导]` 并说明“可能与资料不一致”，则允许输出。

`_selftest.py` 证明了这个契约真的会拦：

```bash
python _selftest.py
# Case A: 假装有课件依据的自信答案              -> blocked? True
# Case B: 标注 [模型推导] 且说明可能与资料不一致 -> blocked? False
# SELFTEST PASS
```

---

## 输出结构

每道题的输出包含：

- **题目复述**：每道题先复述题干，不能只输出答案。
- **接地度诊断**：接地状态、命中证据块数、证据字数、知识库公式数。
- **标准答案 / 标准答案草稿**：按课件口径作答；离线模式只给检索证据，不编公式。
- **依据**：列出使用的课件证据编号。
- **合规自检 + Harness 合规校验**：脚本侧的拦截/提示/说明，含合规闸门是否通过。

---

## 当前边界

- PPTX / DOCX / PDF 的普通文本、表格文本支持较好。
- **Office 公式、图片公式、扫描版 PDF 默认只抽可复制文本**，抽不到的会被诊断如实标出（`likely_scanned`）。扫描 PDF 要走 `prep-pdf`、页图证据和局部 OCR。
- 检索是轻量词项重叠打分（中文按二元组切分），不是向量检索；对短碎片证据会如实判为“弱接地”。
- 没配模型时只输出“证据草稿”，不会假装完成了复杂推导。

---

