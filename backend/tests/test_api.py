from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def create_sample_event():
    response = client.post(
        "/events",
        json={
            "name": "API sample",
            "pairs": [
                {"code": "NS1", "name": "NS 1"},
                {"code": "NS2", "name": "NS 2"},
                {"code": "NS3", "name": "NS 3"},
                {"code": "NS4", "name": "NS 4"},
                {"code": "EW1", "name": "EW 1"},
                {"code": "EW2", "name": "EW 2"},
                {"code": "EW3", "name": "EW 3"},
                {"code": "EW4", "name": "EW 4"},
            ],
            "movement": [
                {"round_no": 1, "table_no": table, "ns_pair_code": f"NS{table}", "ew_pair_code": f"EW{table}"}
                for table in range(1, 5)
            ],
            "board_assignments": [
                {"round_no": 1, "table_no": table, "board_no": 2}
                for table in range(1, 5)
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def result(table, **overrides):
    payload = {
        "board_no": 2,
        "table_no": table,
        "round_no": 1,
        "ns_pair_code": f"NS{table}",
        "ew_pair_code": f"EW{table}",
        "declarer": "S",
        "level": 4,
        "denomination": "S",
        "penalty": "DOUBLED",
        "overtricks": 0,
        "undertricks": 1,
        "source_ref": f"api-source-{table}",
        "entered_by": "tester",
    }
    payload.update(overrides)
    return payload


def test_api_scores_audits_ties_missing_table_and_freezes_publication():
    event_id = create_sample_event()

    assert client.post(f"/events/{event_id}/results", json=result(1)).status_code == 201

    # Tables 2 and 3 tie at +110 for N-S.
    tied_by_table = {
        2: {"declarer": "N", "level": 3, "denomination": "C", "penalty": "NONE", "undertricks": 0, "overtricks": 0},
        3: {"declarer": "N", "level": 2, "denomination": "D", "penalty": "NONE", "undertricks": 0, "overtricks": 1},
    }
    for table in (2, 3):
        response = client.post(f"/events/{event_id}/results", json=result(table, **tied_by_table[table]))
        assert response.status_code == 201, response.text

    # Table 4 is scheduled but no row is submitted: audit excludes it.
    audit = client.get(f"/events/{event_id}/audit").json()
    assert audit["boards"]["2"]["played_table_count"] == 3
    assert audit["boards"]["2"]["available_matchpoints_per_side"] == 4
    assert audit["boards"]["2"]["played_tables"] == [1, 2, 3]
    assert audit["missing_results"] == [
        {
            "board_no": 2,
            "table_no": 4,
            "round_no": 1,
            "ns_pair_code": "NS4",
            "ew_pair_code": "EW4",
            "handling": "excluded_from_comparison; not scored as zero",
        }
    ]
    by_table = {row["table_no"]: row for row in audit["results"]}
    assert by_table[1]["ns_matchpoints"] == 0
    assert by_table[2]["ns_matchpoints"] == 3
    assert by_table[3]["ns_matchpoints"] == 3

    publication = client.post(
        f"/events/{event_id}/publications",
        json={"name": "frozen"},
    ).json()
    frozen = client.get(f"/publications/{publication['id']}").json()
    assert frozen["result_count"] == 3
    assert len(frozen["board_scores"]) == 3
    assert all(score["source_result_id"] for score in frozen["board_scores"])


def test_duplicate_same_board_table_requires_source_review():
    event_id = create_sample_event()
    first = client.post(f"/events/{event_id}/results", json=result(1))
    assert first.status_code == 201

    # An identical retry with the same source is idempotent.
    retry = client.post(f"/events/{event_id}/results", json=result(1))
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]

    # A different result/source for the same table/board is not silently merged.
    conflict = client.post(
        f"/events/{event_id}/results",
        json=result(1, source_ref="different-sheet", overtricks=1, undertricks=0, penalty="NONE", declarer="N", level=3, denomination="NT"),
    )
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["source_matches"] is False
    assert detail["existing_source_ref"] == "api-source-1"


def test_rejects_result_not_matching_the_frozen_movement():
    event_id = create_sample_event()
    payload = result(1, table_no=2, ns_pair_code="NS1", ew_pair_code="EW1")
    response = client.post(f"/events/{event_id}/results", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "pair codes do not match this scheduled table"


def test_correction_keeps_original_source_traceability():
    event_id = create_sample_event()
    original = client.post(f"/events/{event_id}/results", json=result(1)).json()
    corrected_payload = result(
        1,
        source_ref="director-correction-1",
        overtricks=0,
        undertricks=0,
        penalty="NONE",
        declarer="N",
        level=3,
        denomination="C",
    )

    corrected = client.post(f"/events/{event_id}/results/{original['id']}/correction", json=corrected_payload)
    assert corrected.status_code == 200, corrected.text
    corrected_body = corrected.json()
    assert corrected_body["id"] != original["id"]

    history = client.get(f"/events/{event_id}/results?include_superseded=true").json()
    by_id = {row["id"]: row for row in history}
    assert by_id[original["id"]]["status"] == "SUPERSEDED"
    assert by_id[original["id"]]["superseded_by_id"] == corrected_body["id"]
    assert by_id[corrected_body["id"]]["status"] == "ACTIVE"
    assert by_id[corrected_body["id"]]["score_ns"] == 110
