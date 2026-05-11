# BudgetFlow deck — 动画页导出 MP4 / GIF

动画源文件：[`motion/budgetflow-reel.html`](motion/budgetflow-reel.html)（React + Babel + 内联 animations 引擎）。

## 本地预览（建议 HTTP，不要长期依赖 `file://`）

在 `paper1/deck` 目录启动静态服务，再用浏览器打开：

```bash
cd /Lishun/_archive/.local_env_bak/research/AgentOS/paper1/deck
python -m http.server 8080
```

- 单独看 Reel：`http://127.0.0.1:8080/huashu_paper1/motion/budgetflow-reel.html`
- 整册翻页（含该页）：`http://127.0.0.1:8080/huashu_paper1/index.html`（最后一页为「Motion · Reel」）

## 依赖

- **Node.js** + **`playwright` 可被 `require('playwright')` 加载**：
  - 全局：`npm i -g playwright` 后再 `playwright install chromium`，导出时用 `NODE_PATH=$(npm root -g)`。
  - **本仓库快捷方式**：若未全局安装，可用 deck 下已有依赖：  
    `NODE_PATH=/…/paper1/deck/uupm_standalone/node_modules`（需已 `npm install`）。
- **ffmpeg** 在 `PATH` 中。部分精简/conda 构建**没有 libx264** 或 OpenH264 版本不匹配：`render-video.js` 会依次尝试 **libx264 → libopenh264 → mpeg4**；生成的 `.mp4` 若为 mpeg4 编码，宜用带 libx264 的 ffmpeg 重编码后再对外分发。

## 导出命令（技能包脚本路径）

将 `SKILL` 换成本机实际路径（以下为 Cursor 全局技能目录，与 `~/.cursor/skills/huashu-design` 等价）：

```bash
SKILL=/root/.cursor/skills/huashu-design
REEL=/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/deck/huashu_paper1/motion/budgetflow-reel.html
```

**1) 25fps MP4**（与 HTML 同目录，输出 `budgetflow-reel.mp4`）：

```bash
NODE_PATH=$(npm root -g) node "$SKILL/scripts/render-video.js" "$REEL" --duration=22
# 或未全局安装 playwright 时（需先在 uupm_standalone 执行过 npm install）：
# NODE_PATH=/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/deck/uupm_standalone/node_modules \
#   node "$SKILL/scripts/render-video.js" "$REEL" --duration=22
```

片长与 Stage 的 `duration` 一致（当前 22s）；若改 HTML 里 `const D = …` 请同步改 `--duration`。

**2) 60fps MP4 + palette GIF**：

```bash
bash "$SKILL/scripts/convert-formats.sh" "$(dirname "$REEL")/budgetflow-reel.mp4" 960
```

产出：`budgetflow-reel-60fps.mp4`、`budgetflow-reel.gif`。

**3) 可选：为 60fps MP4 混入 BGM**

```bash
bash "$SKILL/scripts/add-music.sh" "$(dirname "$REEL")/budgetflow-reel-60fps.mp4" --mood=tech
```
