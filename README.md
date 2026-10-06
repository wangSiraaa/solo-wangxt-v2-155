# 双人复式桥牌 MP 计分应用

一个面向俱乐部双人赛的可审计计分系统：

- **牌面分**：由成约方、加倍状态、超墩/宕墩和局况计算；后端使用 [`endplay`](https://pypi.org/project/endplay/) 的 `Contract.score()`、`Vul.from_board()`、`Player.from_board()` 等牌局/计分能力，并用同一套显式分解输出来交叉核对。
- **局况**：严格按牌号循环：`无局、NS、EW、双有、NS、EW、双有、无局 ...`；发牌人也由牌号得到。
- **统一符号**：所有结果统一保存为 `ns_score`：NS 得分为正，EW 得分为负；EW 分为其相反数。
- **MP比较**：胜一对比较得 1，负得 0，同分各得 0.5；NS 与 EW 的得点互为补数。
- **缺桌不是零分**：未上报桌位只进入 `missing_table_numbers` 和审计说明，不创建幻影零分，不参与胜负比较。
- **发布冻结**：发布排名时保存完整快照（比较集合、逐牌MP、排名、原始成绩），之后新增成绩不会改变已发布版本。
- **重复上报核对**：同桌同牌唯一；相同来源且相同内容幂等；不同来源或不同成绩一律保留到 `duplicate_reports`，不覆盖原录入。
- **裁判追查**：API 和界面均展示每一桌与其他每一已上报桌的逐项比较，而不只是最终排名。

## 技术栈

- Backend：FastAPI、SQLAlchemy、PostgreSQL、endplay
- Frontend：React、TypeScript、Vite
- 测试：pytest、FastAPI TestClient

## 快速启动

### Docker Compose

```bash
docker compose up --build
```

- API：<http://localhost:8000>
- Swagger：<http://localhost:8000/docs>
- React：<http://localhost:5173>
- PostgreSQL：localhost:5432，数据库 `bridge_scoring`，用户/密码 `bridge/bridge`

### 本地运行

后端：

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://bridge:bridge@localhost:5432/bridge_scoring'
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

首次启动 API 时会创建所需数据表。生产环境建议替换为 Alembic 迁移和受限数据库账号。

## 数据模型

PostgreSQL 中保存：

- `events`：赛事和桌数。
- `boards`：牌号及由牌号确定的局况。
- `rotation_assignments`：每牌、每桌的 NS/EW 轮转安排。
- `result_entries`：已接受的原始录入、来源、牌面分及分项拆解。
- `duplicate_reports`：所有同桌同牌重复上报及核对说明。
- `publications`：发布时的不可变排名快照、逐牌MP和结果集合。

创建赛事时可传完整 `rotation`；未传时使用一个简单 Mitchell 示范轮转，真实比赛建议导入俱乐部实际轮转表。

## API 摘要

### 创建赛事

```bash
curl -X POST http://localhost:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{"name":"周五双人赛","table_count":3,"board_numbers":[1,2,3]}'
```

### 录入牌局

字段：

- `declarer`: `N/E/S/W`
- `doubled`: `none/doubled/redoubled`
- `overtricks` 与 `undertricks` 不能同时非零
- `passed_out=true` 表示全 PASS；此时不得给合约、庄位或加倍

例：第2牌（NS有局），北家主打 4SX，宕2：

```bash
curl -X POST http://localhost:8000/api/events/1/results \
  -H 'Content-Type: application/json' \
  -d '{
    "board_number":2,
    "table_number":1,
    "declarer":"N",
    "level":4,
    "denomination":"S",
    "doubled":"doubled",
    "overtricks":0,
    "undertricks":2,
    "source":"tablet-1"
  }'
```

### 查看逐牌比较

```bash
curl http://localhost:8000/api/events/1/boards/2/matchpoints
```

返回中包含：

- `compared_table_count` / `expected_table_count`
- `missing_table_numbers`
- 每桌的 `ns_matchpoints`、`ew_matchpoints`
- `comparisons`：与每个对手桌的比较、得分和结果（胜/平/负）
- `note`：明确说明缺桌未计零分

### 发布排名

```bash
curl -X POST 'http://localhost:8000/api/events/1/publications?note=终稿'
```

发布后可通过 `/api/events/1/publications/latest` 查看固定版本。

## 手算案例

### 1. 有局、加倍、宕约

第2牌是 NS 有局。北家主打 `4SX-2`，NS 为成约方且有局。

加倍有局宕墩罚分：

- 宕1：200
- 宕2：200 + 300 = **500**

合约失败没有定约分、奖分、超墩或成约奖分。因此：

- Declarer score / NS score：**-500**
- EW score：**+500**

后端测试见 `backend/tests/test_scoring.py::test_vulnerable_doubled_undertrick_hand_example`。

### 2. 并列分

三桌同一牌，以 NS 符号表示：

| 桌 | NS分 | 比较 | NS MP |
|---|---:|---|---:|
| 1 | +420 | 胜桌3，平桌2 | 1 + 0.5 = **1.5** |
| 2 | +420 | 胜桌3，平桌1 | 1 + 0.5 = **1.5** |
| 3 | -50 | 负于桌1、桌2 | **0** |

EW MP 分别为 `max - NS MP`：0.5、0.5、2。测试见 `test_tied_scores_receive_split_matchpoints`。

### 3. 缺一桌

三桌赛程中只有桌1和桌2上报：

- 桌1：NS +420
- 桌2：NS -50
- 桌3：未打，**不填0**

实际比较集合大小为 2，最大MP为 1：

- 桌1 NS 胜桌2：**1 MP**
- 桌2 NS 负于桌1：**0 MP**
- 桌3不进入比较，不把 +420 当作赢一个零分幻影桌
- API 返回 `missing_table_numbers: [3]`，并注明“未计零分”

若只有一桌有效成绩，则没有比较对象，该牌最大MP为 0，不凭空给该桌满分。测试见 `test_missing_table_is_not_zero_and_only_reported_results_are_compared` 和 `test_single_report_has_no_matchpoint_comparison`。

## 测试

```bash
cd backend
PYTHONPATH=. pytest -q
```

当前覆盖：

- 牌号局况循环
- 有局加倍宕约
- 加倍成约、超墩、奖分
- 再加倍成约的 endplay/显式公式一致性
- PASS 零分与缺桌区分
- 并列MP
- 缺桌不计零
- 单桌无可比较对象
- 排名分母排除未打牌
- FastAPI 录入、逐牌追查、重复来源核对和发布快照

前端构建：

```bash
cd frontend
npm run build
```

## 审计原则

1. 原始录入不可被重复上报静默覆盖。
2. 已接受结果和冲突上报都保留来源与原始 JSON。
3. MP永远能展开到“本桌对哪一桌、得到多少点”。
4. 发布的是某个时刻的比较集合和快照，而不是随时变化的数据库视图。
5. PASS 的零分是真实结果；缺桌没有结果，二者在数据结构和界面中明确区分。
