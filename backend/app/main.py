from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, FastAPI, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, get_session
from .models import DuplicateReport, Event, Publication, ResultEntry, RotationAssignment
from .schemas import (
    BoardMatchpointsOut,
    BoardOut,
    DuplicateReportOut,
    EventCreate,
    EventOut,
    PublicationOut,
    ResultCreate,
    ResultOut,
    RotationOut,
)
from .scoring import ContractInput, score_contract, vulnerability_for_board
from .services import (
    board_payload,
    create_event,
    current_board_matchpoints,
    current_event_matchpoints,
    get_event_or_404,
    publish_ranking,
    submit_result,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="双人复式桥牌 MP 计分",
    version="1.0.0",
    description="牌面分、局况、同桌核对、MP逐牌追查和发布快照。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_new_event(data: EventCreate, session: Session = Depends(get_session)) -> Event:
    return create_event(
        session,
        name=data.name,
        table_count=data.table_count,
        board_numbers=data.board_numbers,
        rotation=data.rotation,
    )


@app.get("/api/events", response_model=list[EventOut])
def list_events(session: Session = Depends(get_session)) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


@app.get("/api/events/{event_id}", response_model=EventOut)
def read_event(event_id: int, session: Session = Depends(get_session)) -> Event:
    return get_event_or_404(session, event_id)


@app.get("/api/events/{event_id}/boards", response_model=list[BoardOut])
def list_boards(event_id: int, session: Session = Depends(get_session)) -> list[dict]:
    event = get_event_or_404(session, event_id)
    board_numbers = [row.board_number for row in event.boards]
    return [board_payload(session, event, number) for number in sorted(board_numbers)]


@app.get("/api/events/{event_id}/boards/{board_number}", response_model=BoardOut)
def read_board(event_id: int, board_number: int, session: Session = Depends(get_session)) -> dict:
    event = get_event_or_404(session, event_id)
    return board_payload(session, event, board_number)


@app.get("/api/events/{event_id}/rotation", response_model=list[RotationOut])
def read_rotation(event_id: int, session: Session = Depends(get_session)) -> list[RotationAssignment]:
    get_event_or_404(session, event_id)
    return list(
        session.scalars(
            select(RotationAssignment)
            .where(RotationAssignment.event_id == event_id)
            .order_by(RotationAssignment.board_number, RotationAssignment.table_number)
        )
    )


@app.post("/api/events/{event_id}/results", response_model=ResultOut)
def create_result(
    event_id: int,
    data: ResultCreate,
    response: Response,
    session: Session = Depends(get_session),
) -> ResultEntry:
    event = get_event_or_404(session, event_id)
    entry, _report, created = submit_result(session, event, data)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return entry


@app.get("/api/events/{event_id}/results", response_model=list[ResultOut])
def list_results(event_id: int, session: Session = Depends(get_session)) -> list[ResultEntry]:
    get_event_or_404(session, event_id)
    return list(
        session.scalars(
            select(ResultEntry)
            .where(ResultEntry.event_id == event_id)
            .order_by(ResultEntry.board_number, ResultEntry.table_number)
        )
    )


@app.get("/api/events/{event_id}/duplicates", response_model=list[DuplicateReportOut])
def list_duplicates(event_id: int, session: Session = Depends(get_session)) -> list[DuplicateReport]:
    get_event_or_404(session, event_id)
    return list(
        session.scalars(
            select(DuplicateReport)
            .where(DuplicateReport.event_id == event_id)
            .order_by(DuplicateReport.created_at.desc())
        )
    )


@app.post("/api/score/preview")
def preview_score(data: ResultCreate) -> dict:
    contract = ContractInput(
        level=0 if data.passed_out else data.level or 0,
        denomination=data.denomination or "NT",
        declarer=data.declarer or "N",
        doubled=data.doubled,
        result=data.overtricks - data.undertricks,
        passed_out=data.passed_out,
    )
    breakdown = score_contract(contract, vulnerability_for_board(data.board_number))
    return {
        "vulnerability": vulnerability_for_board(data.board_number),
        "breakdown": asdict(breakdown),
    }


@app.get("/api/events/{event_id}/matchpoints", response_model=list[BoardMatchpointsOut])
def event_matchpoints(event_id: int, session: Session = Depends(get_session)) -> list[dict]:
    event = get_event_or_404(session, event_id)
    return [asdict(board) for board in current_event_matchpoints(session, event)]


@app.get("/api/events/{event_id}/boards/{board_number}/matchpoints", response_model=BoardMatchpointsOut)
def board_matchpoints(event_id: int, board_number: int, session: Session = Depends(get_session)) -> dict:
    event = get_event_or_404(session, event_id)
    return asdict(current_board_matchpoints(session, event, board_number))


@app.post("/api/events/{event_id}/publications", response_model=PublicationOut, status_code=status.HTTP_201_CREATED)
def publish(
    event_id: int,
    note: str = Query(default=""),
    session: Session = Depends(get_session),
) -> Publication:
    event = get_event_or_404(session, event_id)
    return publish_ranking(session, event, note)


@app.get("/api/events/{event_id}/publications", response_model=list[PublicationOut])
def list_publications(event_id: int, session: Session = Depends(get_session)) -> list[Publication]:
    get_event_or_404(session, event_id)
    return list(
        session.scalars(
            select(Publication)
            .where(Publication.event_id == event_id)
            .order_by(Publication.version.desc())
        )
    )


@app.get("/api/events/{event_id}/publications/latest", response_model=PublicationOut)
def latest_publication(event_id: int, session: Session = Depends(get_session)) -> Publication:
    get_event_or_404(session, event_id)
    publication = session.scalar(
        select(Publication)
        .where(Publication.event_id == event_id)
        .order_by(Publication.version.desc())
        .limit(1)
    )
    if publication is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no published ranking")
    return publication
