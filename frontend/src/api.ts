export type Vulnerability = 'none' | 'NS' | 'EW' | 'both';
export type Doubled = 'none' | 'doubled' | 'redoubled';

export interface Event {
  id: number;
  name: string;
  table_count: number;
  created_at: string;
}

export interface BoardInfo {
  board_number: number;
  vulnerability: Vulnerability;
  dealer: 'N' | 'E' | 'S' | 'W';
  expected_table_numbers: number[];
  missing_table_numbers: number[];
}

export interface ScoreBreakdown {
  contract_side: 'NS' | 'EW';
  vulnerable: boolean;
  ns_score: number;
  ew_score: number;
  declarer_score: number;
  contract_points: number;
  game_or_part_bonus: number;
  slam_bonus: number;
  insult_bonus: number;
  overtrick_points: number;
  penalty_points: number;
}

export interface ResultEntry {
  id: number;
  event_id: number;
  board_number: number;
  table_number: number;
  ns_pair_number: number;
  ew_pair_number: number;
  level: number | null;
  denomination: 'C' | 'D' | 'H' | 'S' | 'NT' | null;
  declarer: 'N' | 'E' | 'S' | 'W' | null;
  doubled: Doubled;
  overtricks: number;
  undertricks: number;
  passed_out: boolean;
  ns_score: number;
  ew_score: number;
  score_breakdown: ScoreBreakdown;
  source: string;
  created_at: string;
}

export interface Comparison {
  opponent_result_id: number;
  opponent_table_number: number;
  opponent_ns_score: number;
  outcome_for_ns: 'better' | 'tied' | 'worse' | 'not_compared';
  ns_matchpoints: number;
  ew_matchpoints: number;
}

export interface MatchpointLine {
  result_id: number;
  table_number: number;
  ns_pair_number: number;
  ew_pair_number: number;
  ns_score: number;
  ew_score: number;
  ns_matchpoints: number;
  ew_matchpoints: number;
  max_matchpoints: number;
  comparisons: Comparison[];
}

export interface BoardMatchpoints {
  board_number: number;
  expected_table_count: number;
  compared_table_count: number;
  missing_table_numbers: number[];
  max_matchpoints: number;
  lines: MatchpointLine[];
  note: string;
}

export interface PairRanking {
  pair_number: number;
  total_matchpoints: number;
  available_matchpoints: number;
  percentage: number | null;
  boards_played: number;
  boards_missing: number[];
  rank: number | null;
}

export interface DuplicateReport {
  id: number;
  board_number: number;
  table_number: number;
  source: string;
  status: 'identical' | 'source_check' | 'conflict';
  existing_result_id: number | null;
  detail: string;
  created_at: string;
}

export interface Publication {
  id: number;
  version: number;
  board_matchpoints: BoardMatchpoints[];
  rankings: PairRanking[];
  result_snapshot: ResultEntry[];
  note: string;
  published_at: string;
}

export interface ResultForm {
  board_number: number;
  table_number: number;
  declarer: 'N' | 'E' | 'S' | 'W' | '';
  level: number | '';
  denomination: 'C' | 'D' | 'H' | 'S' | 'NT' | '';
  doubled: Doubled;
  overtricks: number;
  undertricks: number;
  passed_out: boolean;
  source: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === 'string' ? body.detail : body.detail?.message ?? JSON.stringify(body.detail);
    } catch {
      // keep status text
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listEvents: () => request<Event[]>('/api/events'),
  createEvent: (payload: { name: string; table_count: number; board_numbers: number[] }) =>
    request<Event>('/api/events', { method: 'POST', body: JSON.stringify(payload) }),
  boards: (eventId: number) => request<BoardInfo[]>(`/api/events/${eventId}/boards`),
  results: (eventId: number) => request<ResultEntry[]>(`/api/events/${eventId}/results`),
  matchpoints: (eventId: number) => request<BoardMatchpoints[]>(`/api/events/${eventId}/matchpoints`),
  boardMatchpoints: (eventId: number, board: number) =>
    request<BoardMatchpoints>(`/api/events/${eventId}/boards/${board}/matchpoints`),
  duplicates: (eventId: number) => request<DuplicateReport[]>(`/api/events/${eventId}/duplicates`),
  publish: (eventId: number, note: string) =>
    request<Publication>(`/api/events/${eventId}/publications?note=${encodeURIComponent(note)}`, { method: 'POST' }),
  latestPublication: (eventId: number) =>
    request<Publication>(`/api/events/${eventId}/publications/latest`),
  submitResult: (eventId: number, form: ResultForm) =>
    request<ResultEntry>(`/api/events/${eventId}/results`, {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        declarer: form.passed_out ? null : form.declarer,
        level: form.passed_out ? null : form.level,
        denomination: form.passed_out ? null : form.denomination,
      }),
    }),
};
