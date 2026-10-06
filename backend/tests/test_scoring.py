from types import SimpleNamespace

from endplay.types import Penalty  # noqa: F401  # proves the required bridge library imports

from app.scoring import (
    aggregate_rankings,
    contract_label,
    matchpoints_for_board,
    score_contract,
    vulnerability_for_board,
)


def test_board_vulnerability_uses_standard_sixteen_board_cycle():
    assert vulnerability_for_board(1) == "NONE"
    assert vulnerability_for_board(2) == "NS"
    assert vulnerability_for_board(3) == "EW"
    assert vulnerability_for_board(4) == "BOTH"
    assert vulnerability_for_board(16) == "EW"
    assert vulnerability_for_board(17) == "NONE"


def test_vulnerable_doubled_undertrick_hand_case():
    # Board 2: N-S vulnerable. South declares 4 spades doubled and takes
    # one trick too many. First undertrick when vulnerable and doubled is 200
    # to the defenders. Signed from N-S: -200 / +200.
    result = score_contract(
        board_no=2,
        declarer="S",
        level=4,
        denomination="S",
        penalty="DOUBLED",
        undertricks=1,
    )
    assert result.contract_label == "4♠X S -1"
    assert result.declarer_side == "NS"
    assert result.declarer_score == -200
    assert result.score_ns == -200
    assert result.score_ew == 200


def test_making_vulnerable_game_bonus_and_signs_are_consistent():
    result = score_contract(board_no=2, declarer="S", level=4, denomination="H", penalty="NONE")
    assert result.score_ns == 620
    assert result.score_ew == -620

    east_result = score_contract(board_no=2, declarer="E", level=4, denomination="H", penalty="NONE")
    assert east_result.declarer_side == "EW"
    assert east_result.score_ew == 420  # E-W are not vulnerable on board 2
    assert east_result.score_ns == -420


def test_tied_matchpoints_and_missing_table_are_hand_calculated():
    # Four tables were scheduled, but only tables 1-3 reported. Table 4 must
    # not be inserted as zero; top for the three-result comparison is 4.
    rows_data = [
        SimpleNamespace(id=101, table_no=1, ns_pair_code="NS1", ew_pair_code="EW1", contract_label="3C N =", score_ns=110, score_ew=-110),
        SimpleNamespace(id=102, table_no=2, ns_pair_code="NS2", ew_pair_code="EW2", contract_label="1NT N +1", score_ns=110, score_ew=-110),
        SimpleNamespace(id=103, table_no=3, ns_pair_code="NS3", ew_pair_code="EW3", contract_label="4S N -1", score_ns=-100, score_ew=100),
    ]
    rows = matchpoints_for_board(1, rows_data)
    by_table = {row.table_no: row for row in rows}

    assert [by_table[t].comparison_size for t in (1, 2, 3)] == [3, 3, 3]
    assert by_table[1].ns_matchpoints == 3
    assert by_table[2].ns_matchpoints == 3
    assert by_table[3].ns_matchpoints == 0
    assert by_table[1].ew_matchpoints == 1
    assert by_table[2].ew_matchpoints == 1
    assert by_table[3].ew_matchpoints == 4


def test_ranking_aggregation_keeps_ties_together():
    rows_data = [
        SimpleNamespace(id=101, table_no=1, ns_pair_code="A", ew_pair_code="B", contract_label="X", score_ns=110, score_ew=-110),
        SimpleNamespace(id=102, table_no=2, ns_pair_code="A", ew_pair_code="C", contract_label="Y", score_ns=-100, score_ew=100),
    ]
    rows = matchpoints_for_board(1, rows_data)
    rankings = aggregate_rankings(rows, {"A": "A", "B": "B", "C": "C"})
    by_pair = {r["pair_code"]: r for r in rankings}
    assert by_pair["C"]["rank"] == 1
    assert by_pair["A"]["rank"] == 2
    assert by_pair["B"]["rank"] == 3
    assert by_pair["A"]["percentage"] == 50.0


def test_passout_is_explicit_zero_not_missing_data():
    result = score_contract(board_no=1, is_passout=True)
    assert result.is_passout is True
    assert result.score_ns == 0
    assert result.score_ew == 0


def test_contract_label_forms_are_readable_for_audit():
    assert contract_label(
        is_passout=False,
        level=3,
        denomination="NT",
        declarer="W",
        penalty="REDOUBLED",
        overtricks=1,
        undertricks=0,
    ) == "3NTXX W +1"
