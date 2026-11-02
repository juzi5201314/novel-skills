---
name: novel-webui
description: 本地写作台 WebUI（墨稿）：在浏览器中浏览和手动编辑章节正文、lore 设定文件，自动保存、字数统计、按卷分组、设定分类管理。纯编辑工具，不做 AI 生成。用户说"打开编辑器""启动 webui""可视化写作""看看章节列表"时使用。
---

# 墨稿 · 网文写作台 WebUI

给作者用的本地编辑界面，零依赖（Python 标准库 + 原生前端，无任何 CDN/联网资源）。它只管**手动浏览和编辑**：章节正文（`chapters/**/*.txt`）与设定文件（`lore/**/*.md`）。AI 创作、审稿、设定生成仍然走 novel-* 技能；WebUI 改的文件 skill 立即可见，反之亦然。

## 启动

在**书根目录**后台运行：

```bash
python3 .agents/skills/novel-webui/scripts/webui.py --no-browser &
# 或指定书目录 / 端口：
python3 .agents/skills/novel-webui/scripts/webui.py --root /path/to/book --port 8080
```

- 默认端口 8080，被占用时自动顺延（8080–8099）；启动输出里有最终 URL。
- 默认会用系统浏览器打开页面，`--no-browser` 关闭（agent 启动时应带上，然后把 URL 报给用户）。
- 前台 `Ctrl+C` 停止；后台运行时用 `kill` 结束进程即可。

## 功能边界

- 章节：按卷分组浏览、新建（自动建议下一章号）、编辑、删除；输入 1.2 秒自动保存，`Ctrl+S` 立即保存；状态栏实时字数（口径与 `novel.py` 一致：去空白字符数）。
- 设定：分类即 `lore/` 下的目录，不写死任何分类；新建文件自动写入 `name/aliases/type/tags` frontmatter（type 取分类名单数，符合 novel-core 模板约定）；删除非空分类会被拒绝。
- 页面结构、文件名规则、字数口径全部遵循 novel-core 约定；章号按全书连续四位补零。

## 注意

- 单用户本地工具，只监听 `127.0.0.1`，不用于多人协作或公网。
- 不要在 WebUI 运行期间手工大改目录结构（移动卷目录等）；正常编辑文件没有问题，刷新页面即生效。
- WebUI 不负责 memory 同步：在 WebUI 里手动改了已定稿章节后，提醒用户对 agent 说一声"第 N 章改过了，重新同步 memory"。
