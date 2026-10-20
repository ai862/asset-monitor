# 资产监控中心

把 Notion 里的 **AI Web / 工控 Web / 信创 Web** 三张资产表镜像成静态页，方便国内网络快速浏览。数据在 `data/*.json`，配置在 `config.json`，无构建步骤。

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
