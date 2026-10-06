from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BoardAssignment, BoardResult, Event, MovementSlot, Pair
from .scoring import aggregate_rankings, matchpoints_for_board, vulnerability_for_board, vulnerability_label


def _expected_boards(event: Event, db: Session) -> set[tuple[int, int, int]]:
    """Return (board, table, round) entries from the frozen movement schedule."""
    assignments = db.scalars(
        select(BoardAssignment).where(BoardAssignment.event_id == event.id)
    ).all()
    if assignments:
        return {(a.board_no, a.table_no, a.round_no) for a in assignments}

    # A simple Mitchell-style event may define tables but not explicitly list
    # every board. In that setup boards are expected at every table of a round.
    slots = db.scalars(select(MovementSlot).where(MovementSlot.event_id == event.id)).all()
    if not slots:
        return set()
    max_board = max([0] + [r.board_no for r in event.results])
    if max_board == 0:
        return set()
    return {(board_no, slot.table_no, slot.round_no) for slot in slots for board_no in range(1, max_board + 1)}


def active_results(db: Session, event_id: int) -> list[BoardResult]:
    return list(
        db.scalars(
            select(BoardResult)
            .where(BoardResult.event_id == event_id, BoardResult.status == "ACTIVE")
            .order_by(BoardResult.board_no, BoardResult.table_no)
        ).all()
    )


def score_all_active(event: Event, db: Session) -> tuple[list[Any], dict[str, Any]]:
    """Score active results and report the fixed, actually played comparison set."""
    results = active_results(db, event.id)
    grouped: dict[int, list[BoardResult]] = defaultdict(list)
    for result in results:
        grouped[result.board_no].append(result)

    all_rows: list[Any] = []
    comparison: dict[str, Any] = {}
    for board_no in sorted(grouped):
        rows = matchpoints_for_board(board_no, grouped[board_no])
        all_rows.extend(rows)
        comparison[str(board_no)] = {
            "board_no": board_no,
            "vulnerability": vulnerability_for_board(board_no),
            "vulnerability_label": vulnerability_label(vulnerability_for_board(board_no)),
            "played_table_count": len(rows),
            "played_tables": sorted(row.table_no for row in rows),
            "available_matchpoints_per_side": 2 * (len(rows) - 1),
            "excluded_missing_tables": _missing_tables(event, db, board_no, grouped[board_no]),
        }
    return all_rows, comparison


def _missing_tables(event: Event, db: Session, board_no: int, board_results: list[BoardResult]) -> list[dict[str, Any]]:
    played_table_rounds = {(r.table_no, r.round_no) for r in board_results}
    expected = [key for key in _expected_boards(event, db) if key[0] == board_no]
    if not expected:
        return []
    missing = []
    for _, table_no, round_no in sorted(expected):
        if (table_no, round_no) not in played_table_rounds:
            slot = db.scalar(
                select(MovementSlot).where(
                    MovementSlot.event_id == event.id,
                    MovementSlot.round_no == round_no,
                    MovementSlot.table_no == table_no,
                )
            )
            missing.append(
                {
                    "table_no": table_no,
                    "round_no": round_no,
                    "scheduled_ns_pair_code": slot.ns_pair_code if slot else None,
                    "scheduled_ew_pair_code": slot.ew_pair_code if slot else None,
                    "handling": "excluded_from_comparison; not scored as zero",
                }
            )
    return missing


def build_audit(event: Event, db: Session, published_publication_id: int | None = None) -> dict[str, Any]:
    results = active_results(db, event.id)
    rows, comparison = score_all_active(event, db)
    pairs = db.scalars(select(Pair).where(Pair.event_id == event.id)).all()
    pair_names = {pair.code: pair.name for pair in pairs}
    rankings = aggregate_rankings(rows, pair_names)

    expected = sorted(_expected_boards(event, db))
    active_keys = {(r.board_no, r.table_no, r.round_no) for r in results}
    missing = []
    for board_no, table_no, round_no in expected:
        if (board_no, table_no, round_no) not in active_keys:
            slot = db.scalar(
                select(MovementSlot).where(
                    MovementSlot.event_id == event.id,
                    MovementSlot.round_no == round_no,
                    MovementSlot.table_no == table_no,
                )
            )
            missing.append(
                {
                    "board_no": board_no,
                    "table_no": table_no,
                    "round_no": round_no,
                    "ns_pair_code": slot.ns_pair_code if slot else None,
                    "ew_pair_code": slot.ew_pair_code if slot else None,
                    "handling": "excluded_from_comparison; not scored as zero",
                }
            )

    return {
        "event": {"id": event.id, "name": event.name},
        "published_publication_id": published_publication_id,
        "boards": comparison,
        "results": [_row_payload(row) for row in rows],
        "missing_results": missing,
        "rankings": rankings,
        "note": "MP is calculated only over active results in each per-board comparison set. Missing boards are audit entries, never zero scores.",
    }


def _row_payload(row: Any) -> dict[str, Any]:
    top = 2 * (row.comparison_size - 1)
    return {
        "board_no": row.board_no,
        "table_no": row.table_no,
        "ns_pair_code": row.ns_pair_code,
        "ew_pair_code": row.ew_pair_code,
        "contract_label": row.contract_label,
        "score_ns": row.score_ns,
        "score_ew": row.score_ew,
        "ns_matchpoints": row.ns_matchpoints,
        "ew_matchpoints": row.ew_matchpoints,
        "comparison_size": row.comparison_size,
        "available_matchpoints_per_side": top,
        "ns_percentage": round(100.0 * row.ns_matchpoints / top, 2) if top else None,
        "ew_percentage": round(100.0 * row.ew_matchpoints / top, 2) if top else None,
        "source_result_id": row.source_result_id,
    }
