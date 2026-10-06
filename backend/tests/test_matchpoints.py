from app.matchpoints import calculate_board_matchpoints, calculate_ranking


def _row(result_id: int, table: int, ns: int, ew: int, score: int):
    return {
        "id": result_id,
        "table_number": table,
        "ns_pair_number": ns,
        "ew_pair_number": ew,
        "ns_score": score,
    }


def test_tied_scores_receive_split_matchpoints():
    results = [
        _row(1, 1, 1, 2, 420),
        _row(2, 2, 3, 4, 420),
        _row(3, 3, 5, 6, -50),
    ]
    board = calculate_board_matchpoints(2, results, [1, 2, 3])
    lines = {line.table_number: line for line in board.lines}
    assert lines[1].ns_matchpoints == 1.5
    assert lines[2].ns_matchpoints == 1.5
    assert lines[3].ns_matchpoints == 0.0
    assert lines[1].ew_matchpoints == 0.5
    assert lines[2].ew_matchpoints == 0.5
    assert lines[3].ew_matchpoints == 2.0


def test_missing_table_is_not_zero_and_only_reported_results_are_compared():
    results = [
        _row(1, 1, 1, 2, 420),
        _row(2, 2, 3, 4, -50),
    ]
    board = calculate_board_matchpoints(1, results, [1, 2, 3])
    assert board.compared_table_count == 2
    assert board.max_matchpoints == 1.0
    assert board.missing_table_numbers == (3,)
    assert "未计零分" in board.note
    table1 = next(line for line in board.lines if line.table_number == 1)
    table3_pair = 7
    # Pair at absent table is simply absent from this board; it is not beaten
    # as a phantom zero by the reported positive score.
    assert table3_pair not in {line.ns_pair_number for line in board.lines}
    assert table1.ns_matchpoints == 1.0


def test_single_report_has_no_matchpoint_comparison():
    board = calculate_board_matchpoints(3, [_row(1, 2, 1, 2, 170)], [1, 2, 3])
    assert board.max_matchpoints == 0
    assert board.lines[0].ns_matchpoints == 0
    assert board.lines[0].ew_matchpoints == 0
    assert board.missing_table_numbers == (1, 3)


def test_ranking_percentage_skips_unplayed_board_denominator():
    first = calculate_board_matchpoints(
        1,
        [_row(1, 1, 1, 10, 100), _row(2, 2, 2, 20, -100)],
        [1, 2],
    )
    second = calculate_board_matchpoints(
        2,
        [_row(3, 1, 1, 20, -50), _row(4, 2, 2, 10, 50)],
        [1, 2],
    )
    # Pair 30 is expected on board 3 but that board has no reported result.
    expected = {
        1: {1, 2},
        2: {1, 2},
        10: {1, 2},
        20: {1, 2},
        30: {3},
    }
    ranking = calculate_ranking([first, second], expected)
    by_pair = {row.pair_number: row for row in ranking}
    assert by_pair[1].total_matchpoints == 1
    assert by_pair[1].available_matchpoints == 2
    assert by_pair[1].percentage == 50.0
    assert by_pair[30].percentage is None
    assert by_pair[30].boards_missing == (3,)
