"""Matchpoint calculation for pair duplicate bridge.

Only reported results belong to a comparison set.  A missing traveller row is
*not* represented as zero: it is reported separately, and competitors receive
matchpoints only against the results that were actually available when the set
was calculated/published.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, Sequence

ComparisonOutcome = Literal["better", "tied", "worse", "not_compared"]


@dataclass(frozen=True)
class Comparison:
    opponent_result_id: int
    opponent_table_number: int
    opponent_ns_score: int
    outcome_for_ns: ComparisonOutcome
    ns_matchpoints: float
    ew_matchpoints: float


@dataclass(frozen=True)
class MatchpointLine:
    result_id: int
    table_number: int
    ns_pair_number: int
    ew_pair_number: int
    ns_score: int
    ew_score: int
    ns_matchpoints: float
    ew_matchpoints: float
    max_matchpoints: float
    comparisons: tuple[Comparison, ...]


@dataclass(frozen=True)
class BoardMatchpoints:
    board_number: int
    expected_table_count: int
    compared_table_count: int
    missing_table_numbers: tuple[int, ...]
    max_matchpoints: float
    lines: tuple[MatchpointLine, ...]
    note: str


def _mp_value(for_ns_score: int, against_ns_score: int) -> tuple[float, float, ComparisonOutcome]:
    if for_ns_score > against_ns_score:
        return 1.0, 0.0, "better"
    if for_ns_score < against_ns_score:
        return 0.0, 1.0, "worse"
    return 0.5, 0.5, "tied"


def calculate_board_matchpoints(
    board_number: int,
    results: Sequence[dict[str, Any]],
    expected_table_numbers: Sequence[int],
) -> BoardMatchpoints:
    """Calculate NS/EW matchpoints from signed NS scores.

    Each result dict needs ``id``, ``table_number``, ``ns_pair_number``,
    ``ew_pair_number`` and ``ns_score``.  Duplicate table/board entries are the
    caller's responsibility; the API keeps only one accepted result per table.
    """
    result_ids = {int(row["id"]) for row in results}
    if len(result_ids) != len(results):
        raise ValueError("duplicate result ids in matchpoint comparison set")

    reported_tables = {int(row["table_number"]) for row in results}
    if len(reported_tables) != len(results):
        raise ValueError("duplicate table numbers in matchpoint comparison set")

    missing = tuple(table for table in expected_table_numbers if table not in reported_tables)
    lines: list[MatchpointLine] = []
    actual_count = len(results)
    max_points = float(actual_count - 1)

    for row in results:
        comparisons: list[Comparison] = []
        ns_mp = 0.0
        for other in results:
            if row["id"] == other["id"]:
                continue
            earned_ns, earned_ew, outcome = _mp_value(int(row["ns_score"]), int(other["ns_score"]))
            ns_mp += earned_ns
            comparisons.append(
                Comparison(
                    opponent_result_id=int(other["id"]),
                    opponent_table_number=int(other["table_number"]),
                    opponent_ns_score=int(other["ns_score"]),
                    outcome_for_ns=outcome,
                    ns_matchpoints=earned_ns,
                    ew_matchpoints=earned_ew,
                )
            )
        lines.append(
            MatchpointLine(
                result_id=int(row["id"]),
                table_number=int(row["table_number"]),
                ns_pair_number=int(row["ns_pair_number"]),
                ew_pair_number=int(row["ew_pair_number"]),
                ns_score=int(row["ns_score"]),
                ew_score=-int(row["ns_score"]),
                ns_matchpoints=ns_mp,
                ew_matchpoints=max_points - ns_mp,
                max_matchpoints=max_points,
                comparisons=tuple(comparisons),
            )
        )

    if actual_count == 0:
        note = "暂无任何成绩；本牌不产生MP。"
    elif actual_count == 1:
        note = "只有一桌有效成绩，没有可比较对象；未把缺桌记作零分。"
    elif missing:
        note = f"当前仅按 {actual_count} 桌有效成绩比较；缺桌 {', '.join(map(str, missing))} 未计零分。"
    else:
        note = f"按全部 {actual_count} 桌比较。"

    return BoardMatchpoints(
        board_number=board_number,
        expected_table_count=len(expected_table_numbers),
        compared_table_count=actual_count,
        missing_table_numbers=missing,
        max_matchpoints=max_points,
        lines=tuple(lines),
        note=note,
    )


@dataclass(frozen=True)
class PairRanking:
    pair_number: int
    total_matchpoints: float
    available_matchpoints: float
    percentage: float | None
    boards_played: int
    boards_missing: tuple[int, ...]
    rank: int | None = None


def calculate_ranking(
    boards: Sequence[BoardMatchpoints],
    expected_pair_boards: dict[int, set[int]],
) -> list[PairRanking]:
    """Aggregate per-pair percentages without scoring a missing board as zero."""
    totals: dict[int, float] = defaultdict(float)
    available: dict[int, float] = defaultdict(float)
    played: dict[int, set[int]] = defaultdict(set)

    for board in boards:
        # A board with one reported result has max=0 and cannot affect ranking.
        if board.max_matchpoints <= 0:
            continue
        for line in board.lines:
            totals[line.ns_pair_number] += line.ns_matchpoints
            available[line.ns_pair_number] += board.max_matchpoints
            played[line.ns_pair_number].add(board.board_number)

            totals[line.ew_pair_number] += line.ew_matchpoints
            available[line.ew_pair_number] += board.max_matchpoints
            played[line.ew_pair_number].add(board.board_number)

    pair_numbers = set(totals) | set(expected_pair_boards)
    rankings: list[PairRanking] = []
    for pair in sorted(pair_numbers):
        max_mp = available.get(pair, 0.0)
        played_boards = played.get(pair, set())
        missing = tuple(sorted(expected_pair_boards.get(pair, set()) - played_boards))
        rankings.append(
            PairRanking(
                pair_number=pair,
                total_matchpoints=totals.get(pair, 0.0),
                available_matchpoints=max_mp,
                percentage=(100.0 * totals[pair] / max_mp) if max_mp > 0 else None,
                boards_played=len(played_boards),
                boards_missing=missing,
            )
        )

    comparable = [row for row in rankings if row.percentage is not None]
    comparable.sort(key=lambda row: (-row.percentage, row.pair_number))
    ranked_by_pair: dict[int, PairRanking] = {}
    previous_percentage: float | None = None
    previous_rank = 0
    for index, row in enumerate(comparable, start=1):
        rank = index
        if previous_percentage is not None and abs(row.percentage - previous_percentage) < 1e-9:
            rank = previous_rank
        ranked_by_pair[row.pair_number] = PairRanking(**{**row.__dict__, "rank": rank})
        previous_percentage = row.percentage
        previous_rank = rank

    for index, row in enumerate(rankings):
        if row.pair_number in ranked_by_pair:
            rankings[index] = ranked_by_pair[row.pair_number]
    rankings.sort(key=lambda row: (row.rank is None, row.rank or 999999, row.pair_number))
    return rankings
