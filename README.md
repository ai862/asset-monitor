# 资产监控中心

把 Notion 里的 **AI Web / 工控 Web / 信创 Web** 三张资产表镜像成静态页，方便国内网络快速浏览。数据在 `data/*.json`，配置在 `config.json`，无构建步骤。

线上：https://ai862.github.io/asset-monitor/

## 本地预览

必须用 HTTP 服务打开（`file://` 下 `fetch` JSON 会被浏览器拦截）：

```bash
cd monitor-hub
python3 -m http.server 8080
# 浏览器打开 http://127.0.0.1:8080/
```

或：

```bash
npx --yes serve .
```

## GitHub Pages

1. 把本目录推到仓库根目录，或 `docs/` / `gh-pages` 分支。
2. 仓库 Settings → Pages → Source 选对应分支/目录。
3. 已附带空文件 `.nojekyll`，避免 Jekyll 忽略 `data/` 等路径。

相对路径引用 `config.json`、`data/*.json`、`styles.css`、`app.js`，子路径托管也可直接用。

## AI Web 自动研判（OpenRouter + DeepWiki）

对 AI Web 资产生成 v2 引导字段（搭建难度、启动指引、开工前先看、建议追问、已知坑、成功标准等），写入 `data/ai-web.json` 后 Pages 自动更新。

### 密钥（务必保密）

- 在仓库 **Settings → Secrets and variables → Actions** 配置 `OPENROUTER_API_KEY`。
- Workflow **只**通过 `${{ secrets.OPENROUTER_API_KEY }}` 读取；日志里会 `::add-mask::`。
- **不要**把 key 写进代码、workflow inputs、`.env` 或提交到 Git。本地 `.env` / `*.env` 已在 `.gitignore`。

### 手动跑

若 Actions 里还没有该 workflow：把 `scripts/triage-ai-web.workflow.yml` 复制为 `.github/workflows/triage-ai-web.yml` 并提交（需具备创建 workflow 的权限 / `workflow` scope），或在 GitHub 网页上 Add file。

1. Actions → **Triage AI Web** → Run workflow。
2. 可选输入：
   - `dedupe_keys`：逗号分隔去重键（空=自动挑未研判）
   - `limit`：默认 3，最大 10
   - `force`：已研判也重跑
3. 有变更时 bot 会 commit `chore(triage): update AI Web guidance` 并推到 `main`。

每周日 14:00 UTC 也会自动扫一轮（limit 5）。

本地试跑（需自行 export 环境变量，勿把 key 打进终端历史到公开处）：

```bash
export OPENROUTER_API_KEY=…   # 勿提交
python3 scripts/triage_ai_web.py --keys rikyz90-shibaclaw --limit 1
python3 scripts/triage_ai_web.py --dry-run --limit 3
```

样例字段见 `triage-pilot/rikyz90-shibaclaw.v2.json`（已合并进 `data/ai-web.json`）。

网页上：打开 AI Web → 搜 `ShibaClaw` → 点「指引」看侧栏（含可分享链接）。

### Agent 如何读取指引

每条已研判资产会导出静态 JSON，供 Agent `fetch`：

- 表字段 `指引URL`（绝对地址）
- 或 `https://ai862.github.io/asset-monitor/assets/ai-web/{去重键}.json`

示例：

```bash
curl -sL https://ai862.github.io/asset-monitor/assets/ai-web/rikyz90-shibaclaw.json
```

人类深链（自动打开侧栏）：`?source=ai-web&id=rikyz90-shibaclaw`。研判流水线结束时会运行 `scripts/export_guidance_assets.py` 同步这些文件。

## 工控 / 信创 下载页补链（浏览器 + OpenRouter）

对 **工控 Web**、**信创 Web** 中「待核 / 下载页为空 / 下载页仅官网首页」的条目，用公开网页抓取 + 免费大模型判断官方下载中心或试用页，写回 `data/ics.json`、`data/xinchuang.json`（字段：`下载页`、`下载条件`、`状态`，并带 `下载核验时间` / `下载核验来源`）。**不会**编造安装包直链；仅商务预约则标「商务墙」。

- 密钥同上：仓库 Secret `OPENROUTER_API_KEY`（与 AI Web 研判共用）。
- Actions → **Find Downloads (ICS / 信创)** → Run workflow；可选 `source`（ics / xinchuang / both）、`dedupe_keys`、`limit`（默认 3，最大 8）、`force`、`max_steps`。
- 每周日 15:00 UTC 低流量自动跑一轮。
- 本地：`export OPENROUTER_API_KEY=…` 后执行 `python3 scripts/find_downloads.py --source xinchuang --keys nfschina-browser --limit 1`（勿提交 key）。无 Playwright 时回退 urllib。

## 扩展新监控源

1. 在 `data/` 新增 JSON 数组（字段名与现有表风格一致即可，至少含 `产品`、`厂商`、`状态`、`去重键`）。
2. 在 `config.json` 的 `sources` 追加一项：

```json
{
  "id": "new-source",
  "name": "新分类",
  "data": "data/new-source.json",
  "notion": "https://www.notion.so/...",
  "accent": "#ec4899"
}
```

3. （可选）若要在 UI 里加「类型/行业/层」一类筛选，在 `app.js` 的 `EXTRA_FIELD` 增加映射，并在表格渲染分支补列。
4. 更新 `updatedAt` 后刷新页面即可。

## 数据说明

- Checkbox 字段已转为布尔值（`true` / `false`）。
- `部署方式` 多为字符串数组。
- 页面只读；改资产请回 Notion，再重新导出 JSON。
- AI Web 的 v2 研判字段由 Actions 写入；页面侧栏只读展示。
