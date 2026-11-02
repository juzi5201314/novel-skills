---
name: novel-core
description: 网文项目的目录约定、文件格式、章节命名、设定文件模板、memory 连续性台账同步规程，以及 novel.py 工具（建目录/下一章/字数统计/格式与AI味检查/正文检索/整本切章）。凡是在小说项目里读写正文、设定、大纲、伏笔、摘要文件，或者要知道“某个东西该放哪、该怎么写格式”，都先读这个技能；其它 novel-* 技能都依赖它。
---

# 网文项目约定

**自动化机制**：详见 `AUTOMATION.md`。所有 novel-* 技能按该文档的机制运行：透明工具调用、智能上下文加载、Memory 自动提取、自动补同步检测、AGENTS.md 自动归档、技能间协作。用户只需专注自然语言对话，幕后工作由 agent 自动完成。

这套约定的目的只有一个：让任何一次会话里的 agent 都能用最少的读取量，拿到写下一章所需的全部上下文，并且不写出与前文矛盾的东西。长篇网文动辄几百万字，没人能把全书塞进上下文，所以“该知道的事”必须落在固定位置的小文件里。

## 目录结构

书根目录就是项目根目录（一本书一个仓库）。

```text
AGENTS.md                    # 每次会话自动注入：作品档案、文风、硬规则、目录索引、当前进度
CLAUDE.md -> AGENTS.md       # 软链接，给 Claude Code 用
chapters/
  vol01/0001-初入洪荒.txt     # 正文，纯文本
outline/
  synopsis.md                # 总纲
  volumes/vol01.md           # 卷纲
  chapters/0001.md           # 章纲
lore/
  world/修炼体系.md           # 世界观：力量体系、地理格局、历史、种族、规则
  characters/鸿钧.md
  locations/不周山.md
  factions/巫族.md
  items/造化玉碟.md
  images/鸿钧-立绘.png
  glossary.md                # 术语与专名表
memory/
  state.md                   # 当前状态快照
  threads.md                 # 伏笔与暗线台账
  timeline.md                # 故事内时间线
  summaries/vol01.md         # 逐章摘要，一卷一个文件
drafts/                      # 草稿、互动写作记录、审稿报告、检索笔记
```

新建项目用 `novel.py init`（见下文），不要手工逐个建。

## 命名

- 目录名用英文，实体文件名用中文专名：`lore/characters/鸿钧.md`。文件名就是 glossary 里的标准写法。
- 章号全书连续、四位补零，不随卷重置：`chapters/vol02/0153-紫霄宫听道.txt`。章纲与之对应：`outline/chapters/0153.md`。
- 章名里不放空格和 `\/:*?"<>|`。
- 设定图：`lore/images/{实体名}-{用途}.png`，用途如 立绘、地图、法宝。

## 正文格式（chapters/*.txt）

正文是要直接复制到网文平台的成品，所以里面只能有读者该看到的字。

- UTF-8 纯文本。第一行 `第N章 章名`（阿拉伯数字或中文数字均可，全书统一），空一行后是正文。
- 段落格式以 AGENTS.md“正文格式”一栏为准，全章统一。没写时默认：段首两个全角空格，段间空一行。
- 全角中文标点。引号用“”，引号内再引用用‘’；省略号“……”；破折号“——”。
- 禁止任何 Markdown 记号（`#`、`**`、`-` 列表、`***`/`---` 分隔线）、作者按语、括号注释、“（本章完）”、字数说明。
- 场景切换默认靠转场句或空行另起。本书若要分隔符，用非 Markdown 符号（如单独一行“◇”）并写进 AGENTS.md 硬规则。
- 对白独立成段。一段话只属于一个说话人。

## 设定文件格式（lore/**/*.md）

一个实体一个文件，模板在本技能 `assets/templates/`：

| 类型 | 模板 | 目录 |
|---|---|---|
| 角色 | character.md | lore/characters/ |
| 地点 | location.md | lore/locations/ |
| 势力 | faction.md | lore/factions/ |
| 物品/功法/丹药 | item.md | lore/items/ |
| 世界观体系 | world.md | lore/world/ |
| 卷纲 | volume.md | outline/volumes/ |
| 章纲 | chapter-outline.md | outline/chapters/ |

规则：
- 文件开头是 YAML frontmatter，`name` 和 `aliases` 必填。`aliases` 写全所有称呼（称号、外号、尊称、昵称），`novel.py find --entity` 靠它检索。
- 正文用 `[[实体名]]` 引用其它实体，用四位章号 `0012` 引用章节。
- 模板里用不上的小节直接删掉，不要填“暂无”“待定”凑格式。空小节比没有小节更误导人。
- “秘密/隐藏设定”小节是作者视角，写真相；读者已知到什么程度记在 memory/threads.md。
- lore 存的是相对固定的设定。境界、伤势、位置、持有物这些每几章就变的东西放 memory/state.md，lore 里只在设定本身改变时才改。这样状态只有一个来源，不会两边不一致。
- 新专名先登记到 lore/glossary.md 再写进正文。

## memory/ 连续性台账

这四个文件是防止前后矛盾的主要手段。审稿（novel-review）以它们为准。

| 文件 | 存什么 | 写法 |
|---|---|---|
| state.md | 此刻的世界：每个活跃角色的境界、伤势、持有物、位置、目标、**已知秘密** | 覆盖式更新，只保留当前值 |
| threads.md | 每条伏笔/暗线：真相、读者已知程度、计划回收点、不可违反的约束、推进记录 | 追加记录，回收后移入“已回收” |
| timeline.md | 故事内时间、事件、地点 | 追加一行 |
| summaries/volNN.md | 每章 3–6 行事实摘要 | 追加一节 |


### 定稿后同步规程

一章定稿（用户确认）后，按顺序做：

1. `memory/summaries/volNN.md` 追加本章摘要（格式见该文件头部）。
2. `memory/state.md` 更新本章改变了的字段，改“截至”。
3. `memory/threads.md`：本章埋设/推进/回收了哪条，追加记录；新伏笔新开编号（T001 起递增）。
4. `memory/timeline.md` 追加本章事件。
5. 新出场的有名角色、地点、势力、物品：在 lore/ 建最小条目（frontmatter + 一句话 + 已在正文中出现的事实），登记 glossary。
6. `outline/volumes/volNN.md` 章节表把本章状态改为“定稿”。
7. 更新 AGENTS.md“当前进度”。

只写正文里真实发生的事，不要把章纲里计划了但没写进正文的内容同步进去。

## 读取预算

写一章需要的上下文（按优先级）：AGENTS.md（已注入）→ 本章章纲 → memory/state.md → memory/threads.md 中“进行中”的条目 → 最近 3 章摘要 → 上一章最后 1500 字左右 → 本章出场实体的 lore 文件。

不要为了“保险”通读几十章正文。需要查前文细节时用 `novel.py find` 精确定位，再读命中位置附近。大范围梳理交给 novel-explore 技能。

## novel.py 工具

路径：`.agents/skills/novel-core/scripts/novel.py`，只依赖 Python 3 标准库，在书根目录运行。

```bash
N=.agents/skills/novel-core/scripts/novel.py
python3 $N init                               # 建目录 + 种子文件（已存在的不覆盖），并建 CLAUDE.md 软链接
python3 $N next                               # 下一章章号、建议路径、章纲是否存在、上一章路径
python3 $N stats --min 2000 --max 3000        # 每章字数，越界标记；--range 1-50 限定范围
python3 $N lint chapters/vol01/0001-x.txt --min 2000 --max 3000
python3 $N find --entity 鸿钧                  # 按 name + aliases 检索所有正文
python3 $N find 紫霄宫 造化玉碟 --range 1-80 --count
python3 $N find 鸿钧 --first                   # 首次出现在哪一章
python3 $N find --all 混沌钟                   # 连 outline/ lore/ memory/ 一起搜
python3 $N split 旧稿.txt --dry-run            # 整本 txt 按“第X章”切成标准章节文件
```

- 字数口径：去掉所有空白后的字符数（含标点），接近主流平台后台的统计。
- `lint` 有错误时退出码为 1。错误是硬格式问题，必须改；警告和 AI 味命中是提示，结合语境判断（判断方法见 novel-craft 技能）。
- `split` 识别“第X章/第X回”标题行和“第X卷”分卷行，卷首语等非章节文字存到 drafts/import-extras.txt。目标文件已存在时整体拒绝写入。
