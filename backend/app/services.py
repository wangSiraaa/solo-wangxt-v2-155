from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from endplay.types import Board as EndplayBoard

from .matchpoints import BoardMatchpoints, calculate_board_matchpoints, calculate_ranking
from .models import Board, DuplicateReport, Event, Publication, ResultEntry, RotationAssignment
from .scoring import ContractInput, score_contract, vulnerability_for_board
from .schemas import ResultCreate


def default_dealer(board_number: int) -> str:
    dealer = EndplayBoard(board_num=board_number).dealer
    if dealer is None:
        raise ValueError("endplay did not provide a dealer")
    return dealer.abbr


def create_event(
    session: Session,
    *,
    name: str,
    table_count: int,
    board_numbers: list[int],
    rotation: dict[int, dict[int, dict[str, int]]] | None,
) -> Event:
    boards = sorted(set(board_numbers or list(range(1, table_count + 1))))
    event = Event(name=name, table_count=table_count)
    session.add(event)
    session.flush()

    for board_number in boards:
        session.add(
            Board(
                event_id=event.id,
                board_number=board_number,
                vulnerability=vulnerability_for_board(board_number),
            )
        )
        for table_number in range(1, table_count + 1):
            if rotation and board_number in rotation:
                pair = rotation[board_number][table_number]
                ns_pair, ew_pair = pair["ns"], pair["ew"]
            else:
                # Simple default Mitchell movement: NS pairs stay at tables and
                # EW pairs rotate. Real sessions can supply an explicit movement.
                ns_pair = table_number
                ew_pair = table_count + 1 + ((board_number + table_number - 2) % table_count)
            session.add(
                RotationAssignment(
                    event_id=event.id,
                    board_number=board_number,
                    table_number=table_number,
                    ns_pair_number=ns_pair,
                    ew_pair_number=ew_pair,
                )
            )
    session.commit()
    session.refresh(event)
    return event


def get_event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return event


def get_board_entity(session: Session, event_id: int, board_number: int) -> Board:
    board = session.scalar(
        select(Board).where(Board.event_id == event_id, Board.board_number == board_number)
    )
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not in event")
    return board


def rotation_map(session: Session, event_id: int) -> dict[tuple[int, int], RotationAssignment]:
    rows = session.scalars(select(RotationAssignment).where(RotationAssignment.event_id == event_id)).all()
    return {(row.board_number, row.table_number): row for row in rows}


def _canonical_result_payload(data: ResultCreate) -> dict[str, Any]:
    return data.model_dump(exclude={"source"})


def submit_result(session: Session, event: Event, data: ResultCreate) -> tuple[ResultEntry, DuplicateReport | None, bool]:
    get_board_entity(session, event.id, data.board_number)
    if not 1 <= data.table_number <= event.table_count:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="table not in event")

    assignment = session.scalar(
        select(RotationAssignment).where(
            RotationAssignment.event_id == event.id,
            RotationAssignment.board_number == data.board_number,
            RotationAssignment.table_number == data.table_number,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rotation assignment missing")

    contract = ContractInput(
        level=0 if data.passed_out else data.level or 0,
        denomination=data.denomination or "NT",
        declarer=data.declarer or "N",
        doubled=data.doubled,
        result=data.overtricks - data.undertricks,
        passed_out=data.passed_out,
    )
    vulnerability = vulnerability_for_board(data.board_number)
    breakdown = score_contract(contract, vulnerability)

    existing = session.scalar(
        select(ResultEntry).where(
            ResultEntry.event_id == event.id,
            ResultEntry.board_number == data.board_number,
            ResultEntry.table_number == data.table_number,
        )
    )
    if existing is not None:
        incoming_canonical = _canonical_result_payload(data)
        existing_canonical = {
            "board_number": existing.board_number,
            "table_number": existing.table_number,
            "declarer": existing.declarer,
            "level": existing.level,
            "denomination": existing.denomination,
            "doubled": existing.doubled,
            "overtricks": existing.overtricks,
            "undertricks": existing.undertricks,
            "passed_out": existing.passed_out,
        }
        same_source = data.source == existing.source
        same_score = (
            existing.passed_out == data.passed_out
            and existing.level == (None if data.passed_out else data.level)
            and existing.denomination == (None if data.passed_out else data.denomination)
            and existing.declarer == (None if data.passed_out else data.declarer)
            and existing.doubled == data.doubled
            and existing.overtricks == data.overtricks
            and existing.undertricks == data.undertricks
            and existing.ns_score == breakdown.ns_score
        )
        if same_score and same_source and incoming_canonical == existing_canonical:
            report = DuplicateReport(
                event_id=event.id,
                board_number=data.board_number,
                table_number=data.table_number,
                source=data.source,
                status="identical",
                existing_result_id=existing.id,
                raw_payload=data.model_dump(),
                detail=f"同一来源 {data.source!r} 重复上报；成绩一致，未覆盖原始录入。",
            )
            session.add(report)
            session.commit()
            session.refresh(report)
            return existing, report, False

        status_value = "source_check" if same_score and not same_source else "conflict"
        if same_score:
            detail = (
                f"成绩相同但来源不同：已接受来源 {existing.source!r}，重复来源 {data.source!r}；"
                "需裁判核对来源，未覆盖原始录入。"
            )
        else:
            detail = (
                f"同桌同牌成绩不一致：已接受来源 {existing.source!r} 得 NS {existing.ns_score}，"
                f"重复来源 {data.source!r} 得 NS {breakdown.ns_score}；需裁判裁决，未覆盖原始录入。"
            )
        report = DuplicateReport(
            event_id=event.id,
            board_number=data.board_number,
            table_number=data.table_number,
            source=data.source,
            status=status_value,
            existing_result_id=existing.id,
            raw_payload=data.model_dump(),
            detail=detail,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": detail,
                "duplicate_report_id": report.id,
                "existing_result_id": existing.id,
            },
        )

    entry = ResultEntry(
        event_id=event.id,
        board_number=data.board_number,
        table_number=data.table_number,
        ns_pair_number=assignment.ns_pair_number,
        ew_pair_number=assignment.ew_pair_number,
        level=None if data.passed_out else data.level,
        denomination=None if data.passed_out else data.denomination,
        declarer=None if data.passed_out else data.declarer,
        doubled=data.doubled,
        overtricks=data.overtricks,
        undertricks=data.undertricks,
        passed_out=data.passed_out,
        ns_score=breakdown.ns_score,
        ew_score=breakdown.ew_score,
        score_breakdown=asdict(breakdown),
        source=data.source,
        raw_payload=data.model_dump(),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry, None, True


def result_to_dict(row: ResultEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_id": row.event_id,
        "board_number": row.board_number,
        "table_number": row.table_number,
        "ns_pair_number": row.ns_pair_number,
        "ew_pair_number": row.ew_pair_number,
        "level": row.level,
        "denomination": row.denomination,
        "declarer": row.declarer,
        "doubled": row.doubled,
        "overtricks": row.overtricks,
        "undertricks": row.undertricks,
        "passed_out": row.passed_out,
        "ns_score": row.ns_score,
        "ew_score": row.ew_score,
        "score_breakdown": row.score_breakdown,
        "source": row.source,
        "created_at": row.created_at.isoformat(),
    }


def board_payload(session: Session, event: Event, board_number: int) -> dict[str, Any]:
    board = get_board_entity(session, event.id, board_number)
    expected = list(range(1, event.table_count + 1))
    results = session.scalars(
        select(ResultEntry)
        .where(ResultEntry.event_id == event.id, ResultEntry.board_number == board_number)
        .order_by(ResultEntry.table_number)
    ).all()
    reported = [row.table_number for row in results]
    return {
        "board_number": board.board_number,
        "vulnerability": board.vulnerability,
        "dealer": default_dealer(board.board_number),
        "expected_table_numbers": expected,
        "missing_table_numbers": [table for table in expected if table not in reported],
    }


def current_board_matchpoints(session: Session, event: Event, board_number: int) -> BoardMatchpoints:
    get_board_entity(session, event.id, board_number)
    results = session.scalars(
        select(ResultEntry)
        .where(ResultEntry.event_id == event.id, ResultEntry.board_number == board_number)
        .order_by(ResultEntry.table_number)
    ).all()
    return calculate_board_matchpoints(
        board_number,
        [result_to_dict(row) for row in results],
        list(range(1, event.table_count + 1)),
    )


def current_event_matchpoints(session: Session, event: Event) -> list[BoardMatchpoints]:
    board_numbers = list(session.scalars(select(Board.board_number).where(Board.event_id == event.id).order_by(Board.board_number)))
    return [current_board_matchpoints(session, event, number) for number in board_numbers]


def expected_pair_boards(session: Session, event: Event) -> dict[int, set[int]]:
    expected: dict[int, set[int]] = {}
    rows = session.scalars(select(RotationAssignment).where(RotationAssignment.event_id == event.id)).all()
    for row in rows:
        expected.setdefault(row.ns_pair_number, set()).add(row.board_number)
        expected.setdefault(row.ew_pair_number, set()).add(row.board_number)
    return expected


def publish_ranking(session: Session, event: Event, note: str = "") -> Publication:
    boards = current_event_matchpoints(session, event)
    rankings = calculate_ranking(boards, expected_pair_boards(session, event))
    results = session.scalars(
        select(ResultEntry).where(ResultEntry.event_id == event.id).order_by(ResultEntry.board_number, ResultEntry.table_number)
    ).all()

    next_version = (
        session.scalar(
            select(Publication.version)
            .where(Publication.event_id == event.id)
            .order_by(Publication.version.desc())
            .limit(1)
        )
        or 0
    ) + 1
    publication = Publication(
        event_id=event.id,
        version=next_version,
        board_matchpoints=[asdict(board) for board in boards],
        rankings=[asdict(row) for row in rankings],
        result_snapshot=[result_to_dict(row) for row in results],
        note=note,
    )
    session.add(publication)
    session.commit()
    session.refresh(publication)
    return publication
