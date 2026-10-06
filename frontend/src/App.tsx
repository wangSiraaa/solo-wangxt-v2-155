import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  api,
  BoardInfo,
  BoardMatchpoints,
  DuplicateReport,
  Event,
  PairRanking,
  Publication,
  ResultEntry,
  ResultForm,
} from './api';
import './styles.css';

const vulLabel: Record<string, string> = {
  none: '双方无局',
  NS: '南北有局',
  EW: '东西有局',
  both: '双方有局',
};

const emptyForm = (boardNumber: number): ResultForm => ({
  board_number: boardNumber,
  table_number: 1,
  declarer: 'N',
  level: 3,
  denomination: 'NT',
  doubled: 'none',
  overtricks: 0,
  undertricks: 0,
  passed_out: false,
  source: '',
});

function formatMp(value: number) {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function formatContract(row: ResultEntry | ResultForm) {
  if ('passed_out' in row && row.passed_out) return 'PASS';
  const doubled = row.doubled === 'redoubled' ? 'XX' : row.doubled === 'doubled' ? 'X' : '';
  return `${row.level}${row.denomination}${row.declarer}${doubled}`;
}

function scoreText(ns: number) {
  return ns === 0 ? '0' : ns > 0 ? `NS +${ns}` : `EW +${Math.abs(ns)}`;
}

export default function App() {
  const [events, setEvents] = useState<Event[]>([]);
  const [event, setEvent] = useState<Event | null>(null);
  const [boards, setBoards] = useState<BoardInfo[]>([]);
  const [results, setResults] = useState<ResultEntry[]>([]);
  const [matchpoints, setMatchpoints] = useState<BoardMatchpoints[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateReport[]>([]);
  const [publication, setPublication] = useState<Publication | null>(null);
  const [selectedBoard, setSelectedBoard] = useState(1);
  const [form, setForm] = useState<ResultForm>(emptyForm(1));
  const [eventName, setEventName] = useState('俱乐部双人赛');
  const [tableCount, setTableCount] = useState(3);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function refresh(eventId: number) {
    const [boardRows, resultRows, mpRows, duplicateRows] = await Promise.all([
      api.boards(eventId),
      api.results(eventId),
      api.matchpoints(eventId),
      api.duplicates(eventId),
    ]);
    setBoards(boardRows);
    setResults(resultRows);
    setMatchpoints(mpRows);
    setDuplicates(duplicateRows);
    setSelectedBoard((current) => (boardRows.some((row) => row.board_number === current) ? current : boardRows[0]?.board_number ?? 1));
    try {
      setPublication(await api.latestPublication(eventId));
    } catch {
      setPublication(null);
    }
  }

  async function loadEvents() {
    const rows = await api.listEvents();
    setEvents(rows);
    if (rows.length && !event) {
      await chooseEvent(rows[0]);
    }
  }

  async function chooseEvent(next: Event) {
    setEvent(next);
    setTableCount(next.table_count);
    await refresh(next.id);
  }

  useEffect(() => {
    loadEvents().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    setForm((current) => ({ ...current, board_number: selectedBoard }));
  }, [selectedBoard]);

  const selectedBoardInfo = boards.find((row) => row.board_number === selectedBoard);
  const selectedMp = matchpoints.find((row) => row.board_number === selectedBoard);
  const selectedResults = results.filter((row) => row.board_number === selectedBoard);

  const rankings = useMemo<PairRanking[]>(() => {
    if (!matchpoints.length) return [];
    const totals = new Map<number, { mp: number; max: number; boards: Set<number> }>();
    for (const board of matchpoints) {
      if (board.max_matchpoints <= 0) continue;
      for (const line of board.lines) {
        for (const pair of [line.ns_pair_number, line.ew_pair_number]) {
          const item = totals.get(pair) ?? { mp: 0, max: 0, boards: new Set<number>() };
          totals.set(pair, item);
        }
        const ns = totals.get(line.ns_pair_number)!;
        ns.mp += line.ns_matchpoints;
        ns.max += board.max_matchpoints;
        ns.boards.add(board.board_number);
        const ew = totals.get(line.ew_pair_number)!;
        ew.mp += line.ew_matchpoints;
        ew.max += board.max_matchpoints;
        ew.boards.add(board.board_number);
      }
    }
    return [...totals.entries()]
      .map(([pair_number, item]) => ({
        pair_number,
        total_matchpoints: item.mp,
        available_matchpoints: item.max,
        percentage: item.max ? (100 * item.mp) / item.max : null,
        boards_played: item.boards.size,
        boards_missing: [] as number[],
        rank: null,
      }))
      .sort((a, b) => (b.percentage ?? -1) - (a.percentage ?? -1))
      .map((row, index, array) => ({
        ...row,
        rank: index > 0 && array[index - 1].percentage === row.percentage ? array[index - 1].rank : index + 1,
      }));
  }, [matchpoints]);

  async function createEvent(submit: FormEvent) {
    submit.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const next = await api.createEvent({
        name: eventName,
        table_count: tableCount,
        board_numbers: Array.from({ length: tableCount }, (_unused, index) => index + 1),
      });
      setEvents((rows) => [...rows, next]);
      await chooseEvent(next);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function saveResult(submit: FormEvent) {
    if (!event) return;
    submit.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const saved = await api.submitResult(event.id, form);
      setMessage(`已保存：第 ${saved.table_number} 桌 ${formatContract(form)}，NS ${saved.ns_score}`);
      await refresh(event.id);
    } catch (error) {
      setMessage((error as Error).message);
      await refresh(event.id);
    } finally {
      setLoading(false);
    }
  }

  async function publish() {
    if (!event) return;
    setLoading(true);
    try {
      const next = await api.publish(event.id, '裁判发布：固定当前已上报比较集合');
      setPublication(next);
      setMessage(`已发布版本 ${next.version}`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header>
        <div>
          <h1>双人复式桥牌 MP 计分</h1>
          <p>逐牌记录牌面分、比较来源与MP；缺桌不补零，发布时冻结比较集合。</p>
        </div>
        <select value={event?.id ?? ''} onChange={(e) => chooseEvent(events.find((row) => row.id === Number(e.target.value))!)}>
          {events.map((row) => (
            <option key={row.id} value={row.id}>{row.name}</option>
          ))}
        </select>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="grid two">
        <form className="card" onSubmit={createEvent}>
          <h2>赛事与轮转</h2>
          <label>名称<input value={eventName} onChange={(e) => setEventName(e.target.value)} /></label>
          <label>桌数<input type="number" min={1} max={40} value={tableCount} onChange={(e) => setTableCount(Number(e.target.value))} /></label>
          <button disabled={loading}>创建示范赛事（牌号1..桌数）</button>
          {event && <p className="muted">当前：{event.name}，{event.table_count} 桌；PostgreSQL保存轮转与原始录入。</p>}
        </form>

        <div className="card">
          <h2>裁判提示</h2>
          <ul>
            <li>局况由牌号自动决定，NS为正、EW为负。</li>
            <li>PASS是真实零分结果；未打桌位只列入“缺少”。</li>
            <li>同桌同牌重复提交：相同同源幂等；异源或成绩冲突保留并等待核对。</li>
          </ul>
        </div>
      </section>

      {event && (
        <>
          <section className="card">
            <div className="section-title">
              <h2>牌号、局况与各桌对照</h2>
              <button onClick={publish} disabled={loading}>发布排名（冻结快照）</button>
            </div>
            <div className="board-tabs">
              {boards.map((board) => (
                <button
                  key={board.board_number}
                  className={board.board_number === selectedBoard ? 'active' : ''}
                  onClick={() => setSelectedBoard(board.board_number)}
                >
                  第{board.board_number}牌
                  {board.missing_table_numbers.length > 0 && <span className="badge">缺{board.missing_table_numbers.length}</span>}
                </button>
              ))}
            </div>

            {selectedBoardInfo && selectedMp && (
              <>
                <div className="board-meta">
                  <strong>第 {selectedBoardInfo.board_number} 牌</strong>
                  <span>发牌人：{selectedBoardInfo.dealer}</span>
                  <span>局况：{vulLabel[selectedBoardInfo.vulnerability]}</span>
                  <span>应有 {selectedBoardInfo.expected_table_numbers.length} 桌，已比较 {selectedMp.compared_table_count} 桌</span>
                </div>
                <p className="warning">{selectedMp.note}</p>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>桌</th><th>南北</th><th>东西</th><th>合约</th><th>结果</th><th>NS分</th><th>NS MP</th><th>EW MP</th><th>来源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedMp.lines.map((line) => {
                        const row = selectedResults.find((item) => item.id === line.result_id)!;
                        const result = row.passed_out ? 'PASS' : row.undertricks ? `宕 ${row.undertricks}` : `超 ${row.overtricks}`;
                        return (
                          <tr key={line.result_id}>
                            <td>{line.table_number}</td>
                            <td>{line.ns_pair_number}</td>
                            <td>{line.ew_pair_number}</td>
                            <td>{formatContract(row)}</td>
                            <td>{result}</td>
                            <td className={line.ns_score > 0 ? 'good' : line.ns_score < 0 ? 'bad' : ''}>{scoreText(line.ns_score)}</td>
                            <td>{formatMp(line.ns_matchpoints)} / {formatMp(line.max_matchpoints)}</td>
                            <td>{formatMp(line.ew_matchpoints)} / {formatMp(line.max_matchpoints)}</td>
                            <td>{row.source}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <h3>逐牌追查：每一对比较</h3>
                <div className="comparisons">
                  {selectedMp.lines.map((line) => {
                    const row = selectedResults.find((item) => item.id === line.result_id)!;
                    return (
                    <details key={line.result_id}>
                      <summary>第 {line.table_number} 桌（NS {line.ns_pair_number} / EW {line.ew_pair_number}）</summary>
                      <pre className="breakdown">{JSON.stringify(row.score_breakdown, null, 2)}</pre>
                      {line.comparisons.length === 0 ? <p>没有其他已上报结果可比较。</p> : (
                        <table>
                          <thead><tr><th>对手桌</th><th>对手NS分</th><th>NS结果</th><th>NS得点</th><th>EW得点</th></tr></thead>
                          <tbody>
                            {line.comparisons.map((comparison) => (
                              <tr key={comparison.opponent_result_id}>
                                <td>{comparison.opponent_table_number}</td>
                                <td>{scoreText(comparison.opponent_ns_score)}</td>
                                <td>{comparison.outcome_for_ns === 'better' ? '胜' : comparison.outcome_for_ns === 'tied' ? '平' : '负'}</td>
                                <td>{comparison.ns_matchpoints}</td>
                                <td>{comparison.ew_matchpoints}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </details>
                    );
                  })}
                </div>
              </>
            )}
          </section>

          <section className="grid two">
            <form className="card" onSubmit={saveResult}>
              <h2>录入第 {selectedBoard} 牌</h2>
              <label>桌号
                <input type="number" min={1} max={event.table_count} value={form.table_number}
                  onChange={(e) => setForm({ ...form, table_number: Number(e.target.value) })} />
              </label>
              <label className="checkbox"><input type="checkbox" checked={form.passed_out}
                onChange={(e) => setForm({ ...form, passed_out: e.target.checked })} /> 全pass（无合约）</label>
              {!form.passed_out && (
                <div className="form-row">
                  <label>水平<select value={form.level} onChange={(e) => setForm({ ...form, level: Number(e.target.value) })}>
                    {[1,2,3,4,5,6,7].map((n) => <option key={n}>{n}</option>)}
                  </select></label>
                  <label>花色<select value={form.denomination} onChange={(e) => setForm({ ...form, denomination: e.target.value as ResultForm['denomination'] })}>
                    {['C','D','H','S','NT'].map((n) => <option key={n}>{n}</option>)}
                  </select></label>
                  <label>庄位<select value={form.declarer} onChange={(e) => setForm({ ...form, declarer: e.target.value as ResultForm['declarer'] })}>
                    {['N','E','S','W'].map((n) => <option key={n}>{n}</option>)}
                  </select></label>
                  <label>加倍<select value={form.doubled} onChange={(e) => setForm({ ...form, doubled: e.target.value as ResultForm['doubled'] })}>
                    <option value="none">未加倍</option><option value="doubled">X</option><option value="redoubled">XX</option>
                  </select></label>
                </div>
              )}
              {!form.passed_out && (
                <div className="form-row">
                  <label>超墩<input type="number" min={0} max={13} value={form.overtricks}
                    onChange={(e) => setForm({ ...form, overtricks: Number(e.target.value), undertricks: 0 })} /></label>
                  <label>宕墩<input type="number" min={0} max={13} value={form.undertricks}
                    onChange={(e) => setForm({ ...form, undertricks: Number(e.target.value), overtricks: 0 })} /></label>
                </div>
              )}
              <label>来源标识<input required placeholder="tablet-2 / director-console" value={form.source}
                onChange={(e) => setForm({ ...form, source: e.target.value })} /></label>
              <button disabled={loading}>提交原始成绩</button>
            </form>

            <div className="card">
              <h2>重复上报核对</h2>
              {duplicates.length === 0 ? <p className="muted">暂无重复上报。</p> : (
                <ul className="duplicates">
                  {duplicates.map((row) => (
                    <li key={row.id} className={row.status === 'conflict' || row.status === 'source_check' ? 'conflict' : 'identical'}>
                      <strong>第{row.board_number}牌 第{row.table_number}桌 · {row.status === 'conflict' ? '成绩冲突' : row.status === 'source_check' ? '异源核对' : '相同重复'}</strong>
                      <p>{row.detail}</p>
                      <small>{new Date(row.created_at).toLocaleString()} · {row.source}</small>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="grid two">
            <div className="card">
              <h2>当前未发布排名</h2>
              <RankingTable rows={rankings} />
            </div>
            <div className="card">
              <h2>已发布快照 {publication ? `v${publication.version}` : ''}</h2>
              {!publication ? <p className="muted">尚未发布。发布后新增成绩不会改变此快照。</p> : (
                <>
                  <p className="muted">{new Date(publication.published_at).toLocaleString()}；{publication.note}</p>
                  <RankingTable rows={publication.rankings} />
                </>
              )}
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function RankingTable({ rows }: { rows: PairRanking[] }) {
  if (!rows.length) return <p className="muted">暂无可排名牌。</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>名次</th><th>对号</th><th>MP</th><th>可得MP</th><th>百分比</th><th>已打牌</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.pair_number}>
              <td>{row.rank}</td>
              <td>{row.pair_number}</td>
              <td>{formatMp(row.total_matchpoints)}</td>
              <td>{formatMp(row.available_matchpoints)}</td>
              <td>{row.percentage === null ? '—' : `${row.percentage.toFixed(2)}%`}</td>
              <td>{row.boards_played}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
