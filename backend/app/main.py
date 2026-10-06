from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit as audit_service
from .database import Base, engine, get_db, get_settings
from .models import (
    BoardAssignment,
    BoardResult,
    Event,
    MovementSlot,
    Pair,
    Publication,
    PublicationBoardScore,
)
from .schemas import (
    EventCreate,
    EventOut,
    PublicationCreate,
    PublicationOut,
    ResultIn,
    ResultOut,
)
from .scoring import matchpoints_for_board, score_contract, vulnerability_for_board, vulnerability_label


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Duplicate Bridge MP Scoring",
    version="1.0.0",
    description="Contract score, per-board matchpoints, movement-aware missing-result audit and frozen publications.",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_event_or_404(event_id: int, db: Session) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


def validate_scheduled_board(event_id: int, payload: ResultIn, db: Session) -> None:
    slot = db.scalar(
        select(MovementSlot).where(
            MovementSlot.event_id == event_id,
            MovementSlot.round_no == payload.round_no,
            MovementSlot.table_no == payload.table_no,
        )
    )
    if slot is None:
        raise HTTPException(status_code=400, detail="round/table is not in the movement schedule")
    if slot.ns_pair_code != payload.ns_pair_code or slot.ew_pair_code != payload.ew_pair_code:
        raise HTTPException(status_code=400, detail="pair codes do not match this scheduled table")
    scheduled_board = db.scalar(
        select(BoardAssignment).where(
            BoardAssignment.event_id == event_id,
            BoardAssignment.round_no == payload.round_no,
            BoardAssignment.table_no == payload.table_no,
            BoardAssignment.board_no == payload.board_no,
        )
    )
    if scheduled_board is None:
        raise HTTPException(status_code=400, detail="this board is not assigned to the scheduled round/table")


def validate_pair_codes(event_id: int, codes: set[str], db: Session) -> None:
    if not codes:
        return
    found = set(db.scalars(select(Pair.code).where(Pair.event_id == event_id, Pair.code.in_(codes))).all())
    missing = sorted(codes - found)
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown pair codes: {', '.join(missing)}")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/meta/vulnerability/{board_no}")
def vulnerability_meta(board_no: int):
    if board_no < 1:
        raise HTTPException(status_code=400, detail="board_no must be positive")
    code = vulnerability_for_board(board_no)
    return {"board_no": board_no, "vulnerability": code, "vulnerability_label": vulnerability_label(code)}


@app.post("/score-preview")
def score_preview(payload: dict[str, Any]):
    try:
        scored = score_contract(**payload)
    except (TypeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return scored.as_dict()


@app.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    event = Event(name=payload.name)
    db.add(event)
    db.flush()
    for pair in payload.pairs:
        db.add(Pair(event_id=event.id, code=pair.code, name=pair.name))
    db.flush()

    pair_codes = {pair.code for pair in payload.pairs}
    movement_codes = {m.ns_pair_code for m in payload.movement} | {m.ew_pair_code for m in payload.movement}
    if pair_codes and not movement_codes <= pair_codes:
        raise HTTPException(status_code=400, detail="movement references unknown pair code")

    movement_keys = {(m.round_no, m.table_no) for m in payload.movement}
    unknown_assignments = [
        (a.round_no, a.table_no, a.board_no)
        for a in payload.board_assignments
        if (a.round_no, a.table_no) not in movement_keys
    ]
    if unknown_assignments:
        raise HTTPException(status_code=400, detail=f"board assignments reference missing table slots: {unknown_assignments}")

    for slot in payload.movement:
        db.add(
            MovementSlot(
                event_id=event.id,
                round_no=slot.round_no,
                table_no=slot.table_no,
                ns_pair_code=slot.ns_pair_code,
                ew_pair_code=slot.ew_pair_code,
            )
        )
    for assignment in payload.board_assignments:
        db.add(
            BoardAssignment(
                event_id=event.id,
                round_no=assignment.round_no,
                table_no=assignment.table_no,
                board_no=assignment.board_no,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate movement or board assignment") from exc
    db.refresh(event)
    return event


@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return list(db.scalars(select(Event).order_by(Event.id)).all())


@app.get("/events/{event_id}")
def event_detail(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(event_id, db)
    pairs = db.scalars(select(Pair).where(Pair.event_id == event_id).order_by(Pair.code)).all()
    slots = db.scalars(
        select(MovementSlot)
        .where(MovementSlot.event_id == event_id)
        .order_by(MovementSlot.round_no, MovementSlot.table_no)
    ).all()
    assignments = db.scalars(
        select(BoardAssignment)
        .where(BoardAssignment.event_id == event_id)
        .order_by(BoardAssignment.board_no, BoardAssignment.round_no, BoardAssignment.table_no)
    ).all()
    return {
        "id": event.id,
        "name": event.name,
        "created_at": event.created_at,
        "pairs": [{"code": p.code, "name": p.name} for p in pairs],
        "movement": [
            {
                "round_no": s.round_no,
                "table_no": s.table_no,
                "ns_pair_code": s.ns_pair_code,
                "ew_pair_code": s.ew_pair_code,
            }
            for s in slots
        ],
        "board_assignments": [
            {"round_no": a.round_no, "table_no": a.table_no, "board_no": a.board_no}
            for a in assignments
        ],
    }


def _persist_result(event_id: int, payload: ResultIn, db: Session) -> BoardResult:
    validate_pair_codes(event_id, {payload.ns_pair_code, payload.ew_pair_code}, db)
    validate_scheduled_board(event_id, payload, db)
    vulnerability = vulnerability_for_board(payload.board_no)
    try:
        scored = score_contract(
            board_no=payload.board_no,
            vulnerability=vulnerability,
            is_passout=payload.is_passout,
            declarer=payload.declarer,
            level=payload.level,
            denomination=payload.denomination,
            penalty=payload.penalty,
            overtricks=payload.overtricks,
            undertricks=payload.undertricks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = BoardResult(
        event_id=event_id,
        board_no=payload.board_no,
        table_no=payload.table_no,
        round_no=payload.round_no,
        ns_pair_code=payload.ns_pair_code,
        ew_pair_code=payload.ew_pair_code,
        is_passout=scored.is_passout,
        declarer=scored.declarer,
        level=scored.level,
        denomination=scored.denomination,
        penalty=scored.penalty,
        overtricks=scored.overtricks,
        undertricks=scored.undertricks,
        vulnerability_code=scored.vulnerability,
        contract_label=scored.contract_label,
        score_ns=scored.score_ns,
        score_ew=scored.score_ew,
        source_ref=payload.source_ref,
        entered_by=payload.entered_by,
        raw_payload=payload.model_dump(mode="json"),
        note=payload.note,
    )
    db.add(result)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="the same source_ref has already been used for this board and table") from exc
    return result


@app.post("/events/{event_id}/results", response_model=ResultOut, status_code=status.HTTP_201_CREATED)
def submit_result(event_id: int, payload: ResultIn, response: Response, db: Session = Depends(get_db)):
    get_event_or_404(event_id, db)
    active = db.scalar(
        select(BoardResult).where(
            BoardResult.event_id == event_id,
            BoardResult.board_no == payload.board_no,
            BoardResult.table_no == payload.table_no,
            BoardResult.status == "ACTIVE",
        )
    )
    canonical = payload.model_dump(mode="json")
    if active:
        if active.source_ref == payload.source_ref and active.raw_payload == canonical:
            response.status_code = status.HTTP_200_OK
            return active
        detail = {
            "message": "this board/table already has an active result; verify the source or enter a correction",
            "existing_result_id": active.id,
            "existing_source_ref": active.source_ref,
            "incoming_source_ref": payload.source_ref,
            "source_matches": active.source_ref == payload.source_ref,
        }
        raise HTTPException(status_code=409, detail=detail)
    result = _persist_result(event_id, payload, db)
    db.commit()
    db.refresh(result)
    return result


@app.post("/events/{event_id}/results/{result_id}/correction", response_model=ResultOut)
def correct_result(event_id: int, result_id: int, payload: ResultIn, db: Session = Depends(get_db)):
    get_event_or_404(event_id, db)
    old = db.get(BoardResult, result_id)
    if old is None or old.event_id != event_id:
        raise HTTPException(status_code=404, detail="result not found")
    if old.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="only an active result can be corrected")
    old.status = "SUPERSEDED"
    db.flush()
    replacement = _persist_result(event_id, payload, db)
    old.superseded_by_id = replacement.id
    db.commit()
    db.refresh(replacement)
    return replacement


@app.get("/events/{event_id}/results", response_model=list[ResultOut])
def list_results(event_id: int, db: Session = Depends(get_db), include_superseded: bool = False):
    get_event_or_404(event_id, db)
    stmt = select(BoardResult).where(BoardResult.event_id == event_id).order_by(BoardResult.board_no, BoardResult.table_no, BoardResult.id)
    if not include_superseded:
        stmt = stmt.where(BoardResult.status == "ACTIVE")
    return list(db.scalars(stmt).all())


@app.get("/events/{event_id}/audit")
def live_audit(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(event_id, db)
    return audit_service.build_audit(event, db)


@app.get("/events/{event_id}/boards/{board_no}/audit")
def board_audit(event_id: int, board_no: int, db: Session = Depends(get_db)):
    event = get_event_or_404(event_id, db)
    results = list(
        db.scalars(
            select(BoardResult)
            .where(
                BoardResult.event_id == event_id,
                BoardResult.board_no == board_no,
                BoardResult.status == "ACTIVE",
            )
            .order_by(BoardResult.table_no)
        ).all()
    )
    rows = matchpoints_for_board(board_no, results)
    n = len(rows)
    formula = {
        "rule": "NS_MP = 2 * lower_NS_scores + equal_NS_scores - 1; EW_MP = top - NS_MP",
        "top_per_side": 2 * (n - 1),
        "played_comparison_size": n,
        "missing_tables_are": "excluded, not zero",
    }
    return {
        "event_id": event_id,
        "board_no": board_no,
        "vulnerability": vulnerability_for_board(board_no),
        "vulnerability_label": vulnerability_label(vulnerability_for_board(board_no)),
        "formula": formula,
        "results": [
            {
                "result_id": r.id,
                "table_no": r.table_no,
                "round_no": r.round_no,
                "ns_pair_code": r.ns_pair_code,
                "ew_pair_code": r.ew_pair_code,
                "contract_label": r.contract_label,
                "declarer": r.declarer,
                "declarer_side": "NS" if r.declarer in ("N", "S") else ("EW" if r.declarer else None),
                "overtricks": r.overtricks,
                "undertricks": r.undertricks,
                "score_ns": r.score_ns,
                "score_ew": r.score_ew,
                "ns_matchpoints": row.ns_matchpoints,
                "ew_matchpoints": row.ew_matchpoints,
                "source_ref": r.source_ref,
                "entered_by": r.entered_by,
                "raw_payload": r.raw_payload,
            }
            for r, row in zip(results, rows)
        ],
    }


@app.post("/events/{event_id}/publications", response_model=PublicationOut, status_code=status.HTTP_201_CREATED)
def publish(event_id: int, payload: PublicationCreate, db: Session = Depends(get_db)):
    event = get_event_or_404(event_id, db)
    rows, comparison = audit_service.score_all_active(event, db)
    if not rows:
        raise HTTPException(status_code=400, detail="cannot publish an event without active results")
    pairs = db.scalars(select(Pair).where(Pair.event_id == event_id)).all()
    pair_names = {pair.code: pair.name for pair in pairs}
    rankings = audit_service.aggregate_rankings(rows, pair_names)

    publication = Publication(
        event_id=event_id,
        name=payload.name,
        board_count=len(comparison),
        result_count=len(rows),
        comparison=comparison,
        rankings=rankings,
    )
    db.add(publication)
    db.flush()
    for row in rows:
        db.add(
            PublicationBoardScore(
                publication_id=publication.id,
                board_no=row.board_no,
                table_no=row.table_no,
                ns_pair_code=row.ns_pair_code,
                ew_pair_code=row.ew_pair_code,
                contract_label=row.contract_label,
                score_ns=row.score_ns,
                score_ew=row.score_ew,
                ns_matchpoints=row.ns_matchpoints,
                ew_matchpoints=row.ew_matchpoints,
                comparison_set_size=row.comparison_size,
                source_result_id=row.source_result_id,
            )
        )
    db.commit()
    db.refresh(publication)
    return publication


@app.get("/events/{event_id}/publications", response_model=list[PublicationOut])
def list_publications(event_id: int, db: Session = Depends(get_db)):
    get_event_or_404(event_id, db)
    return list(db.scalars(select(Publication).where(Publication.event_id == event_id).order_by(Publication.id)).all())


@app.get("/publications/{publication_id}")
def publication_detail(publication_id: int, db: Session = Depends(get_db)):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="publication not found")
    scores = db.scalars(
        select(PublicationBoardScore)
        .where(PublicationBoardScore.publication_id == publication_id)
        .order_by(PublicationBoardScore.board_no, PublicationBoardScore.table_no)
    ).all()
    return {
        "id": publication.id,
        "event_id": publication.event_id,
        "name": publication.name,
        "created_at": publication.created_at,
        "board_count": publication.board_count,
        "result_count": publication.result_count,
        "comparison": publication.comparison,
        "rankings": publication.rankings,
        "board_scores": [
            {
                "board_no": s.board_no,
                "table_no": s.table_no,
                "ns_pair_code": s.ns_pair_code,
                "ew_pair_code": s.ew_pair_code,
                "contract_label": s.contract_label,
                "score_ns": s.score_ns,
                "score_ew": s.score_ew,
                "ns_matchpoints": s.ns_matchpoints,
                "ew_matchpoints": s.ew_matchpoints,
                "comparison_set_size": s.comparison_set_size,
                "source_result_id": s.source_result_id,
            }
            for s in scores
        ],
    }
