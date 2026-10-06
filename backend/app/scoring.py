"""Bridge contract scoring and matchpoint calculations.

Contract score is produced by endplay's bridge contract model.  All stored
results are signed from North-South's point of view: a positive ``score_ns``
is good for N-S and ``score_ew`` is its exact opposite.
"""

from dataclasses import dataclass
from typing import Any, Literal

from endplay.types import Board, Contract, Denom, Penalty, Player, Vul

PenaltyCode = Literal["NONE", "DOUBLED", "REDOUBLED"]
Declarer = Literal["N", "E", "S", "W"]
Denomination = Literal["C", "D", "H", "S", "NT"]
VulnerabilityCode = Literal["NONE", "NS", "EW", "BOTH"]

_PENALTY = {
    "NONE": Penalty.passed,
    "DOUBLED": Penalty.doubled,
    "REDOUBLED": Penalty.redoubled,
}
_PLAYER = {
    "N": Player.north,
    "E": Player.east,
    "S": Player.south,
    "W": Player.west,
}
_DENOM = {
    "C": Denom.clubs,
    "D": Denom.diamonds,
    "H": Denom.hearts,
    "S": Denom.spades,
    "NT": Denom.nt,
}
_DECLARER_SIDE = {
    "N": "NS",
    "S": "NS",
    "E": "EW",
    "W": "EW",
}
_VUL = {
    "NONE": Vul.none,
    "NS": Vul.ns,
    "EW": Vul.ew,
    "BOTH": Vul.both,
}
_VUL_LABEL = {
    "NONE": "双方无局",
    "NS": "南北有局",
    "EW": "东西有局",
    "BOTH": "双方有局",
}
_DENOM_SYMBOL = {"C": "♣", "D": "♦", "H": "♥", "S": "♠", "NT": "NT"}
_PENALTY_SYMBOL = {"NONE": "", "DOUBLED": "X", "REDOUBLED": "XX"}


def vulnerability_for_board(board_no: int) -> VulnerabilityCode:
    """Return the standard board-number vulnerability using endplay's Board model."""
    if board_no < 1:
        raise ValueError("board_no must be positive")
    return Board(board_num=board_no).vul.name.upper()  # type: ignore[return-value]


def vulnerability_label(code: str) -> str:
    return _VUL_LABEL[code]


def declarer_side(declarer: str) -> str:
    return _DECLARER_SIDE[declarer]


@dataclass(frozen=True)
class ContractScore:
    is_passout: bool
    declarer: str | None
    declarer_side: str | None
    level: int | None
    denomination: str | None
    penalty: PenaltyCode
    overtricks: int
    undertricks: int
    vulnerability: VulnerabilityCode
    contract_label: str | None
    declarer_score: int
    score_ns: int
    score_ew: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_passout": self.is_passout,
            "declarer": self.declarer,
            "declarer_side": self.declarer_side,
            "level": self.level,
            "denomination": self.denomination,
            "penalty": self.penalty,
            "overtricks": self.overtricks,
            "undertricks": self.undertricks,
            "vulnerability": self.vulnerability,
            "vulnerability_label": vulnerability_label(self.vulnerability),
            "contract_label": self.contract_label,
            "declarer_score": self.declarer_score,
            "score_ns": self.score_ns,
            "score_ew": self.score_ew,
        }


def contract_label(
    *,
    is_passout: bool,
    level: int | None,
    denomination: str | None,
    declarer: str | None,
    penalty: PenaltyCode,
    overtricks: int,
    undertricks: int,
) -> str | None:
    if is_passout:
        return "Pass"
    if level is None or denomination is None or declarer is None:
        return None
    if undertricks:
        trick_part = f"-{undertricks}"
    elif overtricks:
        trick_part = f"+{overtricks}"
    else:
        trick_part = "="
    return (
        f"{level}{_DENOM_SYMBOL[denomination]}{_PENALTY_SYMBOL[penalty]} "
        f"{declarer} {trick_part}"
    )


def score_contract(
    *,
    board_no: int | None = None,
    vulnerability: str | None = None,
    is_passout: bool = False,
    declarer: str | None = None,
    level: int | None = None,
    denomination: str | None = None,
    penalty: PenaltyCode = "NONE",
    overtricks: int = 0,
    undertricks: int = 0,
) -> ContractScore:
    """Calculate a signed N-S/E-W bridge score.

    ``overtricks`` and ``undertricks`` are non-negative; exactly one may be
    non-zero.  Passout is explicit rather than represented by a zero-scoring
    fake contract.
    """
    if vulnerability is None:
        if board_no is None:
            raise ValueError("board_no or vulnerability is required")
        vulnerability = vulnerability_for_board(board_no)
    if vulnerability not in _VUL:
        raise ValueError("vulnerability must be NONE, NS, EW or BOTH")
    if penalty not in _PENALTY:
        raise ValueError("penalty must be NONE, DOUBLED or REDOUBLED")
    if overtricks < 0 or undertricks < 0:
        raise ValueError("trick deltas must be non-negative")
    if overtricks and undertricks:
        raise ValueError("overtricks and undertricks cannot both be non-zero")

    vuln: VulnerabilityCode = vulnerability  # type: ignore[assignment]
    label = contract_label(
        is_passout=is_passout,
        level=level,
        denomination=denomination,
        declarer=declarer,
        penalty=penalty,
        overtricks=overtricks,
        undertricks=undertricks,
    )

    if is_passout:
        if any(v is not None for v in (declarer, level, denomination)):
            raise ValueError("a passout cannot have a declarer or contract")
        if penalty != "NONE" or overtricks or undertricks:
            raise ValueError("a passout cannot be doubled or have a result")
        return ContractScore(
            is_passout=True,
            declarer=None,
            declarer_side=None,
            level=None,
            denomination=None,
            penalty="NONE",
            overtricks=0,
            undertricks=0,
            vulnerability=vuln,
            contract_label="Pass",
            declarer_score=0,
            score_ns=0,
            score_ew=0,
        )

    if declarer not in _PLAYER or level is None or denomination not in _DENOM:
        raise ValueError("declarer, level and denomination are required")
    if not 1 <= level <= 7:
        raise ValueError("level must be 1 through 7")

    result = overtricks - undertricks
    contract = Contract(
        level=level,
        denom=_DENOM[denomination],
        declarer=_PLAYER[declarer],
        penalty=_PENALTY[penalty],
        result=result,
    )
    declarer_score = int(contract.score(_VUL[vuln]))
    side = _DECLARER_SIDE[declarer]
    score_ns = declarer_score if side == "NS" else -declarer_score

    return ContractScore(
        is_passout=False,
        declarer=declarer,
        declarer_side=side,
        level=level,
        denomination=denomination,
        penalty=penalty,
        overtricks=overtricks,
        undertricks=undertricks,
        vulnerability=vuln,
        contract_label=label,
        declarer_score=declarer_score,
        score_ns=score_ns,
        score_ew=-score_ns,
    )


@dataclass
class MatchpointRow:
    board_no: int
    table_no: int
    ns_pair_code: str
    ew_pair_code: str
    contract_label: str | None
    score_ns: int
    score_ew: int
    ns_matchpoints: float
    ew_matchpoints: float
    comparison_size: int
    source_result_id: int | None = None


def matchpoints_for_board(
    board_no: int,
    rows: list[Any],
    *,
    id_attr: str = "id",
) -> list[MatchpointRow]:
    """Apply cross-table matchpoints to one board.

    Each result earns 2 MP for every worse N-S score and 1 MP for every equal
    N-S score.  A missing table is not represented in ``rows`` and therefore
    is neither compared nor awarded zero; the top for the played comparison
    set is ``2 * (n - 1)``.
    """
    n = len(rows)
    if n == 0:
        return []

    scores = sorted(int(r.score_ns) for r in rows)
    out: list[MatchpointRow] = []
    for row in rows:
        score = int(row.score_ns)
        worse = sum(1 for value in scores if value < score)
        equal = sum(1 for value in scores if value == score)
        ns_mp = float(2 * worse + (equal - 1))
        out.append(
            MatchpointRow(
                board_no=board_no,
                table_no=int(row.table_no),
                ns_pair_code=row.ns_pair_code,
                ew_pair_code=row.ew_pair_code,
                contract_label=row.contract_label,
                score_ns=score,
                score_ew=int(row.score_ew),
                ns_matchpoints=ns_mp,
                ew_matchpoints=float(2 * (n - 1) - ns_mp),
                comparison_size=n,
                source_result_id=getattr(row, id_attr),
            )
        )
    return out


def aggregate_rankings(board_rows: list[MatchpointRow], pair_names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Aggregate pair rankings from a frozen set of scored board rows."""
    pair_names = pair_names or {}
    totals: dict[str, dict[str, Any]] = {}
    for row in board_rows:
        top = 2 * (row.comparison_size - 1)
        for code, mp in (
            (row.ns_pair_code, row.ns_matchpoints),
            (row.ew_pair_code, row.ew_matchpoints),
        ):
            item = totals.setdefault(
                code,
                {"pair_code": code, "pair_name": pair_names.get(code, code), "matchpoints": 0.0, "available_matchpoints": 0, "boards": 0},
            )
            item["matchpoints"] += mp
            item["available_matchpoints"] += top
            item["boards"] += 1

    rankings = list(totals.values())
    for item in rankings:
        available = item["available_matchpoints"]
        item["percentage"] = round(100.0 * item["matchpoints"] / available, 2) if available else 0.0
        item["matchpoints"] = round(item["matchpoints"], 1)

    rankings.sort(key=lambda r: (-r["percentage"], -r["matchpoints"], r["pair_code"]))
    current_rank = 0
    previous_key: tuple[float, float] | None = None
    for item in rankings:
        key = (item["percentage"], item["matchpoints"])
        if previous_key is None or key != previous_key:
            current_rank += 1
            previous_key = key
        item["rank"] = current_rank
    return rankings
