#!/usr/bin/env python3
"""网文项目工具箱，只依赖 Python 标准库。在书根目录运行（或用 --root 指定）。

子命令：
  init      创建通用骨架与种子文件（不覆盖已有文件；不含设定分类，分类用 category add）
  next      给出下一章章号、建议路径和上一章位置
  stats     统计章节字数
  lint      检查单章格式与 AI 味高频表达
  find      在正文中检索实体/关键词（--entity 自动带上 lore 里的别名）
  split     把整本 txt 按"第X章"切分成标准章节文件
  category  设定分类注册表：list / add / rename（注册表在 AGENTS.md"设定分类"一节）
  validate  检查项目完整性（必填字段、分类注册表、glossary、frontmatter、编号连续性）
  export    合并全书为单个 txt，可按卷或章号范围导出
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path
from datetime import datetime

TEMPLATES = Path(__file__).resolve().parent.parent / "assets" / "templates"

# 只建与作品内容无关的通用骨架；设定分类由用户决定后用 category add 添加
DIRS = (
    "chapters/vol01",
    "outline/volumes",
    "outline/chapters",
    "lore",
    "lore/images",
    "memory/summaries",
    "drafts",
)
# 目标路径 -> 模板文件名
SEEDS = {
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
SPLIT_CHAPTER_RE = re.compile(rf"^\s*第[{CN_NUM}]+[章回][ \u3000:：、.]*(.*)$")
SPLIT_VOLUME_RE = re.compile(rf"^\s*第[{CN_NUM}]+卷")
CHAPTER_FILE_RE = re.compile(r"^(\d{4,})-(.+)\.txt$")
CJK_RE = re.compile(f"[{CJK}]")
WS_RE = re.compile(r"\s")

MD_RE = re.compile(r"^(?:#{1,6}\s|[-*+]\s|>|\d+\.\s|(?:-{3,}|\*{3,}|_{3,})$)|\*\*|`")
HALF_PUNCT_RE = re.compile(rf"(?<=[{CJK}])[,.?!:;()]|[,.?!:;()](?=[{CJK}])")
ELLIPSIS_RE = re.compile(r"\.{2,}|。{2,}|(?<!…)…(?!…)|…{3,}")
DASH_RE = re.compile(rf"(?<!—)—(?!—)|—{{3,}}|-{{2,}}|(?<=[{CJK}])-(?=[{CJK}])")

# AI 味高频表达：命中不等于错误，密度才是问题。说明见 novel-craft/references/anti-ai.md
AI_PATTERNS = [
    (r"仿佛|宛如|犹如|恍若|恍如", "比喻连接词"),
    (r"不禁|不由得|不由自主", "不禁/不由得"),
    (r"缓缓|微微", "缓缓/微微"),
    (r"淡淡", "淡淡"),
    (r"一[丝抹缕]", "一丝/一抹/一缕"),
    (r"嘴角[^，。！？]{0,6}(?:勾起|扬起|上扬|弧度)", "嘴角弧度"),
    (r"[眼眸目瞳][中里底光内][^，。！？]{0,4}闪过", "眼中闪过"),
    (r"深吸(?:了)?一口气", "深吸一口气"),
    (r"心(?:中|头|里|下)一(?:凛|紧|动|震|沉|颤)", "心中一凛"),
    (r"(?:冷冷|淡淡|缓缓|轻轻|沉声|低声|柔声)(?:地)?(?:说道|道)", "副词+说道"),
    (r"说道", "说道"),
    (r"空气(?:仿佛|似乎|都|中)?(?:凝固|凝滞|安静)", "空气凝固"),
    (r"落针可闻|鸦雀无声|倒吸一口凉气", "围观套话"),
    (r"这一刻", "这一刻"),
    (r"[他她]知道[，,]", "他知道，"),
    (r"不是[^。！？\n]{1,25}[，,]而是", "不是……而是"),
    (r"不仅仅?是[^。！？\n]{1,25}[，,](?:更|还|也)是", "不仅是……更是"),
    (r"命运的齿轮|才刚刚开始|仅仅只是开始|一切才刚刚", "宿命式收尾"),
    (r"难以言喻|无法形容|说不清道不明|前所未有", "无法形容"),
    (r"指节(?:泛白|发白)|喉结(?:上下)?滚动|瞳孔(?:骤然|猛地|微微)?(?:一)?缩", "身体反应套话"),
    (r"眸(?:子|光|中|底)", "眸子"),
    (r"带着(?:几分|一丝|一抹|些许)", "带着几分"),
    (r"显得(?:格外|十分|异常|有些|尤为)", "显得格外"),
    (r"某种", "某种"),
    (r"与此同时", "与此同时"),
    (r"涌上心头|心头一暖|五味杂陈|百感交集", "情绪套话"),
    (r"弥漫着|交织|涟漪|璀璨|深邃|低语", "AI 偏爱词"),
]
AI_RES = [(re.compile(p), label) for p, label in AI_PATTERNS]


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


def chapter_files(root: Path) -> list[tuple[int, Path]]:
    found = []
    for p in (root / "chapters").rglob("*.txt"):
        m = CHAPTER_FILE_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found)


def parse_range(spec: str | None) -> tuple[int, int]:
    if not spec:
        return 0, sys.maxsize
    lo, _, hi = spec.partition("-")
    return int(lo), int(hi or lo)


def fmt_lines(nums: list[int], limit: int = 8) -> str:
    shown = " ".join(f"L{n}" for n in nums[:limit])
    return shown + (f" …(+{len(nums) - limit})" if len(nums) > limit else "")


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
    print("提示：骨架不含设定分类。问清用户后用 'category add 中文名 目录名 [--from 模板]' 按需添加。")


def cmd_next(a: argparse.Namespace) -> None:
    root = Path(a.root)
    files = chapter_files(root)
    if files:
        n, last = files[-1]
        vol_dir = last.parent
        missing = sorted(set(range(1, n + 1)) - {num for num, _ in files})
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
    rows = [(n, p) for n, p in chapter_files(root) if lo <= n <= hi]
    if not rows:
        sys.exit("没有找到章节文件（chapters/**/NNNN-章名.txt）")
    total = 0
    print("章号    字数    汉字  文件")
    for n, p in rows:
        lines = read_text(p).splitlines()
        _, hline = split_header(lines)
        words, han = word_count("\n".join(lines[hline:]))
        total += words
        flag = ""
        if a.min and words < a.min:
            flag = f"  偏少（<{a.min}）"
        elif a.max and words > a.max:
            flag = f"  偏多（>{a.max}）"
        print(f"{n:04d}  {words:>6}  {han:>6}  {p.relative_to(root)}{flag}")
    print(f"合计 {len(rows)} 章，{total} 字，平均 {total // len(rows)} 字/章")


def cmd_lint(a: argparse.Namespace) -> None:
    path = Path(a.file)
    lines = read_text(path).splitlines()
    errors: list[str] = []
    warns: list[str] = []

    header, hline = split_header(lines)
    if not HEADER_RE.match(header):
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
    files = [(f"{n:04d}", p) for n, p in chapter_files(root) if lo <= n <= hi]
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
        if m:
            cur = {"vol": vol, "title": m.group(1).strip() or "无题", "body": []}
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
    for idx, ch in enumerate(chapters, a.start):
        safe = re.sub(r'[\\/:*?"<>|\s]+', "", ch["title"]) or "无题"
        target = out / f"vol{ch['vol']:02d}" / f"{idx:04d}-{safe}.txt"
        body = "\n".join(ch["body"]).strip("\n")
        plan.append((target, f"第{idx}章 {ch['title']}\n\n{body}\n"))
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
    print(f"{'预览' if a.dry_run else '已切分'} {len(plan)} 章，{vol} 卷")


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

    # 4. 章节编号连续性
    files = chapter_files(root)
    if files:
        nums = [n for n, _ in files]
        missing = sorted(set(range(1, nums[-1] + 1)) - set(nums))
        if missing:
            warns.append(f"章节编号不连续，缺少：{', '.join(f'{m:04d}' for m in missing[:10])}")

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


def cmd_export(a: argparse.Namespace) -> None:
    root = Path(a.root)
    lo, hi = parse_range(a.range) if a.range else (0, sys.maxsize)
    files = [(n, p) for n, p in chapter_files(root) if lo <= n <= hi]

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

    p = sub.add_parser("split", help="整本 txt 切分成章节文件")
    p.add_argument("file")
    p.add_argument("--start", type=int, default=1, help="起始章号")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_split)

    p = sub.add_parser("category", help="设定分类注册表：list / add / rename")
    p.add_argument("action", choices=["list", "add", "rename"])
    p.add_argument("args", nargs="*",
                   help="add: 分类名 目录名；rename: 旧目录 新目录")
    p.add_argument("--from", dest="from_", default="entity",
                   help="add 时用作 _schema.md 底稿的内建模板（默认 entity）")
    p.add_argument("--name", help="rename 时的新分类名（不改可省略）")
    p.set_defaults(fn=cmd_category)

    p = sub.add_parser("validate", help="检查项目完整性")
    p.add_argument("--fix", action="store_true", help="自动修复简单问题")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("export", help="导出全书")
    p.add_argument("--output", "-o", default="export.txt", help="输出文件")
    p.add_argument("--range", help="章号范围，如 1-50")
    p.add_argument("--volumes", help="卷号范围，如 1-3")
    p.set_defaults(fn=cmd_export)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
