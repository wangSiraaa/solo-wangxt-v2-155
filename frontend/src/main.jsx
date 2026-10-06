import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

const VULN_LABEL = {
  NONE: '双方无局',
  NS: '南北有局',
  EW: '东西有局',
  BOTH: '双方有局',
};

const SAMPLE_EVENT = {
  name: '裁判手算示例：有局加倍宕约、并列、缺一桌',
  pairs: [
    {code: 'NS1', name: '南北 1 号'},
    {code: 'NS2', name: '南北 2 号'},
    {code: 'NS3', name: '南北 3 号'},
    {code: 'NS4', name: '南北 4 号'},
    {code: 'EW1', name: '东西 1 号'},
    {code: 'EW2', name: '东西 2 号'},
    {code: 'EW3', name: '东西 3 号'},
    {code: 'EW4', name: '东西 4 号'},
  ],
  movement: [1, 2, 3, 4].map((tableNo) => ({
    round_no: 1,
    table_no: tableNo,
    ns_pair_code: `NS${tableNo}`,
    ew_pair_code: `EW${tableNo}`,
  })),
  board_assignments: [1, 2, 3, 4].map((tableNo) => ({
    round_no: 1,
    table_no: tableNo,
    board_no: 2,
  })),
};

const SAMPLE_RESULTS = [
  {
    board_no: 2,
    table_no: 1,
    round_no: 1,
    ns_pair_code: 'NS1',
    ew_pair_code: 'EW1',
    declarer: 'S',
    level: 4,
    denomination: 'S',
    penalty: 'DOUBLED',
    overtricks: 0,
    undertricks: 1,
    source_ref: 'sheet-2026-02-T1',
    entered_by: 'director',
    note: '有局加倍宕一：防守方 +200',
  },
  {
    board_no: 2,
    table_no: 2,
    round_no: 1,
    ns_pair_code: 'NS2',
    ew_pair_code: 'EW2',
    declarer: 'N',
    level: 3,
    denomination: 'C',
    penalty: 'NONE',
    overtricks: 0,
    undertricks: 0,
    source_ref: 'sheet-2026-02-T2',
    entered_by: 'director',
  },
  {
    board_no: 2,
    table_no: 3,
    round_no: 1,
    ns_pair_code: 'NS3',
    ew_pair_code: 'EW3',
    declarer: 'N',
    level: 2,
    denomination: 'D',
    penalty: 'NONE',
    overtricks: 1,
    undertricks: 0,
    source_ref: 'sheet-2026-02-T3',
    entered_by: 'director',
  },
  // Table 4 is deliberately absent. It must be listed as missing and excluded,
  // not converted to a zero result.
];

const EMPTY_FORM = {
  board_no: 2,
  table_no: 1,
  round_no: 1,
  ns_pair_code: '',
  ew_pair_code: '',
  is_passout: false,
  declarer: 'N',
  level: 4,
  denomination: 'S',
  penalty: 'NONE',
  overtricks: 0,
  undertricks: 0,
  source_ref: '',
  entered_by: '',
  note: '',
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {'Content-Type': 'application/json', ...(options.headers ?? {})},
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data));
  }
  return data;
}

function mpClass(value, top) {
  if (!top) return '';
  if (value === top) return 'mp-top';
  if (value === 0) return 'mp-zero';
  return '';
}

function BoardTable({rows, board}) {
  const top = board?.available_matchpoints_per_side ?? 0;
  return (
    <div className="card">
      <div className="card-heading">
        <div>
          <h3>第 {board?.board_no} 牌桌对照</h3>
          <p className="muted">局况：{board ? VULN_LABEL[board.vulnerability] : '—'} · 实际比较 {board?.played_table_count ?? 0} 桌</p>
        </div>
        <div className="pill">每方顶分 {top}</div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>桌号</th>
              <th>南北</th>
              <th>东西</th>
              <th>定约/结果</th>
              <th className="number">NS 分</th>
              <th className="number">EW 分</th>
              <th className="number">NS MP</th>
              <th className="number">EW MP</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.board_no}-${row.table_no}`}>
                <td>{row.table_no}</td>
                <td>{row.ns_pair_code}</td>
                <td>{row.ew_pair_code}</td>
                <td className="contract">{row.contract_label}</td>
                <td className={`number ${row.score_ns > 0 ? 'good' : row.score_ns < 0 ? 'bad' : ''}`}>{row.score_ns}</td>
                <td className={`number ${row.score_ew > 0 ? 'good' : row.score_ew < 0 ? 'bad' : ''}`}>{row.score_ew}</td>
                <td className={`number ${mpClass(row.ns_matchpoints, top)}`}>{row.ns_matchpoints}</td>
                <td className={`number ${mpClass(row.ew_matchpoints, top)}`}>{row.ew_matchpoints}</td>
                <td className="source">#{row.source_result_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ResultForm({eventId, onSaved}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  const update = (key, value) => setForm((current) => ({...current, [key]: value}));

  async function submit(event) {
    event.preventDefault();
    setError('');
    setBusy(true);
    const payload = {...form};
    if (payload.is_passout) {
      payload.declarer = null;
      payload.level = null;
      payload.denomination = null;
      payload.penalty = 'NONE';
      payload.overtricks = 0;
      payload.undertricks = 0;
    }
    try {
      await api(`/events/${eventId}/results`, {method: 'POST', body: JSON.stringify(payload)});
      setForm((current) => ({...current, source_ref: '', note: ''}));
      onSaved();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  async function previewScore() {
    setError('');
    try {
      const data = await api('/score-preview', {
        method: 'POST',
        body: JSON.stringify({
          board_no: Number(form.board_no),
          is_passout: form.is_passout,
          declarer: form.is_passout ? null : form.declarer,
          level: form.is_passout ? null : Number(form.level),
          denomination: form.is_passout ? null : form.denomination,
          penalty: form.penalty,
          overtricks: Number(form.overtricks),
          undertricks: Number(form.undertricks),
        }),
      });
      setPreview(data);
    } catch (exc) {
      setPreview(null);
      setError(exc.message);
    }
  }

  return (
    <form className="card form-grid" onSubmit={submit}>
      <h3>录入原始结果</h3>
      <label>牌号<input type="number" min="1" value={form.board_no} onChange={(e) => update('board_no', e.target.value)} /></label>
      <label>桌号<input type="number" min="1" value={form.table_no} onChange={(e) => update('table_no', e.target.value)} /></label>
      <label>轮次<input type="number" min="1" value={form.round_no ?? ''} onChange={(e) => update('round_no', e.target.value)} /></label>
      <label>南北对号<input value={form.ns_pair_code} onChange={(e) => update('ns_pair_code', e.target.value)} placeholder="NS1" /></label>
      <label>东西对号<input value={form.ew_pair_code} onChange={(e) => update('ew_pair_code', e.target.value)} placeholder="EW1" /></label>
      <label>来源编号<input value={form.source_ref} onChange={(e) => update('source_ref', e.target.value)} placeholder="paper-sheet-..." /></label>
      <label>录入员<input value={form.entered_by} onChange={(e) => update('entered_by', e.target.value)} placeholder="director" /></label>
      <label className="checkbox"><input type="checkbox" checked={form.is_passout} onChange={(e) => update('is_passout', e.target.checked)} />全 Pass</label>
      {!form.is_passout && <>
        <label>定约人<select value={form.declarer} onChange={(e) => update('declarer', e.target.value)}>{['N','E','S','W'].map((p) => <option key={p}>{p}</option>)}</select></label>
        <label>阶数<select value={form.level} onChange={(e) => update('level', e.target.value)}>{[1,2,3,4,5,6,7].map((n) => <option key={n}>{n}</option>)}</select></label>
        <label>花色<select value={form.denomination} onChange={(e) => update('denomination', e.target.value)}>{['C','D','H','S','NT'].map((d) => <option key={d}>{d}</option>)}</select></label>
        <label>加倍<select value={form.penalty} onChange={(e) => update('penalty', e.target.value)}><option value="NONE">无</option><option value="DOUBLED">X</option><option value="REDOUBLED">XX</option></select></label>
        <label>超墩<input type="number" min="0" value={form.overtricks} onChange={(e) => update('overtricks', e.target.value)} /></label>
        <label>宕墩<input type="number" min="0" value={form.undertricks} onChange={(e) => update('undertricks', e.target.value)} /></label>
      </>}
      <label className="wide">备注<input value={form.note ?? ''} onChange={(e) => update('note', e.target.value)} /></label>
      <div className="actions wide">
        <button type="button" onClick={previewScore}>试算牌面分</button>
        <button type="submit" disabled={busy}>{busy ? '提交中…' : '保存原始录入'}</button>
      </div>
      {preview && <div className="notice wide">牌面分：NS {preview.score_ns} / EW {preview.score_ew}（{VULN_LABEL[preview.vulnerability]}，{preview.contract_label}）</div>}
      {error && <div className="error wide">{error}</div>}
    </form>
  );
}

function App() {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [audit, setAudit] = useState(null);
  const [publications, setPublications] = useState([]);
  const [selectedPublication, setSelectedPublication] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const refresh = useCallback(async (id = eventId) => {
    if (!id) return;
    const [eventData, auditData, publicationList] = await Promise.all([
      api(`/events/${id}`),
      api(`/events/${id}/audit`),
      api(`/events/${id}/publications`),
    ]);
    setDetail(eventData);
    setAudit(auditData);
    setPublications(publicationList);
    if (!publicationList.length) setSelectedPublication(null);
  }, [eventId]);

  useEffect(() => {api('/events').then((data) => {
      setEvents(data);
      if (data.length) setEventId(data[0].id);
    }).catch((exc) => setError(exc.message));
  }, []);

  useEffect(() => {if (eventId) refresh(eventId).catch((exc) => setError(exc.message));
  }, [eventId, refresh]);

  async function createSample() {
    setMessage(''); setError('');
    try {
      const event = await api('/events', {method: 'POST', body: JSON.stringify(SAMPLE_EVENT)});
      for (const result of SAMPLE_RESULTS) {
        await api(`/events/${event.id}/results`, {method: 'POST', body: JSON.stringify(result)});
      }
      const all = await api('/events');
      setEvents(all);
      setEventId(event.id);
      setMessage('示例已建立：第 4 桌尚未录入，应出现在缺桌审计中。');
    } catch (exc) {
      setError(exc.message);
    }
  }

  async function publishRankings() {
    setMessage(''); setError('');
    try {
      const name = `第 ${publications.length + 1} 次发布 ${new Date().toLocaleString('zh-CN')}`;
      const pub = await api(`/events/${eventId}/publications`, {method: 'POST', body: JSON.stringify({name})});
      const detailData = await api(`/publications/${pub.id}`);
      setSelectedPublication(detailData);
      setPublications(await api(`/events/${eventId}/publications`));
      setMessage('排名已发布；比较集合和每个来源结果已随发布冻结。');
    } catch (exc) {
      setError(exc.message);
    }
  }

  async function openPublication(id) {
    setSelectedPublication(await api(`/publications/${id}`));
  }

  const boardGroups = useMemo(() => {
    const rows = selectedPublication ? selectedPublication.board_scores : audit?.results ?? [];
    return rows.reduce((acc, row) => {
      (acc[row.board_no] ||= []).push(row);
      return acc;
    }, {});
  }, [audit, selectedPublication]);

  const boards = selectedPublication
    ? Object.values(selectedPublication.comparison)
    : Object.values(audit?.boards ?? {});
  const rankings = selectedPublication ? selectedPublication.rankings : audit?.rankings ?? [];

  return (
    <main>
      <header>
        <div>
          <h1>双人复式桥牌 MP 计分</h1>
          <p>牌号局况、牌面分、逐牌 MP、缺桌审计与发布冻结</p>
        </div>
        <div className="header-actions">
          <button onClick={createSample}>创建手算示例</button>
          <select value={eventId ?? ''} onChange={(e) => setEventId(Number(e.target.value))}>
            {events.map((event) => <option key={event.id} value={event.id}>{event.id}. {event.name}</option>)}
          </select>
        </div>
      </header>

      {message && <div className="success">{message}</div>}
      {error && <div className="error">{error}</div>}

      {eventId && <>
        <section className="grid two">
          <div className="card">
            <h2>{detail?.name}</h2>
            <p className="muted">轮转安排：{detail?.movement.length ?? 0} 个桌位，牌张分发：{detail?.board_assignments.length ?? 0} 条</p>
            <div className="pairs">
              {detail?.pairs.map((pair) => <span className="pair" key={pair.code}>{pair.code} · {pair.name}</span>)}
            </div>
          </div>
          <div className="card">
            <h2>发布</h2>
            <p className="muted">发布时固定每牌实际结果集合；后续录入或改正不会改变历史发布。</p>
            <button onClick={publishRankings}>发布当前排名</button>
            <div className="publication-list">
              {publications.map((pub) => <button key={pub.id} type="button" onClick={() => openPublication(pub.id)}>查看 #{pub.id} {pub.name}</button>)}
              {selectedPublication && <button type="button" onClick={() => setSelectedPublication(null)}>返回实时审计</button>}
            </div>
          </div>
        </section>

        {!selectedPublication && <ResultForm eventId={eventId} onSaved={() => refresh()} />}

        {audit?.missing_results?.length > 0 && !selectedPublication && (
          <div className="card warning">
            <h3>缺桌/缺牌（不计零分）</h3>
            {audit.missing_results.map((item) => (
              <div key={`${item.board_no}-${item.table_no}-${item.round_no}`}>
                第 {item.board_no} 牌 / 第 {item.table_no} 桌（第 {item.round_no} 轮，{item.ns_pair_code} VS {item.ew_pair_code}）：{item.handling}
              </div>
            ))}
          </div>
        )}

        {Object.entries(boardGroups).map(([boardNo, rows]) => (
          <BoardTable key={boardNo} rows={rows} board={boards.find((b) => String(b.board_no) === String(boardNo))} />
        ))}

        <div className="card">
          <h2>{selectedPublication ? '冻结排名' : '实时排名'}</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>名次</th><th>对号</th><th>名称</th><th className="number">已打牌</th><th className="number">MP</th><th className="number">可用 MP</th><th className="number">百分比</th></tr></thead>
              <tbody>{rankings.map((r) => <tr key={r.pair_code}><td>{r.rank}</td><td>{r.pair_code}</td><td>{r.pair_name}</td><td className="number">{r.boards}</td><td className="number">{r.matchpoints}</td><td className="number">{r.available_matchpoints}</td><td className="number">{r.percentage}%</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      </>}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
