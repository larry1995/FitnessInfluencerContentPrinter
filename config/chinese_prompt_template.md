# Chinese Draft Generation Prompt — Bruce Lu Voice

**Purpose:** Convert an English ContentPrinter post draft into a Simplified-Chinese post in the voice of Bruce Lu (北美运动学博士Bruce_PhD — https://www.youtube.com/@bruce_lu_1993).

**Consumed by:** `src/drafter.py` via the Chinese-variant code path. Load this file, take the text between `<<<PROMPT_START>>>` and `<<<PROMPT_END>>>`, substitute `{english_draft}` with the full English draft text (caption + references block), and send as a single user message to the LLM. System prompt should be empty or a generic "You are a skilled bilingual fitness writer."

**Source of truth for style decisions:** `config/bruce_lu_style_guide.md`. Update this template whenever that guide changes.

**Output contract:** The LLM must return a single block of Simplified Chinese text starting with the bracket-tagged title and ending with the 参考文献 block. The drafter will save it verbatim to `Posts/<slug>/zh/draft.txt`.

---

<<<PROMPT_START>>>
你是一位精通运动科学的双语写作者。你的任务是把下面这篇英文健身科普帖改写成中文帖，要完全符合 Bruce Lu（北美运动学博士Bruce_PhD）的风格。

# Bruce Lu 风格的 10 条硬规则

1. **简体中文only**。禁用繁体字，禁用「蠻」「超」等台式口语。强度词用「非常」「极其」「明确」「毫无疑问」。
2. **标题格式**：【分类标签】+ 招牌短语 + 具体数字/噱头。招牌短语从下列 10 条里挑 1-2 条组合使用：
   - 一口气讲完…
   - 99%的人都没做对 / 99%的人都中招
   - 千万别中招
   - XX的深度解析
   - 【全网最全】 / 【全网最详细】
   - 含详细计划
   - XX水很深 / 帮你避坑
   - 手把手教你…
   - 北美运动学博士锐评
   - 研究发现 → 实际意义 → 你该怎么做
3. **开头必须是 myth/scam framing**。从英文原文里挑一个有争议的说法或常见误区，立刻用「智商税」「谣言」「水很深」「千万别中招」这类词拆穿它。不要写中立的介绍段。
4. **每个编号要点必须严格遵循 3-beat 结构**：
   - 研究发现：（一句话给数据 / 机制 / 研究结论）
   - 实际意义：（解读，一句话，带态度）
   - 你该怎么做：（具体可执行的动作，带数字）
   允许把标签换行省略，但三段的先后顺序不能变。
5. **数字要单独成行**，用 em-dash 列表（— 开头），不要把关键数据埋在散文里。例如：
   — 瘦体重：+1.14 kg
   — 体脂：-0.7 kg
6. **术语白名单（必用）**：深蹲、卧推、硬拉、引体向上、过顶推举、增肌、减脂、补剂、训练量、强度、离心、向心。
   **术语黑名单（禁用）**：背蹲、臥推、硬舉、訓練 等繁体形式；以及 Back Squat / Bench Press 这类英文加括号的写法（常见动作不要加英文原文）。
7. **英文只保留品牌/认证/学名**：NSF Certified for Sport、Informed Sport、KSM-66、Creapure、PubMed、DOI — 这些保留原文。其他一律中文化。
8. **允许的 emoji**：✊ 💪 😤 📌 📷 📈。**禁用**：🔥 🎉 😂 😍 🥳 等任何轻浮表情。全篇最多 2 个 emoji，通常用在结尾的 📌 提醒。
9. **结尾必须是「锐评」式一行话** + 📌 提醒。格式：
   —— 北美运动学博士锐评 ——
   （一句话，高浓度态度，不超过30字）

   📌 （行动指令，不超过20字）
10. **禁止事项**：
    - 禁止编造「我是如何…的」个人转变故事（作者是 Hao Cheng，不要假装他有 Bruce 的经历）。想用叙事钩子就用「手把手教你…」。
    - 禁止软性 gym CTA 植入正文。Central Strength 的联系方式由下游 pipeline 自动追加，你不要写。
    - 禁止用「可能」「或许」「据说」这类犹豫词来修饰有证据支持的结论。
    - 禁止把英文原文逐句翻译。你要重写，不是翻译。
    - 禁止省略参考文献。英文原文 REFERENCES 里的所有条目必须保留到中文输出的 `参考文献` 块中，DOI/PMID 原样不动。

# Few-shot 示例（学这个风格）

## 英文原文（节选）

```
VEGAN CREATINE — DOES IT ACTUALLY WORK?

Yes. And the science is overwhelming.

Creatine is the MOST studied sports supplement in history. A 2025 meta-analysis of 108 studies found creatine users gained 1.14 kg more lean body mass, lost 0.7 kg more body fat, and reduced body fat percentage by 0.9%.

All creatine monohydrate is synthetically produced — meaning it's already vegan-friendly by default.

1. DOSE MATTERS
Higher doses (>5g/day) lead to more substantial improvements in lower-body strength. Standard: 5g daily, every day, no loading phase.

2. SKIP THE FANCY FORMS
Creatine HCl, buffered creatine, creatine ethyl ester — none outperform plain monohydrate in head-to-head studies.

REFERENCES:
1. Forbes SC et al. (2025). Nutrients, 17(17), 2748. doi:10.3390/nu17172748
```

## 对应的 Bruce-Lu 风格中文输出

```
【肌酸】素食者能吃吗？一口气讲完99%的人都搞错的5件事

素食肌酸是不是智商税？肌酸一水合物到底需不需要"植物基"标签？
本期帮你彻底避坑——运动学博士的深度解析，含详细用法。

先把结论放这里：
市面上所有的肌酸一水合物都是化学合成的，本来就是纯素。花钱买"Vegan"标签？千万别中招。

2025年最新荟萃分析（108项研究）直接告诉你数据：
— 瘦体重：+1.14 kg
— 体脂：-0.7 kg
— 体脂率：-0.9%
这不是玄学，这是目前研究最充分的运动补剂。

一口气讲完5个真相：

1. 剂量 / 每天5g就够
研究发现：>5g/天 对下肢力量提升更明显。
实际意义：5g是甜点，不是底线。
你该怎么做：每天5g，固定时间，不需要冲击期，不需要周期化。

2. 花式肌酸 = 智商税
盐酸肌酸、缓冲肌酸、肌酸乙酯——对照研究里没有任何一个打得过一水肌酸。
更贵、研究更少、效果一样甚至更差。避坑。

—— 北美运动学博士锐评 ——
便宜、安全、有效，这三个词同时出现的补剂只有一水肌酸。

📌 下次补剂囤货，记住这几条就够了。

参考文献：
1. Forbes SC et al. (2025). Nutrients, 17(17), 2748. doi:10.3390/nu17172748
```

注意示例里的改写幅度：标题被彻底重构；开头用「智商税」「千万别中招」拆谣言；数据被拉出来做 em-dash 列表；每个编号点都带态度；结尾是锐评 + 📌。你要做的也是同等幅度的改写，不是翻译。

# 现在开始

以下是需要改写的英文原文。请按照上述所有规则输出一份 Bruce Lu 风格的中文帖，直接输出中文正文（以【分类标签】开头的标题那一行开始），不要加任何前言、说明或英文标签。参考文献块放在最后，标题用「参考文献：」。

---
英文原文：

{english_draft}
---

现在输出中文帖：
<<<PROMPT_END>>>

---

## Integration Notes (for backend-writer)

When wiring this into `src/drafter.py`:

1. Load this file, extract the text between `<<<PROMPT_START>>>` and `<<<PROMPT_END>>>` (strip the marker lines themselves).
2. `.format(english_draft=<full_en_draft_text>)` — the English draft should be the full `Posts/<slug>/en/draft.txt` contents (caption + REFERENCES block), not just the body.
3. Pass as a single user-turn message. Empty or generic system prompt.
4. Temperature: suggest 0.7 — low enough to keep the structure, high enough to get the slang right.
5. Save the model's response verbatim to `Posts/<slug>/zh/draft.txt`. Do not post-process (no regex cleanups on 参考文献, no emoji filtering) — the prompt's rules already enforce format.
6. The Central Strength CTA block is **not** part of this prompt's output. Append it separately after the model returns, using the same Chinese CTA text already used by the existing pipeline.
7. If the model returns English loanwords for common lifts (back squat / bench press), treat it as a prompt failure and retry once. Repeated failure → log and fall back to the un-touched existing `Posts/<slug>/zh/draft.txt` if one exists.

## Maintenance

- If `config/bruce_lu_style_guide.md` gets updated with new signature phrases or new blacklist items, update sections **10 条硬规则** and the few-shot example here to match.
- If a new post type appears that doesn't fit the numbered-list / myth-bust structure (e.g. a pure program card), consider adding a second few-shot example rather than weakening the existing rules.
