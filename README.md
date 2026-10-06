# 双人复式桥牌 MP 计分应用

本项目实现牌面分、逐牌 Matchpoint（MP）比较、缺桌审计、原始结果留存、重复上报核对和发布快照。

- `backend/`：FastAPI + SQLAlchemy + PostgreSQL，牌面分使用 `endplay` 的 `Contract` / `Vul`。
- `frontend/`：React + Vite，展示牌号、局况、各桌定约、牌面分、MP 和排名。
- `docker-compose.yml`：启动 PostgreSQL、后端和前端。

## 核心计分规则

1. 局况只按牌号的 16 牌标准循环推导：
   - 1、8、12、16 等按标准规则循环；代码直接使用 `endplay.types.Vul.from_board()`。
   - 第 2 牌为南北有局。
2. 所有存储分均以南北为符号基准：
   - 南北成约/防守得分：`score_ns` 为正。
   - 东西得分：`score_ew = -score_ns`。
   - 因此同一桌两边的分永远大小相同、符号相反。
3. MP 使用 2 分制：
   - `NS_MP = 2 × 低于本结果的 NS 分数数量 + 1 ×（同分数量 - 1）`
   - `EW_MP = 2(n-1) - NS_MP`
4. **没有结果的桌不生成记录、不按零分比较。**每牌只比较当前实际存在的 active 结果集合，该牌顶分为 `2(n-1)`。
5. 全 Pass 是一种明确结果，得 0/0；它和“未录入”严格区分。
6. 发布时复制比较集合、逐牌分数、MP、来源结果 ID 和排名；之后录入或改正不会改变历史发布。
7. 同桌同牌已有 active 结果时：
   - 完全相同的来源和载荷：幂等返回原结果。
   - 来源或内容不同：返回 409，要求核对来源；确需改正时走 correction 接口，旧记录标记为 `SUPERSEDED`。

## 快速启动

```bash
docker compose up --build
# API: http://localhost:8000/docs
# UI:  http://localhost:5173
```

本地开发后端：

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

本地前端：

```bash
cd frontend
npm install
npm run dev
```

默认本地开发可使用 SQLite；生产通过 `POSTGRES_HOST` 或 `DATABASE_URL` 指向 PostgreSQL。

## 内置手算案例

打开 UI 后点击“创建手算示例”，会创建第 2 牌（南北有局）的 4 桌轮转，但只录入 3 桌：

| 桌 | 定约 | 手算牌面分 | NS 牌面分 | EW 牌面分 | NS MP | EW MP |
|---:|---|---|---:|---:|---:|---:|
| 1 | 4♠X S -1 | 有局加倍首宕 200 给防守方 | -200 | 200 | 0 | 4 |
| 2 | 3♣ N = | 定约 3×20=60，不成局奖 50，共 110 | 110 | -110 | 3 | 1 |
| 3 | 2♦ N +1 | 定约 2×20=40，超墩 20，不成局奖 50，共 110 | 110 | -110 | 3 | 1 |
| 4 | 未录入 | 排除，不填零 | — | — | — | — |

并列时两桌 NS 各得 `(4 + 2) / 2 = 3`，EW 各得 1；低分桌 NS 得 0、EW 得顶分 4。第 4 桌出现在缺桌列表中，比较大小仍为 3，顶分仍为 4。

## 裁判审计入口

- `GET /events/{event_id}/audit`：总览，逐牌结果、MP、排名、缺桌及处理说明。
- `GET /events/{event_id}/boards/{board_no}/audit`：单牌追查，包含原始载荷、来源编号、录入员、定约人、超/宕墩、局况和 MP 公式。
- `GET /publications/{publication_id}`：冻结发布，逐牌保留 `source_result_id`。
- `POST /events/{event_id}/results/{result_id}/correction`：有来源的更正链。

## 测试

```bash
cd backend
PYTHONPATH=. pytest -q
cd ../frontend
npm run build
```

当前后端测试覆盖：

- 标准牌号局况循环；
- 有局加倍宕一；
- 成约奖分及 NS/EW 符号一致性；
- 并列 MP；
- 缺一桌时不补零、按实际比较集合给顶分；
- 并列排名；
- 全 Pass；
- API 重复上报核对；
- 发布快照固定比较集合和来源结果。
