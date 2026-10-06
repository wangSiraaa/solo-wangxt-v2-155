"""Bridge scoring primitives.

The score itself is calculated with endplay's :class:`Contract` and
:class:`Vul`.  A small explicit calculator is retained to produce an auditable
breakdown and to keep the documented hand examples executable in environments
where the native DDS wheel cannot be installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from endplay.types import Board as EndplayBoard
from endplay.types import Contract as EndplayContract
from endplay.types import Denom, Penalty, Player, Vul

Declarer = Literal["N", "E", "S", "W"]
DoubledState = Literal["none", "doubled", "redoubled"]
Denomination = Literal["C", "D", "H", "S", "NT"]
Vulnerability = Literal["none", "NS", "EW", "both"]
Side = Literal["NS", "EW"]

_PENALTY = {
    "none": Penalty.passed,
    "doubled": Penalty.doubled,
    "redoubled": Penalty.redoubled,
}
_PLAYER = {seat: Player.find(seat) for seat in "NESW"}
_VUL = {
    "none": Vul.none,
    "NS": Vul.ns,
    "EW": Vul.ew,
    "both": Vul.both,
}


@dataclass(frozen=True)
class ContractInput:
    level: int
    denomination: Denomination
    declarer: Declarer
    doubled: DoubledState = "none"
    # Positive: overtricks. Negative: undertricks. Zero means exactly made.
    result: int = 0
    passed_out: bool = False


@dataclass(frozen=True)
class ScoreBreakdown:
    contract_side: Side
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

    @property
    def score_ns(self) -> int:
        """Signed NS score; EW score is always the negative of this value."""
        return self.ns_score


def vulnerability_for_board(board_number: int) -> Vulnerability:
    """Return standard duplicate bridge vulnerability by board number."""
    endplay_board = EndplayBoard(board_num=board_number)
    mapping = {Vul.none: "none", Vul.ns: "NS", Vul.ew: "EW", Vul.both: "both"}
    return mapping[endplay_board.vul]


def side_of(declarer: Declarer) -> Side:
    return "NS" if declarer in ("N", "S") else "EW"


def _contract_points(level: int, denomination: Denomination, doubled: DoubledState) -> int:
    per_trick = 20 if denomination in ("C", "D") else 30
    points = level * per_trick + (10 if denomination == "NT" else 0)
    return points * {"none": 1, "doubled": 2, "redoubled": 4}[doubled]


def _undertrick_penalty(undertricks: int, vulnerable: bool, doubled: DoubledState) -> int:
    """Return positive penalty points awarded to the defenders."""
    if doubled == "none":
        return undertricks * (100 if vulnerable else 50)

    multiplier = 1 if doubled == "doubled" else 2
    if vulnerable:
        # First undertrick 200, further undertricks 300 before the XX multiplier.
        unscaled = 200 + (undertricks - 1) * 300
    else:
        # 100, 200, 200, then 300 each before the XX multiplier.
        if undertricks == 1:
            unscaled = 100
        elif undertricks == 2:
            unscaled = 300
        elif undertricks == 3:
            unscaled = 500
        else:
            unscaled = 500 + (undertricks - 3) * 300
    return unscaled * multiplier


def score_contract(
    contract: ContractInput,
    vulnerability: Vulnerability,
    *,
    engine: Literal["endplay", "explicit"] = "endplay",
) -> ScoreBreakdown:
    """Calculate a duplicate bridge score and orient it to NS/EW.

    ``ns_score`` is signed: a positive number is NS plus, negative is EW plus.
    Passed-out boards are zero for both sides and remain a real comparison
    result; they are never confused with an unplayed table.
    """
    contract_side = side_of(contract.declarer)
    vulnerable = (
        vulnerability == "both"
        or (vulnerability == "NS" and contract_side == "NS")
        or (vulnerability == "EW" and contract_side == "EW")
    )

    if contract.passed_out or contract.level == 0:
        return ScoreBreakdown(contract_side, vulnerable, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    undertricks = -contract.result if contract.result < 0 else 0
    overtricks = max(contract.result, 0)

    if undertricks:
        contract_points = 0
        game_or_part_bonus = 0
        slam_bonus = 0
        insult_bonus = 0
        overtrick_points = 0
        penalty_points = _undertrick_penalty(undertricks, vulnerable, contract.doubled)
        declarer_score = -penalty_points
    else:
        contract_points = _contract_points(contract.level, contract.denomination, contract.doubled)
        game_or_part_bonus = 500 if vulnerable and contract_points >= 100 else 300 if contract_points >= 100 else 50
        slam_bonus = 0
        if contract.level == 6:
            slam_bonus = 750 if vulnerable else 500
        elif contract.level == 7:
            slam_bonus = 1500 if vulnerable else 1000
        insult_bonus = {"none": 0, "doubled": 50, "redoubled": 100}[contract.doubled]

        if contract.doubled == "none":
            per_overtrick = 20 if contract.denomination in ("C", "D") else 30
        else:
            per_overtrick = (200 if vulnerable else 100) * (2 if contract.doubled == "redoubled" else 1)
        overtrick_points = overtricks * per_overtrick
        penalty_points = 0
        declarer_score = (
            contract_points
            + game_or_part_bonus
            + slam_bonus
            + insult_bonus
            + overtrick_points
        )

    if engine == "endplay":
        endplay_contract = EndplayContract(
            level=contract.level,
            denom=Denom.find(contract.denomination),
            declarer=Player.find(contract.declarer),
            penalty=_PENALTY[contract.doubled],
            result=contract.result,
        )
        endplay_score = endplay_contract.score(_VUL[vulnerability])
        # Keep the explicit breakdown internally, but never allow it to drift
        # from the score returned by the required scoring library.
        if endplay_score != declarer_score:
            raise AssertionError(f"endplay score {endplay_score} != explicit score {declarer_score}")

    ns_score = declarer_score if contract_side == "NS" else -declarer_score
    return ScoreBreakdown(
        contract_side=contract_side,
        vulnerable=vulnerable,
        ns_score=ns_score,
        ew_score=-ns_score,
        declarer_score=declarer_score,
        contract_points=contract_points,
        game_or_part_bonus=game_or_part_bonus,
        slam_bonus=slam_bonus,
        insult_bonus=insult_bonus,
        overtrick_points=overtrick_points,
        penalty_points=penalty_points,
    )
