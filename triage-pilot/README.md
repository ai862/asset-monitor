# triage-pilot：方案二样例（已并入 `data/ai-web.json`）

- 样例：`rikyz90-shibaclaw.v2.json`（搭建难度=易）。
- 流水线：仓库根目录 `.github/workflows/triage-ai-web.yml` + `scripts/triage_ai_web.py`。
- 密钥：只用 GitHub Actions Secret `OPENROUTER_API_KEY`，不要提交 `.env` 或本目录以外的 key 文件。
- 模型试跑记录：`nvidia/nemotron-3-super-120b-a12b:free`（cost=0）；`openrouter/free` 曾被安全策略拦；Gemma free 曾 429。
- 研判时间样例：2026-10-20T13:28:48+08:00（Asia/Shanghai）。
