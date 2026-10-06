from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PenaltyCode = Literal["NONE", "DOUBLED", "REDOUBLED"]
Declarer = Literal["N", "E", "S", "W"]
Denomination = Literal["C", "D", "H", "S", "NT"]


class PairCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)


class PairOut(PairCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MovementSlotIn(BaseModel):
    round_no: int = Field(gt=0)
    table_no: int = Field(gt=0)
    ns_pair_code: str = Field(min_length=1, max_length=20)
    ew_pair_code: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def distinct_pairs(self):
        if self.ns_pair_code == self.ew_pair_code:
            raise ValueError("a pair cannot play both directions at one table")
        return self


class BoardAssignmentIn(BaseModel):
    round_no: int = Field(gt=0)
    table_no: int = Field(gt=0)
    board_no: int = Field(gt=0)


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pairs: list[PairCreate] = Field(default_factory=list)
    movement: list[MovementSlotIn] = Field(default_factory=list)
    board_assignments: list[BoardAssignmentIn] = Field(default_factory=list)


class EventOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ResultIn(BaseModel):
    board_no: int = Field(gt=0)
    table_no: int = Field(gt=0)
    round_no: int = Field(gt=0)
    ns_pair_code: str = Field(min_length=1, max_length=20)
    ew_pair_code: str = Field(min_length=1, max_length=20)
    is_passout: bool = False
    declarer: Declarer | None = None
    level: int | None = Field(default=None, ge=1, le=7)
    denomination: Denomination | None = None
    penalty: PenaltyCode = "NONE"
    overtricks: int = Field(default=0, ge=0)
    undertricks: int = Field(default=0, ge=0)
    source_ref: str = Field(min_length=3, max_length=120)
    entered_by: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self):
        if self.ns_pair_code == self.ew_pair_code:
            raise ValueError("a pair cannot play both directions at one table")
        if self.overtricks and self.undertricks:
            raise ValueError("overtricks and undertricks cannot both be non-zero")
        if self.is_passout:
            if self.declarer or self.level or self.denomination or self.penalty != "NONE" or self.overtricks or self.undertricks:
                raise ValueError("passout must have no contract, penalty or trick delta")
        elif not (self.declarer and self.level and self.denomination):
            raise ValueError("declarer, level and denomination are required unless this is a passout")
        return self


class ResultOut(BaseModel):
    id: int
    board_no: int
    table_no: int
    round_no: int | None
    ns_pair_code: str
    ew_pair_code: str
    is_passout: bool
    declarer: str | None
    level: int | None
    denomination: str | None
    penalty: str
    overtricks: int
    undertricks: int
    vulnerability_code: str
    contract_label: str | None
    score_ns: int
    score_ew: int
    source_ref: str
    entered_by: str
    status: str
    superseded_by_id: int | None
    note: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PublicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PublicationOut(BaseModel):
    id: int
    event_id: int
    name: str
    created_at: datetime
    board_count: int
    result_count: int
    comparison: dict
    rankings: list[dict]
    model_config = ConfigDict(from_attributes=True)
