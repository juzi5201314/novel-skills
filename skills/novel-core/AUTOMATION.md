# 自动化增强说明

本文档描述幕后自动化机制，供 agent 调用时参考。

## 核心原则

**用户只说意图，agent 完成所有操作**：
- 用户说"写第 N 章"→ agent 自动读上下文、生成章纲、写正文、检查、保存、同步 memory
- 用户说"审稿"→ agent 自动跑 lint、核对设定、检查伏笔、生成报告
- 用户说"定稿"→ agent 自动同步 8 个地方（含 git 暂存）、更新进度

不需要用户：
- 手动运行 `python3 novel.py lint`
- 手动编辑 memory/state.md
- 手动更新 glossary.md
- 记住要同步哪些文件

**自动化覆盖机械操作**（读写文件、跑检查、同步 memory、git 暂存）和**生成动作**（代拟章纲、列方案、写草稿）——agent 尽管自主生成，但生成的东西不是定论：凡是用户没说过的剧情/设定/走向，标「拟」经用户审核后才落定；用户明确说"我不管/你完全自动"之类的话时免审。上面"生成章纲"这类步骤的完整含义是"自主生成 → 标注生成部分 → 用户审核 → 才写正文"。细则见 SKILL.md「创作主权」。

## 自动化机制

### 1. 透明工具调用

Agent 调用 `novel.py` 时，使用 `_bash` 工具在后台执行，**不在对话里展示命令**，只展示结果摘要。

```python
# ❌ 错误：展示命令给用户
print("运行：python3 .agents/skills/novel-core/scripts/novel.py lint ...")

# ✓ 正确：后台执行，只报告结果
result = subprocess.run([...], capture_output=True)
if result.returncode == 0:
    print("格式检查通过 ✓")
else:
    print("发现 3 处格式问题，已自动修复")
```

### 2. 智能上下文加载

每个 skill 自动判断需要读取哪些文件，**不要全盘读取**。

#### novel-chapter 写章前：
```python
必读：
- AGENTS.md（已注入）
- memory/state.md
- memory/threads.md（"进行中"条目）
- memory/summaries/volNN.md（最近 3 章）
- chapters/volNN/上一章.txt（最后 1500 字）

按需读：
- outline/chapters/NNNN.md（若存在）
- outline/volumes/volNN.md（若首次写该卷）
- lore/（本章出场实体的文件，从 state.md 或章纲获取名单）

不要读：
- 全书所有章节正文
- 所有 lore 文件
- 其它卷的摘要
```

#### novel-review 审稿时：
```python
必读：
- 被审章节
- memory/state.md + threads.md + timeline.md
- lore/glossary.md

按需读：
- 前后各 1 章（检查衔接）
- 相关 lore 文件（按正文提及的实体）
- 章纲（若存在）

自动调用：
- novel.py lint（格式和 AI 味）
- novel.py find（检查实体名一致性）
```

### 3. Memory 自动提取

定稿时，agent 不要"完全依赖自己回忆"，而是**从正文里提取事实**：

```python
def auto_extract_memory(chapter_text, chapter_num):
    """从正文自动提取 memory 更新"""
    
    # 1. 扫描实力变化（关键词按本书体系类设定的词汇调整）
    实力模式 = ["突破到", "晋升", "达到...", "进阶"]
    for 句子 in chapter_text.splitlines():
        if 匹配实力模式(句子):
            提取(角色, 新实力, 章号)
    
    # 2. 扫描物品流转
    物品模式 = ["得到", "交给", "遗失", "夺取"]
    
    # 3. 扫描地点变化
    地点模式 = ["来到", "抵达", "离开"]
    
    # 4. 扫描信息获得
    信息模式 = ["得知", "发现", "听说", "看到"]
    # → 更新 state.md 的"已知秘密"
    
    # 5. 扫描伏笔操作
    伏笔模式 = 从 threads.md 读取每条伏笔的"检索钩子"
    # → 检测本章是否推进了某条伏笔
    
    # 6. 生成摘要
    # 提取：主要事件、场景类型、地点、出场角色、关键信息、状态变化
    # 按 summaries 模板格式化（含 类型/场景 索引字段）
    
    return {
        "state_updates": [...],
        "thread_records": [...],
        "timeline_entry": ...,
        "summary": ...
    }
```

**实现方式**：
- 写完章节后，agent 先扫描正文，生成提取建议
- 展示给用户："我检测到以下变化，要同步到 memory 吗？"
- 用户确认后批量更新

### 4. Memory 版本化

`state.md` 改为追加式，而不是覆盖：

```markdown
# 当前状态

截至：第 123 章

## 时间与地点
...

---
## 历史快照

### 截至第 100 章
- 主角所在：不周山
- 主角境界：金仙初期

### 截至第 50 章
- 主角所在：紫霄宫
- 主角境界：天仙巅峰
```

好处：
- 可以回溯任意章节时的状态
- 写番外或支线时，可以切到特定时间点的状态
- 发现错误时，能追溯是哪一章改错了

### 5. 自动补同步检测

Agent 在开始写新章前，**自动检查未同步章节**：

```python
def check_sync_status(root):
    """检查是否有未同步的章节"""
    
    # 读 AGENTS.md"当前进度"→ 最新定稿章号
    last_synced = 从 AGENTS.md 提取最新章号
    
    # 扫描 chapters/ → 实际存在的最新章号
    actual_latest = chapter_files(root)[-1][0] if章节存在 else 0
    
    if actual_latest > last_synced:
        unsynced = list(range(last_synced + 1, actual_latest + 1))
        return {
            "has_unsynced": True,
            "chapters": unsynced,
            "message": f"检测到 {len(unsynced)} 章未同步：{unsynced}"
        }
    
    return {"has_unsynced": False}
```

**用户体验**：
```
用户：写第 5 章
Agent：检测到第 4 章尚未同步到 memory，我先补同步第 4 章。
      [自动读第 4 章、提取信息、更新 memory]
      第 4 章已同步 ✓
      现在开始第 5 章...
```

### 6. AGENTS.md 自动归档

当 AGENTS.md 超过 150 行时，agent 自动归档已完成卷的规则：

```python
def auto_archive_agents(root):
    agents_md = root / "AGENTS.md"
    text = agents_md.read_text()
    lines = text.splitlines()
    
    if len(lines) > 150:
        # 提取"硬规则"一节
        rules = 提取硬规则段落(text)
        
        # 区分"全书级规则"和"已完成卷的规则"
        current_vol = 从当前进度提取卷号(text)
        archived_rules = [r for r in rules if "第N卷" in r and N < current_vol]
        active_rules = [r for r in rules if r not in archived_rules]
        
        # 归档
        archive_path = root / "lore/archive" / f"vol{N}-rules.md"
        archive_path.parent.mkdir(exist_ok=True)
        archive_path.write_text("\n".join(archived_rules))
        
        # 重写 AGENTS.md，只保留活跃规则
        new_text = 重写AGENTS(text, active_rules, 添加归档链接)
        agents_md.write_text(new_text)
        
        return f"AGENTS.md 已归档 {len(archived_rules)} 条历史规则到 lore/archive/"
```

用户看到的是：
```
用户：写第 101 章（第三卷第一章）
Agent：AGENTS.md 已归档前两卷的 8 条规则，保持精简 ✓
      开始写第 101 章...
```

### 7. AI 味检测上下文敏感

`novel.py lint` 的 AI 味检测按文风预设调整权重：

```python
# 从 AGENTS.md 读取文风预设
style = 提取文风预设()

# 调整检测权重
if style == "古典仙侠":
    AI_PATTERNS["缓缓/微微"]["weight"] = 0.5  # 降低权重
    AI_PATTERNS["嘴角弧度"]["weight"] = 2.0   # 提高权重
elif style == "冷硬简笔":
    AI_PATTERNS["情绪套话"]["weight"] = 3.0   # 严格检查
    AI_PATTERNS["比喻连接词"]["weight"] = 0.3 # 放宽（本就很少）
```

在 lint 报告里体现：
```
[AI 味] 命中 8 处，3.2 处/千字
  ×3  缓缓/微微  L12 L45 L89（古典仙侠文风可接受，密度正常）
  ×2  嘴角弧度  L34 L78（！本文风应避免，建议改写）
```

### 8. Skill 间自动协作

#### novel-chapter 内置轻量 review

```python
def 写章后自检(章节路径):
    # 1. 跑 lint
    lint_result = subprocess.run([novel.py, "lint", 章节路径, ...])
    
    # 2. 轻量一致性检查（不展开全面审稿）
    快速检查 = {
        "字数达标": 是否在范围,
        "格式通过": lint 无错误,
        "上章衔接": 简单读上章末尾对比,
        "硬规则": 扫描 AGENTS.md 硬规则的关键词,
        "纲外新增": 正文冒出的新专名/新事件/新设定是否在已审核范围内
    }
    
    # 3. 发现硬错误：直接改
    if 有硬错误:
        自动修复()
        重新检查()
    
    # 4. 有警告或建议：报告给用户
    return 检查报告
```

用户体验：
```
Agent：[写完第 5 章 2487 字]
      自检：字数 ✓  格式 ✓  衔接 ✓  硬规则 ✓
      AI 味密度 2.1 处/千字（正常）
      
      第 5 章已完成，要定稿吗？
```

#### novel-init 调用 novel-lore

```python
# novel-init 第 2 轮（设定分类）：每个分类由 novel.py category 创建，
# 分类字段若用户有特别要求，接着编辑该目录的 _schema.md。

# 第 3 轮（核心要素，可选）：用户选择"现在填"时，
# 对具体实体（如主角）调用 lore 的详细流程
agent.call_skill("novel-lore", {
    "action": "create_entity",
    "category": 所属分类目录,
    "name": 实体名,
    "preset": 从用户选择提取的要点,
    "auto_mode": True  # 自动模式，跳过冗余提问；用户没答的决策点仍列出供审核
})
```

用户体验：
```
用户：[给出主角要点]
Agent：[自主生成的关键字段先列出来给你过目]
      好的，按审核通过的方案建文件...
      [内部调用 novel-lore，按 characters/_schema.md 建文件]
      主角「林川」已创建 ✓
      - 核心欲望：证明自己
      - 缺陷：过于自负
```

### 9. 批量操作自动化

#### 写多章

```
用户：写接下来 3 章
Agent：读卷纲 → 生成第 N、N+1、N+2 章的骨架 → 展示确认
      用户确认后：
      - 逐章写作（后章能读前章正文）
      - 每章写完自检
      - 全部完成后统一展示
      - 用户说"都定稿"→ 批量同步 memory
```

#### 整卷审稿

```
用户：审第一卷
Agent：扫描 chapters/vol01/ → 发现 30 章
      [后台批量 lint]
      [后台批量一致性检查]
      生成卷级报告：
      - 每章一行简评（通过/警告/错误）
      - 汇总统计（平均字数、AI 味密度趋势）
      - 卷级问题（伏笔遗忘、配角失踪、节奏平淡段）
```

### 10. Git 版本管理

环境有 git 就自动启用，没有就静默跳过（不提示安装、不打断流程）。核心规则：**暂存自动做，提交必须问**——`git add` 廉价可逆，commit 产生历史，要用户点头。

#### 建仓（任何建书流程收尾时：novel-init / novel-import）

```python
def auto_init_repo(root):
    if not shutil.which("git"):
        return                      # 没装 git，跳过
    if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                      cwd=root, capture_output=True).returncode == 0:
        return                      # 已在某个仓库内，不嵌套建仓
    subprocess.run(["git", "init"], cwd=root)
    # .gitignore 由 novel.py init 播种（排除 drafts/）
    subprocess.run(["git", "add", "-A"], cwd=root)
    if 问用户("Git 仓库已建好并暂存全部文件，要做初始提交吗？"):
        git commit -m "init: 建书骨架"      # 默认消息，用户可改
```

#### 定稿暂存（novel-chapter 定稿规程第 8 步）

memory 同步完成后：

```python
def auto_stage(root, 章号, 章名):
    if not 书根目录是 git 仓库:
        return
    subprocess.run(["git", "add", "-A"], cwd=root)   # 正文 + memory + outline + 新 lore 全暂存
    files = git diff --cached --name-only
    展示(f"已暂存 {len(files)} 个文件")
    if 问用户("要提交吗？"):
        git commit -m f"第{章号}章《{章名}》定稿"   # 用户可改消息
```

- **批量写多章**：逐章定稿照常暂存，全部写完后**只问一次**，一个提交覆盖这批章（消息如"第 N-M 章定稿"）。
- **改稿、番外**定稿走同一规则，消息对应改写（"改稿第 N 章""番外 0019c 定稿"）。
- 用户不提交就留在暂存区，下次暂存自然叠加；攒不攒着提交由用户决定，agent 不擅自 commit。

### 11. 规则文件自动编译

规则写成文件：本书 `rules/*.md`，全局 `~/.novel-skills/rules/*.md`（跨书共享）。文件的 `scope` frontmatter（可不写，默认 `always`）决定生效方式：`always` 编译进 AGENTS.md「规则」节随文件注入；`writing`/`review`/`lore` 只进该节末尾的场景表，做对应工作前按需读取。机制详见 novel-core SKILL.md「规则文件」节。

- 不需要手动同步：每次 `novel.py` 调用前自动比对源文件，变了就重编译；重编译会把新注入层打印到工具输出，当前会话立即生效，不等下次注入。
- agent 自己经手修改 `rules/*.md` 后：跑一次 `novel.py rules --sync`，确认生效并展示注入层。
- 同名文件本书覆盖全局；`priority`（默认 0，小的排前）控制编译顺序；「规则」节块内不要手改。
- 用户手动改源文件的场景由惰性检查兜底——没有"必须记得跑"的步骤，这正是它替代"会话开头跑脚本"方案的原因。

## 实现检查清单

Agent 每次操作时，内心检查：

**写章前**：
- ☑ 检查未同步章节 → 补同步
- ☑ 检查 AGENTS.md 长度 → 需要归档吗
- ☑ 「规则」节场景表有 writing 文件就先读
- ☑ 读必需上下文（不多不少）
- ☑ 章纲/方案里 agent 自主生成的部分已标「拟」并经用户审核

**写章中**：
- ☑ 应用文风预设
- ☑ 遵守硬规则
- ☑ 不违反伏笔约束

**写章后**：
- ☑ 后台跑 lint
- ☑ 轻量自检
- ☑ 硬错误自动修复

**定稿时**：
- ☑ 自查正文有无纲外新要素；有则列出请用户决定去留
- ☑ 扫描正文提取 memory 更新
- ☑ 展示提取结果让用户确认
- ☑ 批量更新 7 个地方
- ☑ 追加 state 历史快照
- ☑ git 暂存本次变更并询问是否提交（有仓库时）

**建设定时**：
- ☑ 检查重名、冲突
- ☑ 自动更新 glossary
- ☑ 双向更新关联实体
- ☑ 实体不归属任何分类时提示用户加分类（novel.py category add）

这些操作**全部在后台完成**，用户只看到结果摘要喵~
