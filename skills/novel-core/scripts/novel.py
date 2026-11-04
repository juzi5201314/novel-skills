#!/usr/bin/env python3
"""网文项目工具箱，只依赖 Python 标准库。在书根目录运行（或用 --root 指定）。

子命令：
  init      创建通用骨架与种子文件（不覆盖已有文件；不含设定分类，分类用 category add）
  next      给出下一章章号、建议路径和上一章位置
  stats     统计章节字数
  lint      检查单章格式与 AI 味高频表达
  find      在正文中检索实体/关键词（--entity 自动带上 lore 里的别名）
  similar   相似段落查重：字符三元组找措辞复用，防套路重复（措辞级，非语义）
  split     把整本 txt 按"第X章"切分成标准章节文件（番外/外篇/楔子识别为 NNNNx）
  insert    在第 N 章后空出一个主线章位（重编号并同步引用）；--extra 取该锚点的空闲番外位
  category  设定分类注册表：list / add / rename（注册表在 AGENTS.md"设定分类"一节）
  rules     规则文件（本书 rules/ + 全局 ~/.novel-skills/rules/）编译进 AGENTS.md「规则」节
  validate  检查项目完整性（必填字段、分类注册表、glossary、frontmatter、编号连续性）
  export    合并全书为单个 txt，可按卷或章号范围导出
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from pathlib import Path
from datetime import datetime

TEMPLATES = Path(__file__).resolve().parent.parent / "assets" / "templates"

# 规则文件：本书 rules/*.md + 全局 ~/.novel-skills/rules/*.md（后者可用 NOVEL_RULES_HOME 改位置）。
# scope: always 编译进 AGENTS.md「规则」节随文件注入；writing/review/lore 只进该节的场景表按需读。
GLOBAL_RULES_DIR = Path(os.environ.get("NOVEL_RULES_HOME", Path.home() / ".novel-skills" / "rules"))
RULES_BEGIN = "<!-- novel:rules -->"
RULES_END = "<!-- /novel:rules -->"
RULE_SCOPES = ("always", "writing", "review", "lore")
_RULES_PAT = re.compile(re.escape(RULES_BEGIN) + ".*?" + re.escape(RULES_END), re.S)

# 只建与作品内容无关的通用骨架；设定分类由用户决定后用 category add 添加
DIRS = (
    "chapters/vol01",
    "outline/volumes",
    "outline/chapters",
    "lore",
    "lore/images",
    "memory/summaries",
    "drafts",
    "rules",
)
# 目标路径 -> 模板文件名
SEEDS = {
    ".gitignore": "gitignore",
    "AGENTS.md": "AGENTS.md",
    "outline/synopsis.md": "synopsis.md",
    "outline/volumes/vol01.md": "volume.md",
    "lore/glossary.md": "glossary.md",
    "memory/state.md": "state.md",
    "memory/threads.md": "threads.md",
    "memory/timeline.md": "timeline.md",
    "memory/summaries/vol01.md": "summaries.md",
}

CN_NUM = "0-9零〇一二三四五六七八九十百千万两"
CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
HEADER_RE = re.compile(rf"^第[{CN_NUM}]+章[ \u3000]+\S")
EXTRA_HEADER_RE = re.compile(r"^(?:番外|外篇|楔子|序章|序曲|尾声)")
SPLIT_CHAPTER_RE = re.compile(rf"^\s*第[{CN_NUM}]+[章回][ \u3000:：、.]*(.*)$")
SPLIT_EXTRA_RE = re.compile(
    rf"^\s*(番外篇?|外篇|楔子|序章|序曲|尾声)[{CN_NUM}]*[ \u3000:：、·\-—]*(.*\S)?\s*$")
SPLIT_VOLUME_RE = re.compile(rf"^\s*第[{CN_NUM}]+卷")
# NNNNx-章名.txt：x 为空是主线章，a-z 是锚在 NNNN 章后的第 1-26 个番外（0000x 用于正文前的楔子/序章）
CHAPTER_FILE_RE = re.compile(r"^(\d{4,})([a-z]?)-(.+)\.txt$")
CJK_RE = re.compile(f"[{CJK}]")
WS_RE = re.compile(r"\s")

MD_RE = re.compile(r"^(?:#{1,6}\s|[-*+]\s|>|\d+\.\s|(?:-{3,}|\*{3,}|_{3,})$)|\*\*|`")
HALF_PUNCT_RE = re.compile(rf"(?<=[{CJK}])[,.?!:;()]|[,.?!:;()](?=[{CJK}])")
ELLIPSIS_RE = re.compile(r"\.{2,}|。{2,}|(?<!…)…(?!…)|…{3,}")
DASH_RE = re.compile(rf"(?<!—)—(?!—)|—{{3,}}|-{{2,}}|(?<=[{CJK}])-(?=[{CJK}])")

# AI 味高频表达：命中不等于错误，密度才是问题。说明见 novel-craft/references/anti-ai.md
AI_PATTERNS = [
    (r"仿佛|宛如|犹如|恍若|恍如", "比喻连接词"),
    (r"像(?:是)?一[盏个只道团片堵面把柄座]|像被[^，。！？]{0,8}无形|像是[^，。！？]{1,8}也在", "换壳比喻(像一…/像被无形…)"),
    (r"将熄的灯|破风箱|无形的大?手|潮水般|瘫坐如泥|如死狗|烂泥般", "陈腐死比喻"),
    (r"不禁|不由得|不由自主", "不禁/不由得"),
    (r"缓缓|微微", "缓缓/微微"),
    (r"淡淡", "淡淡"),
    (r"一[丝抹缕]", "一丝/一抹/一缕"),
    (r"嘴角[^，。！？]{0,6}(?:勾起|扬起|上扬|弧度)", "嘴角弧度"),
    (r"[眼眸目瞳][中里底光内][^，。！？]{0,4}闪过", "眼中闪过"),
    (r"没有温度|不带(?:一丝|半点|任何)?(?:感情|温度|情绪)", "没有温度/不带感情"),
    (r"深吸(?:了)?一口气", "深吸一口气"),
    (r"心(?:中|头|里|下)一(?:凛|紧|动|震|沉|颤)", "心中一凛"),
    (r"(?:冷冷|淡淡|缓缓|轻轻|沉声|低声|柔声)(?:地)?(?:说道|道)", "副词+说道"),
    (r"说道", "说道"),
    (r"空气(?:仿佛|似乎|都|中)?(?:凝固|凝滞|安静)", "空气凝固"),
    (r"落针可闻|鸦雀无声|倒吸一口凉气", "围观套话"),
    (r"这一刻", "这一刻"),
    (r"[他她]知道[，,]", "他知道，"),
    (r"不知何时", "不知何时(伪细节)"),
    (r"终究(?:还是|只是|只能)|自始至终", "终究只能/自始至终(旁白腔)"),
    (r"不是[^。！？\n]{1,25}[，,]而是", "不是……而是"),
    (r"不仅仅?是[^。！？\n]{1,25}[，,](?:更|还|也)是", "不仅是……更是"),
    (r"没有[^，。！？\n]{1,12}[，,]也没有", "没有A，也没有B(端腔句式)"),
    (r"没等来[^，。！？\n]{0,10}[，,]等来了|来了又去[、，]去了又来", "顶真回环金句腔"),
    (r"命运的齿轮|才刚刚开始|仅仅只是开始|一切才刚刚", "宿命式收尾"),
    (r"难以言喻|无法形容|说不清道不明|前所未有", "无法形容"),
    (r"指节(?:泛白|发白)|喉结(?:上下)?滚动|瞳孔(?:骤然|猛地|微微)?(?:一)?缩", "身体反应套话"),
    (r"青筋(?:暴起|凸起)|眼眶(?:微微|有些)?泛红|红着眼|[横握]剑冷笑|冷笑一声|擦了又渗", "战损/神态套话"),
    (r"眸(?:子|光|中|底)", "眸子"),
    (r"带着(?:几分|一丝|一抹|些许)", "带着几分"),
    (r"显得(?:格外|十分|异常|有些|尤为)", "显得格外"),
    (r"某种", "某种"),
    (r"与此同时", "与此同时"),
    (r"涌上心头|心头一暖|五味杂陈|百感交集", "情绪套话"),
    (r"弥漫着|交织|涟漪|璀璨|深邃|低语|呜咽|苟延|轰然", "AI 偏爱词"),
]
AI_RES = [(re.compile(p), label) for p, label in AI_PATTERNS]

# 相似度检测（similar）：去标点空白后取字符三元组做指纹，查措辞级复用
SIM_PUNCT_RE = re.compile(r"[\s　，。！？；：、“”‘’（）《》【】「」…—·,.?!;:'\"()\[\]<>_-]+")
SIM_NGRAM = 3
SIM_MIN_LEN = 15  # 归一化后短于该长度的段落不生成指纹（太短没有可比性）


def word_count(text: str) -> tuple[int, int]:
    """返回（去空白字符数, 汉字数）。前者接近网文平台的字数口径。"""
    return len(WS_RE.sub("", text)), len(CJK_RE.findall(text))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sys.exit(f"{path}: 不是 UTF-8 编码（正文与设定要求 UTF-8；GBK 旧稿请用 split 导入）")


# lore 下不算实体分类的目录：images 存图，archive 存归档规则
LORE_SKIP_DIRS = {"images", "archive"}


def load_categories(root: Path) -> list[dict]:
    """读 AGENTS.md"## 设定分类"表，返回 [{"name", "dir"}]，dir 为 lore/ 下的相对路径。
    没有该节或解析失败时返回 []，调用方应退化为扫描 lore/ 实际目录。"""
    agents = root / "AGENTS.md"
    if not agents.exists():
        return []
    m = re.search(r"^##\s*设定分类[^\n]*\n(.*?)(?=^##\s|\Z)", read_text(agents), re.M | re.S)
    if not m:
        return []
    cats = []
    for line in m.group(1).splitlines():
        row = re.match(r"^\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|?\s*$", line)
        if not row:
            continue
        name, dircol = row.group(1).strip(" `　"), row.group(2).strip(" `　")
        if not name or name == "分类" or set(name + dircol) <= set("-: "):
            continue
        d = dircol.strip("/")
        if d.startswith("lore/"):
            d = d[5:]
        if d:
            cats.append({"name": name, "dir": d})
    return cats


def _lore_dirs_with_md(root: Path) -> set[str]:
    """lore 下实际含有 .md 文件的目录（相对 lore/ 的路径，可嵌套）。"""
    lore = root / "lore"
    found = set()
    if lore.is_dir():
        for p in lore.rglob("*.md"):
            rel = p.relative_to(lore)
            if len(rel.parts) >= 2 and rel.parts[0] not in LORE_SKIP_DIRS:
                found.add(rel.parent.as_posix())
    return found


def entity_files(root: Path) -> list[Path]:
    """lore 下的实体文件：排除 glossary、_ 开头的元文件（如 _schema.md）、
    images/ archive/ 等非实体目录、以及 lore 根目录下的散文件。"""
    lore = root / "lore"
    if not lore.is_dir():
        return []
    return sorted(
        p for p in lore.rglob("*.md")
        if len(p.relative_to(lore).parts) >= 2
        and p.relative_to(lore).parts[0] not in LORE_SKIP_DIRS
        and not p.name.startswith("_")
    )


def _glossary_rows(text: str) -> list[list[str]]:
    """glossary.md 的全部表格行（含表头/分隔行），每行为 cell 列表。"""
    return [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.lstrip().startswith("|")]


def _glossary_data_rows(rows: list[list[str]]) -> list[list[str]]:
    """去掉表头和分隔行后的条目行。"""
    return [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c or "-") for c in r)]


def _upsert_registry(text: str, name: str, dircol: str) -> str:
    """在 AGENTS.md 文本的"## 设定分类"表追加一行；没有该节则在文末补节。"""
    row = f"| {name} | lore/{dircol}/ |"
    m = re.search(r"^##\s*设定分类[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return text.rstrip() + f"\n\n## 设定分类\n\n| 分类 | 目录 |\n|---|---|\n{row}\n"
    body, lines = m.group(1), m.group(1).splitlines()
    tail_nl = "\n" if body.endswith("\n") else ""
    last_tbl = -1
    for i, l in enumerate(lines):
        if l.lstrip().startswith("|"):
            last_tbl = i
    if last_tbl >= 0:
        lines.insert(last_tbl + 1, row)
    else:
        lines += ["", "| 分类 | 目录 |", "|---|---|", row]
    return text[: m.start(1)] + "\n".join(lines) + tail_nl + text[m.end(1):]


def _rename_registry_row(text: str, dircol: str, new_name: str) -> str:
    """把注册表中目录列为 lore/{dircol}/ 的行的分类名改为 new_name。"""
    out, changed = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = line.split("|")
            if any(c.strip() == f"lore/{dircol}/" for c in cells):
                cells[1] = f" {new_name} "
                line, changed = "|".join(cells), True
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "") if changed else text


def split_header(lines: list[str]) -> tuple[str, int]:
    """返回（首个非空行, 其 1 起始行号）。"""
    for i, line in enumerate(lines, 1):
        if line.strip():
            return line.strip(), i
    return "", 0


def chapter_files(root: Path) -> list[tuple[int, str, Path]]:
    """返回 (章号, 番外后缀, 路径)，按 (章号, 后缀) 排序：0019 < 0019a < 0019b < 0020。
    后缀 "" 是主线章，"a"-"z" 是番外。"""
    found = []
    for p in (root / "chapters").rglob("*.txt"):
        m = CHAPTER_FILE_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), m.group(2), p))
    return sorted(found)


def parse_range(spec: str | None) -> tuple[int, int]:
    if not spec:
        return 0, sys.maxsize
    lo, _, hi = spec.partition("-")
    return int(lo), int(hi or lo)


def fmt_lines(nums: list[int], limit: int = 8) -> str:
    shown = " ".join(f"L{n}" for n in nums[:limit])
    return shown + (f" …(+{len(nums) - limit})" if len(nums) > limit else "")


_CN_DIGITS = {c: i for i, c in enumerate("零一二三四五六七八九")}
_CN_DIGITS["〇"] = 0
_CN_DIGITS["两"] = 2
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn2int(s: str) -> int | None:
    """章号写法 → int。阿拉伯数字直接转，中文数字支持到万位；解析不了返回 None。"""
    if s.isdigit():
        return int(s)
    total, sec, num = 0, 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            sec += (num or 1) * _CN_UNITS[ch]
            num = 0
        elif ch == "万":
            sec = (sec + num) * 10000
            total += sec
            sec = num = 0
        else:
            return None
    return total + sec + num


def int2cn(n: int) -> str:
    """1-99999 → 中文章号写法（章头风格：15→十五、101→一百零一、10020→一万零二十）。"""
    d = "零一二三四五六七八九"

    def four(v: int, leading: bool) -> str:
        s, zero = "", False
        for u, name in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
            q, v = divmod(v, u)
            if q == 0:
                if s:
                    zero = True
                continue
            if zero:
                s += "零"
                zero = False
            s += name if u == 10 and q == 1 and leading and not s else d[q] + name
        return s

    hi, lo = divmod(n, 10000)
    if hi:
        low = ("零" if 0 < lo < 1000 else "") + (four(lo, True) if lo else "")
        return four(hi, False) + "万" + low
    return four(lo, True)


def frontmatter(path: Path) -> dict[str, str | list[str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    data: dict[str, str | list[str]] = {}
    for line in text[3:end].splitlines():
        key, sep, val = line.partition(":")
        if not sep:
            continue
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            data[key.strip()] = [v.strip().strip("'\"") for v in re.split(r"[,，]", val[1:-1]) if v.strip()]
        else:
            data[key.strip()] = val.strip("'\"")
    return data


def _collect_rules(root: Path) -> tuple[list[dict], list[str]]:
    """收集全局（~/.novel-skills/rules/）与本书（rules/）的规则文件；本书同名文件覆盖全局，
    "_" 开头的不参与。frontmatter 可不写：缺省 scope=always、priority=0。
    返回（按 priority、文件名排序的规则列表, 警告列表）。"""
    found: dict[str, tuple[str, Path]] = {}
    for d, rel in ((GLOBAL_RULES_DIR, "~/.novel-skills/rules"), (root / "rules", "rules")):
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                if not p.name.startswith("_"):
                    found[p.stem] = (f"{rel}/{p.name}", p)
    rules, warns = [], []
    for stem, (rel, p) in found.items():
        try:
            fm, text = frontmatter(p), read_text(p)
        except UnicodeDecodeError:
            warns.append(f"{rel}: 不是 UTF-8 编码，已跳过")
            continue
        raw = fm.get("scope", "always")
        items = raw if isinstance(raw, list) else [raw]
        scopes = {str(s).strip().lower() for s in items}
        if bad := scopes - set(RULE_SCOPES):
            warns.append(f"{rel}: 未知 scope {sorted(bad)}，可选 {'/'.join(RULE_SCOPES)}")
            scopes -= bad
        if not scopes:
            scopes = {"always"}
        try:
            pri = int(str(fm.get("priority", 0)))
        except ValueError:
            warns.append(f"{rel}: priority 不是整数，按 0 处理")
            pri = 0
        body = re.sub(r"\A---\n.*?\n---\n?", "", text, count=1, flags=re.S).strip()
        rules.append({"rel": rel, "stem": stem, "scopes": scopes, "priority": pri,
                      "body": body, "desc": str(fm.get("desc") or fm.get("name") or "")})
    rules.sort(key=lambda r: (r["priority"], r["stem"]))
    return rules, warns


def _rules_block(root: Path) -> str:
    """AGENTS.md「规则」节的受管块（含 ## 标题与标记，整段由本函数生成）。"""
    rules, _ = _collect_rules(root)
    lines = [RULES_BEGIN, "## 规则", ""]
    if not rules:
        lines.append("（暂无规则文件。在本书 rules/ 或全局 ~/.novel-skills/rules/ 放 .md，"
                     "可选 frontmatter：scope 默认 always，可选 writing/review/lore；priority 默认 0。"
                     "由 novel.py 编译到这里。）")
    else:
        lines += ["由 `novel.py rules` 从本书 rules/ 与全局 ~/.novel-skills/rules/ 编译；"
                  "改规则请改源文件，块内手改会被覆盖。", ""]
        for r in rules:
            if "always" in r["scopes"] and r["body"]:
                lines += [f"<!-- {r['rel']} -->", r["body"], ""]
        scoped = [r for r in rules if "always" not in r["scopes"]]
        if scoped:
            lines += ["### 场景规则（做对应工作前读取）", "", "| 场景 | 文件 | 说明 |", "|---|---|---|"]
            for r in scoped:
                sc = "、".join(s for s in RULE_SCOPES[1:] if s in r["scopes"])
                lines.append(f"| {sc} | `{r['rel']}` | {r['desc']} |")
    lines.append(RULES_END)
    return "\n".join(lines)


def _announce_rules(root: Path, changed: bool) -> None:
    """把当前注入层打到输出：本会话内 AGENTS.md 注入的还是旧内容，新规则经工具输出立即进上下文。"""
    rules, warns = _collect_rules(root)
    agents = root / "AGENTS.md"
    if agents.exists() and re.search(r"(?m)^##\s*规则", _RULES_PAT.sub("", read_text(agents))):
        print("[规则] 注意：标记块外还存在手写「规则」节，会与编译块并存；建议并入 rules/ 源文件后删除")
    always = [r for r in rules if "always" in r["scopes"] and r["body"]]
    print(f"[规则] AGENTS.md「规则」节{'已重编译' if changed else '已是最新'}。当前注入层：")
    if always:
        for r in always:
            print(f"<!-- {r['rel']} -->")
            print(r["body"])
    else:
        print("（空）")
    scoped = [r["rel"] for r in rules if "always" not in r["scopes"]]
    if scoped:
        print("[规则] 场景规则（按需读取）：" + "、".join(scoped))
    n = sum(r["body"].count("\n") + 1 for r in always)
    if n > 60:
        print(f"[规则] 注入层 {n} 行偏多：AGENTS.md 建议控制在 150 行，细则可改 scope 按需文件")
    for w in warns:
        print(f"[规则] {w}")


def _sync_rules(root: Path, announce: bool = False) -> bool:
    """rules/ 源文件与 AGENTS.md「规则」块不一致时重编译，返回是否有写入。"""
    agents = root / "AGENTS.md"
    if not agents.exists():
        return False
    text = read_text(agents)
    rules, _ = _collect_rules(root)
    matches = list(_RULES_PAT.finditer(text))
    if not rules and not matches:
        return False
    block = _rules_block(root)
    if matches:
        parts, last = [], 0
        for i, m in enumerate(matches):  # 只保留第一个块，多余的（手贴出来的）清掉
            parts += [text[last:m.start()], block if i == 0 else ""]
            last = m.end()
        parts.append(text[last:])
        new = "".join(parts)
    else:
        anchor = re.search(r"(?m)^##\s*(?:设定分类|目录索引|工作流|当前进度)", text)
        new = (text[:anchor.start()].rstrip() + "\n\n" + block + "\n\n" + text[anchor.start():]
               if anchor else text.rstrip() + "\n\n" + block + "\n")
    if new == text:
        return False
    agents.write_text(new, encoding="utf-8")
    if announce:
        _announce_rules(root, changed=True)
    return True


def cmd_init(a: argparse.Namespace) -> None:
    root = Path(a.root)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for dst, tpl in SEEDS.items():
        target = root / dst
        if target.exists():
            print(f"跳过（已存在）：{dst}")
            continue
        target.write_text((TEMPLATES / tpl).read_text(encoding="utf-8"), encoding="utf-8")
        print(f"创建：{dst}")
    link = root / "CLAUDE.md"
    if link.exists() or link.is_symlink():
        print("跳过（已存在）：CLAUDE.md")
    else:
        link.symlink_to("AGENTS.md")
        print("创建：CLAUDE.md -> AGENTS.md")
    if not GLOBAL_RULES_DIR.is_dir():
        GLOBAL_RULES_DIR.mkdir(parents=True)
        print(f"创建：{GLOBAL_RULES_DIR}（全局规则目录，对所有的书生效，可选）")
    if _sync_rules(root):
        print("更新：AGENTS.md「规则」节按 rules/ 与全局规则编译")
    print("提示：骨架不含设定分类。问清用户后用 'category add 中文名 目录名 [--from 模板]' 按需添加。")


def cmd_next(a: argparse.Namespace) -> None:
    root = Path(a.root)
    mains = [(n, p) for n, s, p in chapter_files(root) if not s]
    if mains:
        n, last = mains[-1]
        vol_dir = last.parent
        missing = sorted(set(range(1, n + 1)) - {num for num, _ in mains})
        if missing:
            print(f"注意：缺少章号 {', '.join(f'{m:04d}' for m in missing[:20])}")
    else:
        n, last, vol_dir = 0, None, root / "chapters" / "vol01"
    nxt = n + 1
    outline = root / "outline" / "chapters" / f"{nxt:04d}.md"
    print(f"下一章：{nxt:04d}（标题行写作“第{nxt}章 章名”）")
    print(f"正文路径：{(vol_dir / f'{nxt:04d}-章名.txt').relative_to(root)}（换卷时改到新的 volNN）")
    print(f"章纲路径：{outline.relative_to(root)}{'（已存在）' if outline.exists() else '（不存在）'}")
    print(f"上一章：{last.relative_to(root) if last else '无'}")


def cmd_stats(a: argparse.Namespace) -> None:
    root = Path(a.root)
    lo, hi = parse_range(a.range)
    rows = [(n, s, p) for n, s, p in chapter_files(root) if lo <= n <= hi]
    if not rows:
        sys.exit("没有找到章节文件（chapters/**/NNNN[x]-章名.txt）")
    total = 0
    print("章号     字数    汉字  文件")
    for n, s, p in rows:
        lines = read_text(p).splitlines()
        _, hline = split_header(lines)
        words, han = word_count("\n".join(lines[hline:]))
        total += words
        flag = ""
        if a.min and words < a.min:
            flag = f"  偏少（<{a.min}）"
        elif a.max and words > a.max:
            flag = f"  偏多（>{a.max}）"
        print(f"{f'{n:04d}{s}':<6} {words:>6}  {han:>6}  {p.relative_to(root)}{flag}")
    print(f"合计 {len(rows)} 章，{total} 字，平均 {total // len(rows)} 字/章")


def cmd_lint(a: argparse.Namespace) -> None:
    path = Path(a.file)
    lines = read_text(path).splitlines()
    errors: list[str] = []
    warns: list[str] = []

    header, hline = split_header(lines)
    fm = CHAPTER_FILE_RE.match(path.name)
    if fm and fm.group(2):
        if not EXTRA_HEADER_RE.match(header):
            errors.append(f"L{hline}: 番外首行应为“番外/外篇/楔子/序章 章名”，实际是“{header[:30]}”")
    elif not HEADER_RE.match(header):
        errors.append(f"L{hline}: 首行应为“第N章 章名”，实际是“{header[:30]}”")
    paras = [(i, line) for i, line in enumerate(lines, 1) if i > hline and line.strip()]
    if not paras:
        sys.exit(f"{path}: 正文为空")
    body = "\n".join(line for _, line in paras)
    words, han = word_count(body)

    # 段落格式
    fw = [n for n, l in paras if l.startswith("\u3000\u3000")]
    none = [n for n, l in paras if not l[0].isspace()]
    bad = [n for n, l in paras if l[0].isspace() and not l.startswith("\u3000\u3000")]
    if bad:
        errors.append(f"段首缩进只能是两个全角空格或不缩进：{fmt_lines(bad)}")
    if fw and none:
        minority = fw if len(fw) < len(none) else none
        warns.append(f"段首缩进不统一（全角缩进 {len(fw)} 段 / 无缩进 {len(none)} 段），少数派：{fmt_lines(minority)}")
    gaps = [b - x for (x, _), (b, _) in zip(paras, paras[1:])]
    tight, spaced = gaps.count(1), gaps.count(2)
    wide = [paras[i + 1][0] for i, g in enumerate(gaps) if g > 2]
    if tight and spaced:
        warns.append(f"段间空行不统一：{tight} 处紧挨、{spaced} 处空一行")
    if wide:
        warns.append(f"连续多个空行：{fmt_lines(wide)}")
    if len(paras) > 1 and not fw and not spaced:
        errors.append("缺少段落排版：全文既无段首两个全角空格缩进（　　），也无段间空行，呈密排文字墙")

    # “一句一行”碎段检测（剔除含对白的段落，统计纯叙述段里的句末标点数量）
    pure_narr = [(n, l.strip()) for n, l in paras if "“" not in l and "「" not in l]
    if len(pure_narr) >= 5:
        one_sent = [n for n, s in pure_narr if len(re.findall(r"[。！？!?]+|……", s)) <= 1]
        if len(one_sent) / len(pure_narr) >= 0.60:
            warns.append(
                f"“一句一行”碎段倾向：{len(one_sent)}/{len(pure_narr)} 个纯叙述段只有一句话（平均 {words // len(paras)} 字/段），"
                f"请将同焦点的连续动作与观察合并为 2–5 句的自然段：{fmt_lines(one_sent)}"
            )
        else:
            # 检测局部连续 4 段以上单句叙述段
            s_run: list[int] = []
            one_set = set(one_sent)
            for n, _ in paras:
                if n in one_set:
                    s_run.append(n)
                else:
                    if len(s_run) >= 4:
                        warns.append(f"连续 {len(s_run)} 段为单句叙述（“一句一行”电报体）：{fmt_lines(s_run)}")
                    s_run = []
            if len(s_run) >= 4:
                warns.append(f"连续 {len(s_run)} 段为单句叙述（“一句一行”电报体）：{fmt_lines(s_run)}")

    # 逐段检查
    checks = {
        "Markdown 残留": [], "半角标点": [], "英文双引号": [], "省略号应为“……”": [],
        "破折号应为“——”": [], "引号不配对": [],
    }
    long_paras: list[int] = []
    for n, line in paras:
        s = line.strip()
        if MD_RE.search(s):
            checks["Markdown 残留"].append(n)
        if HALF_PUNCT_RE.search(s):
            checks["半角标点"].append(n)
        if '"' in s:
            checks["英文双引号"].append(n)
        if ELLIPSIS_RE.search(s):
            checks["省略号应为“……”"].append(n)
        if DASH_RE.search(s):
            checks["破折号应为“——”"].append(n)
        if s.count("“") != s.count("”"):
            checks["引号不配对"].append(n)
        if len(s) > a.long_para:
            long_paras.append(n)
    for label, nums in checks.items():
        if nums:
            errors.append(f"{label}：{fmt_lines(nums)}")
    if "「" in body and "“" in body:
        warns.append("同时使用了“”和「」两种引号")
    if long_paras:
        warns.append(f"段落超过 {a.long_para} 字（手机阅读吃力）：{fmt_lines(long_paras)}")

    # 连续 3 段以上同字开头（对白段除外）
    run: list[int] = []
    prev = ""
    for n, line in paras + [(0, "“")]:
        first = line.strip()[:1]
        if first == prev and first != "“":
            run.append(n)
        else:
            if len(run) >= 3:
                warns.append(f"连续 {len(run)} 段以“{prev}”开头：{fmt_lines(run)}")
            run = [n]
        prev = first

    if a.min and words < a.min:
        warns.append(f"字数 {words} 低于下限 {a.min}")
    if a.max and words > a.max:
        warns.append(f"字数 {words} 高于上限 {a.max}")

    # 参考指标
    narr = [len(l.strip()) for _, l in paras if not l.strip().startswith("“")]
    cv = statistics.pstdev(narr) / statistics.mean(narr) if len(narr) > 1 else 0.0
    quoted = sum(len(m) for m in re.findall(r"“[^”]*”", body))
    per_k = 1000 / max(words, 1)
    dash_lines = [n for n, l in paras if "——" in l]
    if len(dash_lines) >= 3 and body.count("——") * per_k > 2.5:
        warns.append(
            f"破折号“——”过多（共 {body.count('——')} 处，{body.count('——') * per_k:.1f} 处/千字，"
            f"警惕句尾旁白补刀腔）：{fmt_lines(dash_lines)}"
        )

    # AI 味
    ai_hits: list[tuple[str, list[int]]] = []
    for rx, label in AI_RES:
        nums = [n for n, l in paras for _ in rx.finditer(l)]
        if nums:
            ai_hits.append((f"{label}（{rx.pattern}）", nums))
    ai_total = sum(len(nums) for _, nums in ai_hits)

    print(f"== {path} ==")
    print(f"字数 {words}（汉字 {han}），段落 {len(paras)}，平均 {words // len(paras)} 字/段")
    print(
        f"参考：叙述段长度变异系数 {cv:.2f}（<0.4 往往节奏呆板）｜对白占比 {quoted / max(words, 1):.0%}"
        f"｜每千字 ！{body.count('！') * per_k:.1f} ——{body.count('——') * per_k:.1f} ……{body.count('……') * per_k:.1f}"
    )
    for e in errors:
        print(f"[错误] {e}")
    for w in warns:
        print(f"[警告] {w}")
    print(f"[AI 味] 命中 {ai_total} 处，{ai_total * per_k:.1f} 处/千字（命中不等于错误，看密度和语境）")
    for label, nums in sorted(ai_hits, key=lambda x: -len(x[1])):
        print(f"  ×{len(nums):<3} {label}  {fmt_lines(nums, 6)}")
    sys.exit(1 if errors else 0)


def cmd_find(a: argparse.Namespace) -> None:
    root = Path(a.root)
    terms = set(a.terms)
    for name in a.entity:
        terms.add(name)
        for p in (root / "lore").rglob("*.md"):
            if p.name.startswith("_"):
                continue
            fm = frontmatter(p)
            if fm.get("name") == name or p.stem == name:
                aliases = fm.get("aliases", [])
                terms.update(aliases if isinstance(aliases, list) else [aliases])
    terms.discard("")
    if not terms:
        sys.exit("需要关键词或 --entity")
    ordered = sorted(terms, key=len, reverse=True)
    pattern = re.compile("|".join(ordered if a.regex else map(re.escape, ordered)))

    lo, hi = parse_range(a.range)
    files = [(f"{n:04d}{s}", p) for n, s, p in chapter_files(root) if lo <= n <= hi]
    if a.all:
        files += [(p.relative_to(root).as_posix(), p) for d in ("outline", "lore", "memory")
                  for p in sorted((root / d).rglob("*.md"))]

    total = 0
    for label, p in files:
        rows = []
        for i, line in enumerate(read_text(p).splitlines(), 1):
            ms = list(pattern.finditer(line))
            if not ms:
                continue
            total += len(ms)
            s, e = max(0, ms[0].start() - a.context), min(len(line), ms[-1].end() + a.context)
            rows.append(f"  L{i}: {pattern.sub(lambda m: f'【{m.group()}】', line[s:e].strip())}")
        if not rows:
            continue
        if a.count:
            print(f"{label}  {len(rows)} 行  {p.relative_to(root)}")
        else:
            print(f"## {label}  {p.relative_to(root)}")
            print("\n".join(rows[: a.limit]))
            if len(rows) > a.limit:
                print(f"  …其余 {len(rows) - a.limit} 行省略（--limit 调整）")
        if a.first:
            break
    print(f"共 {total} 处；检索词：{'、'.join(ordered)}")


def _sim_paras(path: Path) -> list[dict]:
    """把章节切成可比较段落，返回 [{line, text, grams}]；标题行与过短段跳过。"""
    lines = read_text(path).splitlines()
    _, hline = split_header(lines)
    out = []
    for i, line in enumerate(lines, 1):
        if i <= hline or not line.strip():
            continue
        norm = SIM_PUNCT_RE.sub("", line)
        if len(norm) < SIM_MIN_LEN:
            continue
        grams = {norm[j:j + SIM_NGRAM] for j in range(len(norm) - SIM_NGRAM + 1)}
        if grams:
            out.append({"line": i, "text": line.strip(), "grams": grams})
    return out


def cmd_similar(a: argparse.Namespace) -> None:
    root = Path(a.root)
    lo, hi = parse_range(a.range)
    corpus: list[dict] = []
    for n, s, p in chapter_files(root):
        if lo <= n <= hi:
            for para in _sim_paras(p):
                para["ref"] = f"{n:04d}{s}:L{para['line']}"
                para["src"] = p.resolve()
                corpus.append(para)
    if len(corpus) < 2:
        sys.exit("可比较的段落不足（chapters/ 为空或段落都太短）")

    # 过滤通用腔：出现在 >15% 段落里的三元组没有区分度（"的时候"级）
    df: dict[str, int] = {}
    for para in corpus:
        for g in para["grams"]:
            df[g] = df.get(g, 0) + 1
    common = {g for g, c in df.items() if c > max(30, int(0.15 * len(corpus)))}
    for para in corpus:
        para["grams"] -= common
    corpus = [para for para in corpus if para["grams"]]

    index: dict[str, list[int]] = {}
    for pid, para in enumerate(corpus):
        for g in para["grams"]:
            index.setdefault(g, []).append(pid)

    def similar(grams: set, skip: set) -> list[tuple[float, int]]:
        """倒排索引收候选，对候选算 Jaccard；返回 (score, pid) 降序。"""
        hits: dict[int, int] = {}
        for g in grams:
            for pid in index.get(g, ()):
                if pid not in skip:
                    hits[pid] = hits.get(pid, 0) + 1
        out = []
        for pid, shared in hits.items():
            union = len(grams) + len(corpus[pid]["grams"]) - shared
            if shared / union >= a.min_score:
                out.append((shared / union, pid))
        return sorted(out, reverse=True)

    def snip(text: str) -> str:
        return text[:38] + "…" if len(text) > 38 else text

    if a.all:
        pairs = []
        for i, para in enumerate(corpus):
            pairs += [(score, i, pid) for score, pid in similar(para["grams"], {i}) if pid > i]
        pairs.sort(reverse=True)
        print(f"== 全书查重：{len(corpus)} 段中 {len(pairs)} 对相似（≥{a.min_score}），Top {a.top} ==")
        for score, i, pid in pairs[: a.top]:
            pa, pb = corpus[i], corpus[pid]
            print(f"{score:.2f}  {pa['ref']} ↔ {pb['ref']}")
            print(f"    {snip(pa['text'])}")
            print(f"    {snip(pb['text'])}")
        return

    if not a.file:
        sys.exit("给文件路径查单章/草稿，或用 --all 全书两两查重")
    qpath = Path(a.file)
    if not qpath.exists():
        sys.exit(f"文件不存在：{qpath}")
    own = {i for i, c in enumerate(corpus) if c["src"] == qpath.resolve()}
    pairs = []
    for para in _sim_paras(qpath):
        pairs += [(score, para, corpus[pid]) for score, pid in similar(para["grams"] - common, own)]
    pairs.sort(key=lambda t: -t[0])
    try:
        qlabel = qpath.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        qlabel = str(qpath)
    print(f"== {qlabel}：与全书相似段落（≥{a.min_score}）==")
    for score, qa, pb in pairs[: a.top]:
        print(f"{score:.2f}  L{qa['line']} ↔ {pb['ref']}")
        print(f"    {snip(qa['text'])}")
        print(f"    {snip(pb['text'])}")
    print(f"共 {len(pairs)} 处（--min-score/--top 调整）")


def cmd_split(a: argparse.Namespace) -> None:
    raw = Path(a.file).read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit("无法识别编码（已尝试 UTF-8 / GB18030）")

    vol = 1
    chapters: list[dict] = []
    extras: list[str] = []  # 卷首语、作品相关等不属于任何章的文字
    cur: dict | None = None
    for line in text.splitlines():
        s = line.strip()
        short = len(s) <= 50 and "。" not in s
        m = SPLIT_CHAPTER_RE.match(line) if short else None
        xm = SPLIT_EXTRA_RE.match(line) if short and m is None else None
        if m:
            cur = {"vol": vol, "title": m.group(1).strip() or "无题", "body": []}
            chapters.append(cur)
        elif xm:
            # 番外/楔子等：锚在前一个主线章之后，正文前的锚记 0000
            cur = {"vol": vol, "title": (xm.group(2) or "").strip() or s,
                   "body": [], "extra": True, "header": s}
            chapters.append(cur)
        elif short and SPLIT_VOLUME_RE.match(line):
            if chapters and chapters[-1]["vol"] == vol:
                vol += 1
            extras.append(s)
            cur = None
        elif cur is None:
            extras.append(line.rstrip())
        else:
            cur["body"].append(line.rstrip())
    if not chapters:
        sys.exit("没有识别到“第X章”标题行")

    out = Path(a.root) / "chapters"
    plan = []
    main_idx, extra_seq, idx = a.start - 1, 0, a.start
    for ch in chapters:
        safe = re.sub(r'[\\/:*?"<>|\s]+', "", ch["title"]) or "无题"
        body = "\n".join(ch["body"]).strip("\n")
        if ch.get("extra"):
            if extra_seq >= 26:
                sys.exit(f"第 {main_idx} 章后的番外超过 26 个，超出 NNNNx 命名容量")
            target = out / f"vol{ch['vol']:02d}" / f"{main_idx:04d}{chr(ord('a') + extra_seq)}-{safe}.txt"
            plan.append((target, f"{ch['header']}\n\n{body}\n"))
            extra_seq += 1
        else:
            main_idx, extra_seq = idx, 0
            target = out / f"vol{ch['vol']:02d}" / f"{idx:04d}-{safe}.txt"
            plan.append((target, f"第{idx}章 {ch['title']}\n\n{body}\n"))
            idx += 1
    clash = [t for t, _ in plan if t.exists()]
    if clash:
        sys.exit(f"目标文件已存在，未写入任何文件：{clash[0]} 等 {len(clash)} 个")
    for target, content in plan:
        if a.dry_run:
            print(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    extra_text = "\n".join(extras).strip()
    if extra_text and not a.dry_run:
        extra_path = Path(a.root) / "drafts" / "import-extras.txt"
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text(extra_text + "\n", encoding="utf-8")
        print(f"非章节文字已存到 {extra_path}")
    main_cnt = idx - a.start
    suffix = f" + {len(plan) - main_cnt} 个番外" if len(plan) > main_cnt else ""
    print(f"{'预览' if a.dry_run else '已切分'} {main_cnt} 章{suffix}，{vol} 卷")


def _retitle_chapter(path: Path) -> None:
    """把章节文件首行“第X章”的章号 +1（阿拉伯/中文数字都保持原写法）。只动首个非空行。"""
    lines = read_text(path).splitlines(keepends=True)
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = re.match(rf"^(\s*)第([{CN_NUM}]+)(章.*)$", line.rstrip("\n"))
        if not m:
            return
        v = cn2int(m.group(2))
        if v is None:
            return
        new = str(v + 1) if m.group(2).isdigit() else int2cn(v + 1)
        lines[i] = m.group(1) + "第" + new + m.group(3) + ("\n" if line.endswith("\n") else "")
        path.write_text("".join(lines), encoding="utf-8")
        return


def _shift_md_refs(text: str, after: int) -> tuple[str, int]:
    """把 markdown 文本里 >after 的章号引用 +1，返回（新文本, 改动处数）。

    覆盖：第N章（阿/中文数字）、标题行 NNNNx、列表项首 NNNNx、
    frontmatter 值、（NNNN）括注、[[NNNN]]、行尾“关键词：NNNN”，
    以及表头含“章”的表格列内的章号集合（0005 / 0001-0030 / 0005、0008）。
    正文语义（故事内年份、字数等）不在这类写法里，不动。
    """
    cnt = 0

    def bump_num(raw: str) -> str | None:
        nonlocal cnt
        v = cn2int(raw)
        if v is None or v <= after:
            return None
        cnt += 1
        return f"{v + 1:0{len(raw)}d}" if raw.isdigit() else int2cn(v + 1)

    def bump_tok(raw: str) -> str:
        nonlocal cnt
        m = re.fullmatch(r"(\d{4})([a-z]?)", raw)
        if not m or int(m.group(1)) <= after:
            return raw
        cnt += 1
        return f"{int(m.group(1)) + 1:04d}{m.group(2)}"

    def rep(g: int):
        def inner(m: re.Match) -> str:
            raw = m.group(g)
            new = bump_tok(raw) if re.fullmatch(r"\d{4}[a-z]?", raw) else (bump_num(raw) or raw)
            if new == raw:
                return m.group(0)
            return (m.group(0)[:m.start(g) - m.start(0)] + new
                    + m.group(0)[m.end(g) - m.start(0):])
        return inner

    text = re.sub(rf"第\s*([{CN_NUM}]+)\s*章", rep(1), text)
    text = re.sub(r"(?m)^(#{1,6}\s+)(\d{4}[a-z]?)(?=\s|$)", rep(2), text)
    text = re.sub(r"(?m)^(\s*[-*]\s+)(\d{4}[a-z]?)(?=[\s:：，,、]|$)", rep(2), text)
    text = re.sub(r"(?m)^(\s*[A-Za-z_][\w-]*\s*:\s*)(\d{4}[a-z]?)\s*$", rep(2), text)
    text = re.sub(r"([(（]\s*)(\d{4}[a-z]?)(\s*[)）])", rep(2), text)
    text = re.sub(r"(\[\[)(\d{4}[a-z]?)(]])", rep(2), text)
    text = re.sub(
        r"(?m)^([^\n|]{0,40}(?:章节|进度|截至|首现|出场|埋设|回收)[^\n:：]{0,12}[:：]\s*)(\d{4}[a-z]?)\s*$",
        rep(2), text)

    # 表格：只改表头含“章”的列；格内所有 NNNNx 记号（含区间/列举）一起平移
    lines = text.splitlines()
    chap_cols: set[int] = set()
    in_table = False
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table:
            # 章号列：表头含“章”但不是章名/标题/名称（避免误伤章名格里的年份等数字）
            chap_cols = {j for j, c in enumerate(cells)
                         if "章" in c and not any(x in c for x in ("名", "题", "称"))}
            in_table = True
            continue
        if all(re.fullmatch(r":?-+:?", c or "-") for c in cells):
            continue
        raw = line.split("|")
        for j in chap_cols:
            if j + 1 < len(raw):
                raw[j + 1] = re.sub(r"(?<!第)\d{4}[a-z]?", lambda m: bump_tok(m.group(0)), raw[j + 1])
        lines[i] = "|".join(raw)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), cnt


def cmd_insert(a: argparse.Namespace) -> None:
    root = Path(a.root)
    files = chapter_files(root)

    if a.extra:
        anchor = a.num
        if anchor < 0:
            sys.exit("锚点章号不能为负")
        main_nums = {n for n, s, _ in files if not s}
        if anchor and anchor not in main_nums:
            sys.exit(f"没有第 {anchor} 章（番外要锚在已有主线章之后；0 表示全书开头）")
        used = sorted(s for n, s, _ in files if n == anchor and s)
        letter = next((c for c in "abcdefghijklmnopqrstuvwxyz" if c not in used), None)
        if letter is None:
            sys.exit(f"第 {anchor} 章后的番外位已用满（a-z）")
        slot = f"{anchor:04d}{letter}"
        anchor_path = next((p for n, s, p in files if n == anchor and not s), None)
        vol_dir = anchor_path.parent if anchor_path else root / "chapters" / "vol01"
        seq_cn = int2cn(ord(letter) - ord("a") + 1)
        print(f"番外位：{slot}（首行写作“番外{seq_cn} 章名”或“番外 章名”，楔子/序章亦可）")
        print(f"建议路径：{vol_dir.relative_to(root) / f'{slot}-章名.txt'}")
        if used:
            print(f"该锚点已有番外：{'、'.join(f'{anchor:04d}{x}' for x in used)}")
        return

    mains = [(n, p) for n, s, p in files if not s]
    if not mains:
        sys.exit("还没有章节，无需插入")
    hi = mains[-1][0]
    if a.num >= hi:
        sys.exit(f"第 {a.num} 章已是最后一章（共 {hi} 章），直接续写即可")
    if a.num < 0:
        sys.exit("章号不能为负")

    # >N 的章节文件（番外随锚点一起移动）与章纲重编号；从大到小改名避免覆盖
    moving = sorted(((n, s, p) for n, s, p in files if n > a.num), reverse=True)
    renames = [(p, p.with_name(f"{n + 1:04d}{s}-{p.name.split('-', 1)[1]}"), s)
               for n, s, p in moving]
    outlines = []
    oc = root / "outline" / "chapters"
    if oc.is_dir():
        for p in oc.glob("*.md"):
            m = re.match(r"^(\d{4,})([a-z]?)\.md$", p.name)
            if m and int(m.group(1)) > a.num:
                outlines.append(
                    (p, p.with_name(f"{int(m.group(1)) + 1:04d}{m.group(2)}.md")))
        outlines.sort(key=lambda t: t[0].name, reverse=True)

    if a.dry_run:
        for old, new, _ in renames + [(o, n, "") for o, n in outlines]:
            print(f"{old.relative_to(root)} -> {new.relative_to(root)}")
        print(f"（预览）第 {a.num} 章后空出 {a.num + 1:04d} 位："
              f"移动 {len(renames)} 章、{len(outlines)} 份章纲，并同步 memory/outline/lore/AGENTS.md 引用")
        return

    for old, new, s in renames:
        old.rename(new)
        if not s:
            _retitle_chapter(new)
    for old, new in outlines:
        old.rename(new)

    touched = []
    targets = [p for d in ("memory", "outline", "lore")
               for p in (root / d).rglob("*.md") if not p.is_symlink()]
    agents = root / "AGENTS.md"
    if agents.exists():
        targets.append(agents)
    for p in targets:
        new_text, n = _shift_md_refs(read_text(p), a.num)
        if n:
            p.write_text(new_text, encoding="utf-8")
            touched.append(f"{p.relative_to(root)}（{n} 处）")

    print(f"已在第 {a.num} 章后空出 {a.num + 1:04d} 位：移动 {len(renames)} 章、{len(outlines)} 份章纲")
    if touched:
        print(f"同步引用 {len(touched)} 个文件：" + "、".join(touched[:8]))
    print("请抽查引用更新是否符合预期（drafts/ 与正文内容不会改动）")


def cmd_validate(a: argparse.Namespace) -> None:
    root = Path(a.root)
    errors: list[str] = []
    warns: list[str] = []
    fixed: list[str] = []

    # 1. 必需文件（机制文件，与作品内容无关）
    for p in ("AGENTS.md", "lore/glossary.md", "memory/state.md", "memory/threads.md"):
        if not (root / p).exists():
            errors.append(f"缺少必需文件：{p}")

    agents = root / "AGENTS.md"
    if agents.exists():
        placeholders = re.findall(r"\{[^}]+\}", read_text(agents))
        if placeholders:
            warns.append(f"AGENTS.md 包含 {len(placeholders)} 个未填充占位符：{', '.join(placeholders[:5])}")

    # 2. 设定分类注册表 ↔ 实际目录（注册表在 AGENTS.md，目录可以任意命名、任意嵌套）
    cats = load_categories(root)
    reg_dirs = {c["dir"] for c in cats}
    real_dirs = _lore_dirs_with_md(root)
    for c in cats:
        if not (root / "lore" / c["dir"]).is_dir():
            warns.append(f"注册表中的分类没有对应目录：{c['name']} -> lore/{c['dir']}/")
    unregistered = sorted(real_dirs - reg_dirs)
    if unregistered:
        warns.append(f"{len(unregistered)} 个 lore 目录未登记到注册表："
                     f"{', '.join('lore/' + d + '/' for d in unregistered[:5])}")

    ents = entity_files(root)
    stray = [p.name for p in (root / "lore").glob("*.md")
             if p.name != "glossary.md" and not p.name.startswith("_")] if (root / "lore").is_dir() else []
    if stray:
        warns.append(f"lore/ 根目录有 {len(stray)} 个散文件（不属于任何分类）：{', '.join(stray[:5])}")

    # 3. glossary ↔ 实体文件
    glossary_path = root / "lore" / "glossary.md"
    missing_in_glossary: set[str] = set()
    if glossary_path.exists():
        gtext = read_text(glossary_path)
        rows = _glossary_rows(gtext)
        entry_names = {r[0] for r in _glossary_data_rows(rows) if r and r[0]}
        stems = {p.stem for p in ents}
        missing_in_glossary = stems - entry_names
        if missing_in_glossary:
            warns.append(f"{len(missing_in_glossary)} 个 lore 文件未登记到 glossary："
                         f"{', '.join(sorted(missing_in_glossary)[:5])}")
        # "设定文件"列写了路径但文件不存在才算问题；术语本来就没有文件
        file_col = next((i for i, c in enumerate(rows[0]) if "设定文件" in c or c == "文件"), None) if rows else None
        if file_col is not None:
            stem_set = {p.stem for p in ents} | {"glossary"}
            stale = []
            for r in _glossary_data_rows(rows):
                if len(r) <= file_col or not r[0]:
                    continue
                ref = r[file_col].strip("` ")
                if ref and (ref.endswith(".md") or "/" in ref) \
                        and not (root / ref).exists() and not (root / "lore" / ref).exists() \
                        and Path(ref).stem not in stem_set:
                    stale.append(f"{r[0]} -> {ref}")
            if stale:
                warns.append(f"{len(stale)} 个 glossary 条目的设定文件路径无效：{', '.join(stale[:5])}")

    # 4. 章节编号连续性与番外规范
    files = chapter_files(root)
    if files:
        nums = [n for n, s, _ in files if not s]
        if nums:
            missing = sorted(set(range(1, nums[-1] + 1)) - set(nums))
            if missing:
                warns.append(f"章节编号不连续，缺少：{', '.join(f'{m:04d}' for m in missing[:10])}")
        main_nums = set(nums)
        no_anchor = [f"{n:04d}{s}" for n, s, _ in files
                     if s and n and n not in main_nums]
        if no_anchor:
            warns.append(f"{len(no_anchor)} 个番外没有对应主线章：{', '.join(no_anchor[:10])}")
        seq: dict[int, list[str]] = {}
        for n, s, _ in files:
            if s:
                seq.setdefault(n, []).append(s)
        for n, letters in sorted(seq.items()):
            expected = [chr(ord("a") + i) for i in range(len(letters))]
            if letters != expected:
                warns.append(f"第 {n} 章的番外编号不连续：{''.join(letters)}（应为 {''.join(expected)}）")
    stray_txt = [p.relative_to(root).as_posix()
                 for p in (root / "chapters").rglob("*.txt")
                 if not CHAPTER_FILE_RE.match(p.name)] if (root / "chapters").is_dir() else []
    if stray_txt:
        warns.append(f"{len(stray_txt)} 个章节文件名不规范（未被识别）：{', '.join(stray_txt[:5])}")

    # 5. frontmatter 检查：覆盖所有分类目录（含自定义、嵌套），_schema.md 等元文件除外
    bad_fm: list[tuple[Path, str]] = []
    for p in ents:
        text = read_text(p)
        if not text.startswith("---"):
            bad_fm.append((p, "缺少 frontmatter"))
            continue
        end = text.find("\n---", 3)
        if end < 0:
            bad_fm.append((p, "frontmatter 未闭合"))
            continue
        if "name:" not in text[3:end]:
            bad_fm.append((p, "frontmatter 缺少 name"))
    for p, reason in bad_fm[:5]:
        errors.append(f"{p.relative_to(root)}: {reason}")
    if len(bad_fm) > 5:
        errors.append(f"...其余 {len(bad_fm) - 5} 个文件也有 frontmatter 问题")

    # 规则文件 frontmatter 合法性（scope/priority 写错在编译期不报错，在这里提示）
    if GLOBAL_RULES_DIR.is_dir() or (root / "rules").is_dir():
        warns += _collect_rules(root)[1]

    # 6. 自动修复
    if a.fix:
        if missing_in_glossary and glossary_path.exists():
            lines = gtext.splitlines()
            sep = next((i for i, l in enumerate(lines)
                        if "-" in l and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", l)), None)
            if sep is not None:
                cols = max(2, len([c for c in lines[sep].strip().strip("|").split("|")]))
                new = [f"| {n} |" + " |" * (cols - 1) for n in sorted(missing_in_glossary)[:20]]
                lines[sep + 1:sep + 1] = new
                glossary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                fixed.append(f"{len(new)} 个 lore 文件补登到 glossary")
        if unregistered and agents.exists():
            text = read_text(agents)
            for d in unregistered:
                text = _upsert_registry(text, d, d)
                fixed.append(f"注册分类：{d} -> lore/{d}/")
            agents.write_text(text, encoding="utf-8")

    # 输出
    print(f"== 项目验证：{root} ==")
    if errors:
        print(f"\n[错误] × {len(errors)}")
        for e in errors:
            print(f"  {e}")
    if warns:
        print(f"\n[警告] × {len(warns)}")
        for w in warns:
            print(f"  {w}")
    if fixed:
        print(f"\n[已修复] ✓ {len(fixed)}")
        for f in fixed:
            print(f"  {f}")
    if not errors and not warns:
        print("✓ 项目完整性检查通过")
    sys.exit(1 if errors else 0)


def cmd_category(a: argparse.Namespace) -> None:
    root = Path(a.root)
    lore = root / "lore"
    agents = root / "AGENTS.md"

    def norm_dir(d: str) -> str:
        d = d.strip().strip("/")
        if d.startswith("lore/"):
            d = d[5:]
        for seg in d.split("/"):
            if not seg or seg.startswith(".") or seg == "..":
                sys.exit(f"非法目录名：{d}")
        return d

    if a.action == "list":
        cats = load_categories(root)
        real = _lore_dirs_with_md(root)
        print("== 设定分类注册表 ==")
        if not cats:
            print("（空。用 'category add 中文名 目录名' 添加，或手动编辑 AGENTS.md“设定分类”表）")
        for c in cats:
            ok = (lore / c["dir"]).is_dir()
            print(f"  {c['name']} -> lore/{c['dir']}/" + ("" if ok else "  ⚠ 目录不存在"))
        unreg = sorted(real - {c["dir"] for c in cats})
        if unreg:
            print("未登记的 lore 目录：")
            for d in unreg:
                print(f"  lore/{d}/  （validate --fix 可自动补登记）")
        return

    if a.action == "add":
        if len(a.args) < 2:
            sys.exit("用法：category add 分类名 目录名 [--from 内建模板]")
        name, dircol = a.args[0].strip(), norm_dir(a.args[1])
        if not name:
            sys.exit("分类名不能为空")
        target = lore / dircol
        target.mkdir(parents=True, exist_ok=True)
        schema = target / "_schema.md"
        if not schema.exists():
            tpl = TEMPLATES / f"{a.from_}.md"
            body = ""
            if tpl.exists():
                t = tpl.read_text(encoding="utf-8")
                body = re.sub(r"\A---\n.*?\n---\n?", "", t, count=1, flags=re.S).lstrip()
            schema.write_text(
                f"---\nname: _schema\ntype: schema\nbase: {a.from_}\n---\n"
                f"<!-- 《{name}》分类的字段模板：建实体文件时参考本文件；小节可自由增删、层级不限。 -->\n\n"
                + body, encoding="utf-8")
            print(f"创建：lore/{dircol}/_schema.md（底稿：{a.from_}.md）")
        if agents.exists():
            if dircol not in {c["dir"] for c in load_categories(root)}:
                agents.write_text(_upsert_registry(read_text(agents), name, dircol), encoding="utf-8")
                print(f"登记：| {name} | lore/{dircol}/ | → AGENTS.md")
            else:
                print(f"注册表已有该目录：lore/{dircol}/")
        else:
            print("警告：没有 AGENTS.md，只创建了目录")
        print(f"完成：《{name}》 = lore/{dircol}/")

    elif a.action == "rename":
        if len(a.args) < 2:
            sys.exit("用法：category rename 旧目录 新目录 [--name 新分类名]")
        old, new = norm_dir(a.args[0]), norm_dir(a.args[1])
        src, dst = lore / old, lore / new
        if not src.is_dir():
            sys.exit(f"目录不存在：lore/{old}/")
        if dst.exists():
            sys.exit(f"目标已存在：lore/{new}/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        print(f"目录：lore/{old}/ → lore/{new}/")
        for f in (agents, lore / "glossary.md"):
            if f.exists():
                t, t2 = read_text(f), None
                t2 = t.replace(f"lore/{old}/", f"lore/{new}/")
                if t2 != t:
                    f.write_text(t2, encoding="utf-8")
                    print(f"更新引用：{f.relative_to(root)}")
        if a.name and agents.exists():
            t = read_text(agents)
            t2 = _rename_registry_row(t, new, a.name)
            if t2 != t:
                agents.write_text(t2, encoding="utf-8")
                print(f"注册表分类名：→《{a.name}》")


def cmd_rules(a: argparse.Namespace) -> None:
    root = Path(a.root)
    rules, warns = _collect_rules(root)
    if a.check:  # 只报告不写入
        cur = None
        agents = root / "AGENTS.md"
        if agents.exists():
            m = _RULES_PAT.search(read_text(agents))
            cur = m.group(0) if m else None
        expected = _rules_block(root) if (rules or cur is not None) else None
        if cur != expected:
            print("「规则」节过期：运行 novel.py rules 同步")
            sys.exit(1)
        print("「规则」节已是最新")
        return
    if rules:
        print("== 规则文件（编译顺序）==")
        for r in rules:
            sc = "+".join(s for s in RULE_SCOPES if s in r["scopes"])
            print(f"  [{sc}] {r['rel']}" + (f"  — {r['desc']}" if r["desc"] else ""))
    else:
        print("没有规则文件。本书放 rules/*.md，全局放 ~/.novel-skills/rules/*.md")
    for w in warns:
        print(f"[警告] {w}")
    if _sync_rules(root, announce=True):
        return  # 已打印新注入层
    if a.sync:
        _announce_rules(root, changed=False)
    else:
        print("AGENTS.md「规则」节已是最新")


def cmd_export(a: argparse.Namespace) -> None:
    root = Path(a.root)
    lo, hi = parse_range(a.range) if a.range else (0, sys.maxsize)
    files = [(n, p) for n, _, p in chapter_files(root) if lo <= n <= hi]

    if a.volumes:
        vol_lo, vol_hi = parse_range(a.volumes)

        def vol_num(p: Path) -> int:
            m = re.fullmatch(r"vol(\d+)", p.parent.name)
            return int(m.group(1)) if m else -1

        files = [(n, p) for n, p in files if vol_lo <= vol_num(p) <= vol_hi]

    if not files:
        sys.exit("没有找到符合条件的章节")

    out = Path(a.output)
    lines = [f"# 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

    agents_md = root / "AGENTS.md"
    if agents_md.exists():
        text = agents_md.read_text(encoding="utf-8")
        m = re.search(r"^# 《(.+)》", text, re.M)
        if m:
            lines[0] = f"# {m.group(1)}"

    cur_vol = None
    for n, p in files:
        vol = p.parent.name
        if vol != cur_vol:
            vol_md = root / "outline/volumes" / f"{vol}.md"
            if vol_md.exists():
                vol_text = vol_md.read_text(encoding="utf-8")
                m = re.search(r"^# 第(.+)卷 (.+)", vol_text, re.M)
                if m:
                    lines.extend(["", f"# 第{m.group(1)}卷 {m.group(2)}", ""])
            cur_vol = vol
        lines.extend(["", p.read_text(encoding="utf-8").strip(), ""])

    out.write_text("\n".join(lines), encoding="utf-8")
    total = sum(len(WS_RE.sub("", p.read_text(encoding="utf-8"))) for _, p in files)
    print(f"已导出 {len(files)} 章，共 {total} 字 → {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="书根目录，默认当前目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="创建标准目录与种子文件").set_defaults(fn=cmd_init)
    sub.add_parser("next", help="下一章章号与路径").set_defaults(fn=cmd_next)

    p = sub.add_parser("stats", help="章节字数统计")
    p.add_argument("--range", help="章号范围，如 1-50")
    p.add_argument("--min", type=int, default=0)
    p.add_argument("--max", type=int, default=0)
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("lint", help="单章格式与 AI 味检查")
    p.add_argument("file")
    p.add_argument("--min", type=int, default=0, help="字数下限")
    p.add_argument("--max", type=int, default=0, help="字数上限")
    p.add_argument("--long-para", type=int, default=300, help="长段落阈值（字）")
    p.set_defaults(fn=cmd_lint)

    p = sub.add_parser("find", help="检索正文")
    p.add_argument("terms", nargs="*", help="关键词")
    p.add_argument("--entity", action="append", default=[], help="实体名，自动加入 lore 中的 aliases，可重复")
    p.add_argument("--regex", action="store_true", help="关键词按正则处理")
    p.add_argument("--range", help="章号范围，如 1-50")
    p.add_argument("--all", action="store_true", help="同时检索 outline/ lore/ memory/")
    p.add_argument("--context", type=int, default=40, help="命中前后保留字数")
    p.add_argument("--limit", type=int, default=20, help="每个文件最多显示行数")
    p.add_argument("--count", action="store_true", help="只输出每章命中行数")
    p.add_argument("--first", action="store_true", help="只显示首次出现的章节")
    p.set_defaults(fn=cmd_find)

    p = sub.add_parser("similar", help="相似段落查重：单章对全书，或 --all 全书两两")
    p.add_argument("file", nargs="?", help="待查章节/草稿文件")
    p.add_argument("--all", action="store_true", help="全书段落两两查重")
    p.add_argument("--range", help="章号范围，如 1-50")
    p.add_argument("--top", type=int, default=15, help="最多显示条数")
    p.add_argument("--min-score", type=float, default=0.25, help="Jaccard 相似度阈值 0-1")
    p.set_defaults(fn=cmd_similar)

    p = sub.add_parser("split", help="整本 txt 切分成章节文件（番外识别为 NNNNx）")
    p.add_argument("file")
    p.add_argument("--start", type=int, default=1, help="起始章号")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_split)

    p = sub.add_parser("insert", help="在第 N 章后空出一个章位（重编号并同步引用）")
    p.add_argument("num", type=int, help="在此章号之后插入（0 表示全书开头）")
    p.add_argument("--extra", action="store_true", help="不插主线章，返回该锚点的空闲番外位")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_insert)

    p = sub.add_parser("category", help="设定分类注册表：list / add / rename")
    p.add_argument("action", choices=["list", "add", "rename"])
    p.add_argument("args", nargs="*",
                   help="add: 分类名 目录名；rename: 旧目录 新目录")
    p.add_argument("--from", dest="from_", default="entity",
                   help="add 时用作 _schema.md 底稿的内建模板（默认 entity）")
    p.add_argument("--name", help="rename 时的新分类名（不改可省略）")
    p.set_defaults(fn=cmd_category)

    p = sub.add_parser("rules", help="规则文件清单与编译（rules/ + ~/.novel-skills/rules/ → AGENTS.md「规则」节）")
    p.add_argument("--sync", action="store_true", help="同时展示当前注入层")
    p.add_argument("--check", action="store_true", help="只检查不写入，过期退出码 1")
    p.set_defaults(fn=cmd_rules)

    p = sub.add_parser("validate", help="检查项目完整性")
    p.add_argument("--fix", action="store_true", help="自动修复简单问题")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("export", help="导出全书")
    p.add_argument("--output", "-o", default="export.txt", help="输出文件")
    p.add_argument("--range", help="章号范围，如 1-50")
    p.add_argument("--volumes", help="卷号范围，如 1-3")
    p.set_defaults(fn=cmd_export)

    a = ap.parse_args()
    # 惰性规则编译：借每次 novel.py 调用检查一次，源文件变了就重编译并把新注入层打到输出。
    # init 播完种子后自己调 _sync_rules；rules 子命令自己处理（--check 必须不写入）。
    if a.cmd not in ("init", "rules"):
        _sync_rules(Path(a.root), announce=True)
    a.fn(a)


if __name__ == "__main__":
    main()
