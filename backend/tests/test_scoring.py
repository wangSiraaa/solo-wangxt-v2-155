from app.scoring import ContractInput, score_contract, vulnerability_for_board


def test_board_vulnerability_standard_cycle():
    # Standard first 16 boards: None, NS, EW, All, NS, ...
    assert [vulnerability_for_board(n) for n in range(1, 9)] == [
        "none",
        "NS",
        "EW",
        "both",
        "NS",
        "EW",
        "both",
        "none",
    ]


def test_vulnerable_doubled_undertrick_hand_example():
    # 4SX by North on board 2: NS vulnerable, two down.
    # Penalty: 200 + 300 = 500 to EW.
    contract = ContractInput(level=4, denomination="S", declarer="N", doubled="doubled", result=-2)
    breakdown = score_contract(contract, "NS")
    assert breakdown.declarer_score == -500
    assert breakdown.ns_score == -500
    assert breakdown.ew_score == 500
    assert breakdown.penalty_points == 500
    assert breakdown.contract_points == 0


def test_overtrick_and_doubled_insult_hand_example():
    # 3NT doubled, non-vulnerable, one over:
    # 2*(40+30+30)=200; non-vul game 300; insult 50; doubled overtrick 100 = 650.
    contract = ContractInput(level=3, denomination="NT", declarer="E", doubled="doubled", result=1)
    breakdown = score_contract(contract, "none")
    assert breakdown.declarer_score == 650
    assert breakdown.ns_score == -650
    assert breakdown.ew_score == 650
    assert breakdown.contract_points == 200
    assert breakdown.overtrick_points == 100


def test_explicit_and_endplay_agree_for_redoubled_made_contract():
    contract = ContractInput(level=4, denomination="H", declarer="W", doubled="redoubled", result=0)
    endplay = score_contract(contract, "EW", engine="endplay")
    explicit = score_contract(contract, "EW", engine="explicit")
    assert endplay == explicit
    # 4H XX = 480 contract points, vulnerable game 500, insult 100 = 1080 EW.
    assert explicit.ew_score == 1080


def test_passed_out_is_zero_result_not_missing_placeholder():
    breakdown = score_contract(
        ContractInput(level=0, denomination="NT", declarer="N", passed_out=True),
        "both",
    )
    assert breakdown.ns_score == 0
    assert breakdown.ew_score == 0
