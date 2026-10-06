from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Doubled = Literal["none", "doubled", "redoubled"]
Denomination = Literal["C", "D", "H", "S", "NT"]
Declarer = Literal["N", "E", "S", "W"]


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    table_count: int = Field(ge=1, le=40)
    board_numbers: list[int] = Field(default_factory=list)
    # Optional complete Howell/Mitchell movement: board -> table -> {"ns": n, "ew": n}.
    rotation: dict[int, dict[int, dict[str, int]]] | None = None

    @model_validator(mode="after")
    def validate_rotation(self) -> "EventCreate":
        if self.board_numbers and any(not 1 <= n <= 32 for n in self.board_numbers):
            raise ValueError("board numbers must be 1..32")
        if self.rotation:
            for board, tables in self.rotation.items():
                if board not in self.board_numbers:
                    raise ValueError(f"rotation board {board} is not configured")
                if set(tables) != set(range(1, self.table_count + 1)):
                    raise ValueError(f"board {board} must schedule tables 1..{self.table_count}")
        return self


class EventOut(BaseModel):
    id: int
    name: str
    table_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BoardOut(BaseModel):
    board_number: int
    vulnerability: Literal["none", "NS", "EW", "both"]
    dealer: Literal["N", "E", "S", "W"]
    expected_table_numbers: list[int]
    missing_table_numbers: list[int]


class RotationOut(BaseModel):
    board_number: int
    table_number: int
    ns_pair_number: int
    ew_pair_number: int


class ResultCreate(BaseModel):
    board_number: int = Field(ge=1, le=32)
    table_number: int = Field(ge=1)
    declarer: Declarer | None = None
    level: int | None = Field(default=None, ge=1, le=7)
    denomination: Denomination | None = None
    doubled: Doubled = "none"
    overtricks: int = Field(default=0, ge=0, le=13)
    undertricks: int = Field(default=0, ge=0, le=13)
    passed_out: bool = False
    source: str = Field(min_length=1, max_length=200, examples=["traveller-table-2", "director-console"])

    @model_validator(mode="after")
    def validate_shape(self) -> "ResultCreate":
        if self.passed_out:
            if (self.declarer, self.level, self.denomination) != (None, None, None):
                raise ValueError("passed-out results must not contain a contract")
            if self.overtricks or self.undertricks or self.doubled != "none":
                raise ValueError("passed-out results must not contain tricks or a double")
            return self
        if self.declarer is None or self.level is None or self.denomination is None:
            raise ValueError("played results require declarer, level and denomination")
        if self.overtricks and self.undertricks:
            raise ValueError("overtricks and undertricks cannot both be non-zero")
        tricks_taken = self.level + 6 + self.overtricks - self.undertricks
        if not 0 <= tricks_taken <= 13:
            raise ValueError("result implies an impossible number of tricks")
        return self


class ScoreBreakdownOut(BaseModel):
    contract_side: Literal["NS", "EW"]
    vulnerable: bool
    ns_score: int
    ew_score: int
    declarer_score: int
    contract_points: int
    game_or_part_bonus: int
    slam_bonus: int
    insult_bonus: int
    overtrick_points: int
    penalty_points: int


class ResultOut(BaseModel):
    id: int
    event_id: int
    board_number: int
    table_number: int
    ns_pair_number: int
    ew_pair_number: int
    level: int | None
    denomination: Denomination | None
    declarer: Declarer | None
    doubled: Doubled
    overtricks: int
    undertricks: int
    passed_out: bool
    ns_score: int
    ew_score: int
    score_breakdown: ScoreBreakdownOut
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DuplicateReportOut(BaseModel):
    id: int
    board_number: int
    table_number: int
    source: str
    status: Literal["identical", "source_check", "conflict"]
    existing_result_id: int | None
    detail: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonOut(BaseModel):
    opponent_result_id: int
    opponent_table_number: int
    opponent_ns_score: int
    outcome_for_ns: Literal["better", "tied", "worse", "not_compared"]
    ns_matchpoints: float
    ew_matchpoints: float


class MatchpointLineOut(BaseModel):
    result_id: int
    table_number: int
    ns_pair_number: int
    ew_pair_number: int
    ns_score: int
    ew_score: int
    ns_matchpoints: float
    ew_matchpoints: float
    max_matchpoints: float
    comparisons: list[ComparisonOut]


class BoardMatchpointsOut(BaseModel):
    board_number: int
    expected_table_count: int
    compared_table_count: int
    missing_table_numbers: list[int]
    max_matchpoints: float
    lines: list[MatchpointLineOut]
    note: str


class PairRankingOut(BaseModel):
    pair_number: int
    total_matchpoints: float
    available_matchpoints: float
    percentage: float | None
    boards_played: int
    boards_missing: list[int]
    rank: int | None


class PublicationOut(BaseModel):
    id: int
    version: int
    board_matchpoints: list[BoardMatchpointsOut]
    rankings: list[PairRankingOut]
    result_snapshot: list[ResultOut]
    note: str
    published_at: datetime

    model_config = {"from_attributes": True}
