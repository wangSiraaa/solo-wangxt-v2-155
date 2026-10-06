def make_event(client, name="示例赛", table_count=3, boards=(1, 2)):
    response = client.post(
        "/api/events",
        json={"name": name, "table_count": table_count, "board_numbers": list(boards)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def result_payload(**overrides):
    payload = {
        "board_number": 1,
        "table_number": 1,
        "declarer": "N",
        "level": 4,
        "denomination": "S",
        "doubled": "doubled",
        "overtricks": 0,
        "undertricks": 2,
        "source": "tablet-1",
    }
    payload.update(overrides)
    return payload


def test_api_board_metadata_results_and_mp_trace(client):
    event = make_event(client)
    boards = client.get(f"/api/events/{event['id']}/boards").json()
    board1 = next(row for row in boards if row["board_number"] == 1)
    board2 = next(row for row in boards if row["board_number"] == 2)
    assert board1["vulnerability"] == "none"
    assert board2["vulnerability"] == "NS"
    assert board1["dealer"] == "N"

    # Board 1 is non-vulnerable: 4SX-2 = NS -300. Table 2 1NT= = NS +90. Table 3 absent.
    response = client.post(f"/api/events/{event['id']}/results", json=result_payload())
    assert response.status_code == 201, response.text
    assert response.json()["ns_score"] == -300

    response = client.post(
        f"/api/events/{event['id']}/results",
        json=result_payload(
            table_number=2,
            declarer="N",
            level=1,
            denomination="NT",
            doubled="none",
            undertricks=0,
            source="tablet-2",
        ),
    )
    assert response.status_code == 201, response.text

    mp = client.get(f"/api/events/{event['id']}/boards/1/matchpoints").json()
    assert mp["compared_table_count"] == 2
    assert mp["missing_table_numbers"] == [3]
    assert mp["max_matchpoints"] == 1.0
    assert mp["note"].endswith("未计零分。")
    table1 = next(row for row in mp["lines"] if row["table_number"] == 1)
    table2 = next(row for row in mp["lines"] if row["table_number"] == 2)
    assert table1["ns_matchpoints"] == 0
    assert table2["ns_matchpoints"] == 1
    assert len(table1["comparisons"]) == 1
    assert table1["comparisons"][0]["outcome_for_ns"] == "worse"


def test_api_identical_duplicate_is_idempotent_and_conflicting_source_is_held(client):
    event = make_event(client, name="重复上报", table_count=2, boards=(1,))
    first = client.post(f"/api/events/{event['id']}/results", json=result_payload())
    assert first.status_code == 201
    duplicate = client.post(f"/api/events/{event['id']}/results", json=result_payload())
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]

    # A different device sends the same score: not silently accepted as source.
    other_source = client.post(
        f"/api/events/{event['id']}/results",
        json=result_payload(source="rescue-tablet"),
    )
    assert other_source.status_code == 409
    assert "来源" in other_source.json()["detail"]["message"]

    # A changed result from the original source is also held for adjudication.
    conflict = client.post(
        f"/api/events/{event['id']}/results",
        json=result_payload(undertricks=1),
    )
    assert conflict.status_code == 409
    duplicates = client.get(f"/api/events/{event['id']}/duplicates").json()
    assert len(duplicates) == 3
    assert {row["status"] for row in duplicates} == {"identical", "source_check", "conflict"}


def test_api_publish_freezes_comparison_set(client):
    event = make_event(client, name="发布快照", table_count=2, boards=(1,))
    client.post(
        f"/api/events/{event['id']}/results",
        json=result_payload(table_number=1, undertricks=0, overtricks=0, source="a"),
    )
    published = client.post(f"/api/events/{event['id']}/publications?note=%E5%8D%8A%E5%9C%BA%E5%8F%91%E5%B8%83")
    assert published.status_code == 201
    snapshot = published.json()
    assert snapshot["version"] == 1
    assert snapshot["board_matchpoints"][0]["compared_table_count"] == 1
    assert snapshot["board_matchpoints"][0]["missing_table_numbers"] == [2]

    # A later result changes the live comparison, but the published snapshot is fixed.
    client.post(
        f"/api/events/{event['id']}/results",
        json=result_payload(
            table_number=2,
            level=1,
            denomination="NT",
            doubled="none",
            undertricks=0,
            source="b",
        ),
    )
    latest = client.get(f"/api/events/{event['id']}/publications/latest").json()
    live = client.get(f"/api/events/{event['id']}/boards/1/matchpoints").json()
    assert latest["id"] == snapshot["id"]
    assert latest["board_matchpoints"][0]["compared_table_count"] == 1
    assert live["compared_table_count"] == 2
