#!/usr/bin/env python3
"""墨稿 · 网文写作台 WebUI

在书根目录运行：

    python3 .agents/skills/novel-webui/scripts/webui.py
    python3 .agents/skills/novel-webui/scripts/webui.py --root /path/to/book --port 8080

只依赖 Python 标准库。功能：章节与 lore 设定的浏览/编辑/新建/删除，自动保存。
纯编辑工具，不含 AI 生成功能；创作辅助交给 novel-* 技能。
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path.cwd()
APP_DIR = Path(__file__).resolve().parent / "app"

CHAPTER_RE = re.compile(r"^(\d+)-(.+)\.txt$")
BAD_NAME = re.compile(r'[\\/:*?"<>|]')


def words(text: str) -> int:
    """字数口径与 novel.py 一致：去掉所有空白后的字符数。"""
    return len(re.sub(r"\s", "", text))


def read_text(path: Path) -> str:
    """与 novel.py 相同的编码口径：UTF-8 优先，回退 GB18030。"""
    data = path.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def safe_path(base: Path, *parts: str) -> Path | None:
    """拼路径并确保解析结果仍在 base 内，否则返回 None。"""
    for p in parts:
        if not p or p.startswith(".") or p.startswith("/") or ".." in Path(p).parts:
            return None
    p = (base / Path(*parts)).resolve()
    return p if p == base or base in p.parents else None


CHAPTERS = LORE = None  # main() 里随 --root 一起赋值


def scan_chapters() -> dict:
    chapters_dir = CHAPTERS
    volumes = []
    max_num = 0
    for vol_dir in sorted(chapters_dir.glob("vol*")) if chapters_dir.is_dir() else []:
        if not vol_dir.is_dir():
            continue
        items = []
        for f in sorted(vol_dir.glob("*.txt")):
            m = CHAPTER_RE.match(f.name)
            num = int(m.group(1)) if m else 0
            if m:
                max_num = max(max_num, num)
            items.append({
                "id": f"{vol_dir.name}/{f.name}",
                "number": m.group(1) if m else "",
                "title": m.group(2) if m else f.stem,
                "words": words(read_text(f)),
            })
        items.sort(key=lambda c: (c["number"] or "9999", c["title"]))
        volumes.append({"name": vol_dir.name, "chapters": items})
    next_num = f"{max_num + 1:04d}"
    next_vol = volumes[-1]["name"] if volumes else "vol01"
    return {"volumes": volumes, "next": {"volume": next_vol, "number": next_num}}


def parse_lore_meta(path: Path) -> dict:
    """读 frontmatter 的 name/tags，取首个正文行做预览。"""
    text = read_text(path)
    name, tags, body = None, [], text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
            for line in parts[1].splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"\'')
                elif line.startswith("tags:"):
                    raw = line.split(":", 1)[1].strip().strip("[]")
                    tags = [t.strip().strip('"\'') for t in raw.split(",") if t.strip()]
    preview_parts = []
    for ln in body.splitlines():
        cleaned = re.sub(r"^[#>\-\s|]+", "", ln).replace("**", "").strip()
        if cleaned and cleaned != name:
            preview_parts.append(cleaned)
        if len(preview_parts) == 2:
            break
    preview = " · ".join(preview_parts)[:100]
    return {"name": name or path.stem, "filename": path.name,
            "tags": tags, "preview": preview}


def scan_lore() -> list[dict]:
    lore_dir = LORE
    if not lore_dir.is_dir():
        return []
    return [
        {"name": d.name, "items": [parse_lore_meta(f) for f in sorted(d.glob("*.md"))]}
        for d in sorted(lore_dir.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


def project_info() -> dict:
    name = ROOT.name
    agents = ROOT / "AGENTS.md"
    if agents.is_file():
        text = read_text(agents)
        m = (re.search(r"书名[^：:|\n]{0,4}[：:]\s*(.+)", text)      # - **书名**：X
             or re.search(r"书名\s*\|\s*([^|]+)", text))            # | 书名 | X |
        if m:
            name = m.group(1).strip().strip("《》* ")
    stats = scan_chapters()
    return {
        "name": name,
        "root": str(ROOT),
        "chapters": sum(len(v["chapters"]) for v in stats["volumes"]),
        "words": sum(c["words"] for v in stats["volumes"] for c in v["chapters"]),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "InkDraft/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 基础设施 ----------

    def log_message(self, fmt, *args):
        pass

    def json_out(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fail(self, msg, status=400):
        self.json_out({"error": msg}, status)

    def body(self) -> dict:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        return json.loads(raw.decode("utf-8") or "{}")

    def serve_static(self, path: str):
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        f = safe_path(APP_DIR, rel)
        if not f or not f.is_file():
            return self.send_error(404)
        ctype = {
            ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
            ".png": "image/png", ".woff2": "font/woff2",
        }.get(f.suffix, "application/octet-stream")
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---------- 路由 ----------

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        seg = [urllib.parse.unquote(s) for s in path.split("/") if s]
        try:
            if path == "/api/project":
                return self.json_out(project_info())
            if path == "/api/chapters":
                return self.json_out(scan_chapters())
            if path == "/api/lore/tree":
                return self.json_out(scan_lore())
            if len(seg) >= 3 and seg[:2] == ["api", "chapter"]:
                f = safe_path(CHAPTERS, "/".join(seg[2:]))
                if not f or not f.is_file():
                    return self.fail("章节不存在", 404)
                text = read_text(f)
                return self.json_out({"content": text, "words": words(text)})
            if len(seg) == 4 and seg[:2] == ["api", "lore-item"]:
                f = safe_path(LORE, seg[2], seg[3])
                if not f or not f.is_file():
                    return self.fail("设定不存在", 404)
                return self.json_out({"content": read_text(f)})
            if path.startswith("/api/"):
                return self.fail("未知接口", 404)
            self.serve_static(path)
        except (KeyError, json.JSONDecodeError):
            self.fail("请求格式错误")
        except OSError as e:
            self.fail(str(e), 500)

    def do_POST(self):
        seg = [urllib.parse.unquote(s) for s in urllib.parse.urlparse(self.path).path.split("/") if s]
        try:
            data = self.body()
            route = "/".join(seg[:2])
            if route == "api/chapter-save":
                f = safe_path(CHAPTERS, data["id"])
                if not f:
                    return self.fail("非法路径")
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(data["content"], encoding="utf-8")
                return self.json_out({"ok": True, "words": words(data["content"])})
            if route == "api/chapter-create":
                volume = re.sub(r"[^0-9A-Za-z_-]", "", data.get("volume", "")) or "vol01"
                number = int(data["number"])
                title = BAD_NAME.sub("", data["title"]).strip()
                if not title:
                    return self.fail("标题不能为空")
                name = f"{number:04d}-{title}.txt"
                f = safe_path(CHAPTERS, volume, name)
                if not f:
                    return self.fail("非法路径")
                if f.exists():
                    return self.fail("同名章节已存在", 409)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(f"第{number}章 {title}\n\n　　", encoding="utf-8")
                return self.json_out({"ok": True, "id": f"{volume}/{name}"})
            if route == "api/chapter-delete":
                f = safe_path(CHAPTERS, data["id"])
                if not f:
                    return self.fail("非法路径")
                if f.is_file():
                    f.unlink()
                return self.json_out({"ok": True})
            if route == "api/lore-category-create":
                name = BAD_NAME.sub("", data["name"]).strip()
                if not name:
                    return self.fail("分类名不能为空")
                f = safe_path(LORE, name)
                if not f:
                    return self.fail("非法分类名")
                f.mkdir(parents=True, exist_ok=True)
                return self.json_out({"ok": True, "name": name})
            if route == "api/lore-item-create":
                name = BAD_NAME.sub("", data["name"]).strip()
                if not name:
                    return self.fail("名称不能为空")
                filename = name if name.endswith(".md") else f"{name}.md"
                f = safe_path(LORE, data["category"], filename)
                if not f:
                    return self.fail("非法路径")
                if f.exists():
                    return self.fail("同名设定已存在", 409)
                f.parent.mkdir(parents=True, exist_ok=True)
                # type 用分类名的单数形式（characters→character）
                type_ = data["category"][:-1] if data["category"].endswith("s") else data["category"]
                stem = filename[:-3]
                f.write_text(
                    f"---\nname: {stem}\naliases: []\ntype: {type_}\ntags: []\n---\n\n# {stem}\n\n",
                    encoding="utf-8",
                )
                return self.json_out({"ok": True, "filename": filename})
            if route == "api/lore-item-save":
                f = safe_path(LORE, data["category"], data["filename"])
                if not f:
                    return self.fail("非法路径")
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(data["content"], encoding="utf-8")
                return self.json_out({"ok": True, "meta": parse_lore_meta(f)})
            if route == "api/lore-item-delete":
                f = safe_path(LORE, data["category"], data["filename"])
                if not f:
                    return self.fail("非法路径")
                if f.is_file():
                    f.unlink()
                return self.json_out({"ok": True})
            self.fail("未知接口", 404)
        except (KeyError, json.JSONDecodeError, ValueError):
            self.fail("请求格式错误")
        except OSError as e:
            self.fail(str(e), 500)

    def do_DELETE(self):
        seg = [urllib.parse.unquote(s) for s in urllib.parse.urlparse(self.path).path.split("/") if s]
        if len(seg) == 3 and seg[:2] == ["api", "lore-category"]:
            d = safe_path(LORE, seg[2])
            if not d or not d.is_dir():
                return self.fail("分类不存在", 404)
            if any(d.iterdir()):
                return self.fail("分类非空，请先删除其中的设定", 409)
            d.rmdir()
            return self.json_out({"ok": True})
        self.fail("未知接口", 404)


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("没有可用端口")


def main():
    global ROOT, CHAPTERS, LORE
    ap = argparse.ArgumentParser(description="墨稿 · 网文写作台 WebUI")
    ap.add_argument("--root", default=".", help="书根目录（默认当前目录）")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    ROOT = Path(args.root).resolve()
    CHAPTERS = ROOT / "chapters"
    LORE = ROOT / "lore"
    if not CHAPTERS.is_dir() and not LORE.is_dir():
        print(f"提示：{ROOT} 下没有 chapters/ 或 lore/，看起来不是书根目录，仍会启动。")

    port = free_port(args.port)
    url = f"http://localhost:{port}"
    print(f"墨稿 · {ROOT}")
    print(f"→ {url}   （Ctrl+C 停止）")

    if not args.no_browser:
        webbrowser.open(url)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
