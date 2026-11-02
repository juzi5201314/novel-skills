<!--
本文件每次会话都会自动注入给 agent（CLAUDE.md 是指向它的软链接）。
只放"每次写作都必须知道"的机制与索引，控制在 150 行内；细节放 lore/ outline/ memory/，这里只留指针。
由 novel-init 生成并持续更新；"当前进度"由 novel-chapter 在每章定稿后更新。
「规则」节是 novel.py 的编译产物（源：本书 rules/ 与全局 ~/.novel-skills/rules/），块内不要手改。
不预设作品内容：类型、文风、主角、力量体系等由用户决定后补写，不要替用户默认。
-->
# 《{书名}》

## 作品信息

| 项 | 内容 |
|---|---|
| 书名 | {书名，可暂定} |
| 简介 | {一句话描述这个故事} |
| 正文格式 | {段首两个全角空格缩进 / 不缩进}，段间{空一行 / 不空行} |

<!-- 以下字段按需补充，写不下或不适用就删掉：
| 视角 | {第三人称限知 / 第一人称 / 多视角} |
| 每章字数 | {下限}–{上限} 字（统计口径：去空白字符数） |
| 文风 | {预设名，见 novel-craft references/styles.md；或自定义描述} |
| 内容尺度 | {清水 / 含蓄亲密 / 成人向}；{绝对不写的边界} |
| 平台/频道 | {目标平台、男频/女频等} |
| 更新节奏 | {如 日更两章} |
本书特有的其他档案字段（主角速查、核心设定速查等）也可自行加节，建议指向 lore/ 而非复制内容。
-->

## 硬规则

写任何正文前必须遵守。快捷条目写在这里；要跨书共享或按场景生效的写成 rules/*.md（见下方「规则」节）。
（待补充）

<!-- novel:rules -->
## 规则

（暂无规则文件。在本书 rules/ 或全局 ~/.novel-skills/rules/ 放 .md，可选 frontmatter：scope 默认 always，可选 writing/review/lore；priority 默认 0。由 novel.py 编译到这里。）
<!-- /novel:rules -->

## 设定分类

本书的设定分类注册表：lore/ 下的分类以此为准，用 `novel.py category` 增删。
每个分类目录里的 `_schema.md` 是该类的字段模板；字段不限层数，用户说了算。

| 分类 | 目录 |
|---|---|

## 目录索引

| 路径 | 内容 |
|---|---|
| chapters/volNN/NNNN-章名.txt | 正文，纯文本 |
| chapters/volNN/NNNNx-章名.txt | 番外（x=a-z，锚在第 NNNN 章后） |
| outline/synopsis.md | 总纲 |
| outline/volumes/volNN.md | 卷纲 |
| outline/chapters/NNNN.md | 章纲（写章前的骨架） |
| lore/ | 设定，一实体一文件；分类目录见上方"设定分类" |
| lore/glossary.md | 术语与专名表，所有专名以此为准 |
| lore/images/ | 设定图 |
| memory/state.md | 当前状态快照：人物实力、位置、伤势、持有物、谁知道什么 |
| memory/threads.md | 伏笔与暗线台账 |
| memory/timeline.md | 故事内时间线 |
| memory/summaries/volNN.md | 逐章摘要 |
| drafts/ | 草稿、审稿报告 |
| rules/ | 本书规则文件（.md），编译进上方「规则」节；全局共享放 ~/.novel-skills/rules/ |

## 工作流

- 写章节 → novel-chapter；审稿 → novel-review；建/改设定 → novel-lore；检索梳理 → novel-explore。
- 写正文前必读：本文件、memory/state.md、memory/threads.md、相关章纲、最近 3 章摘要、上一章末尾。
- 每章定稿后同步 memory/（规程见 novel-core 技能）。

## 当前进度

- 最新章节：（未开始）
- 当前卷：（待定）
- 下一章计划：（待定）
