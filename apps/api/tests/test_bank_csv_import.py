from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from grok_bot.domain.bank_imports import CSV_COLUMNS, MAX_CSV_BYTES, MAX_CSV_ROWS, parse_canonical_csv
from tests.test_accounting_core import _world

HEADER = ",".join(CSV_COLUMNS) + "\n"
BANK_ID = str(uuid4())


def test_csv_preserves_integer_cents_quotes_bom_and_signed_amounts():
    rows = parse_canonical_csv("\ufeff" + HEADER + f'{BANK_ID},"bank,ref",10001,2026-11-01\r\n\n{BANK_ID},debit,-50,2026-11-02\n')
    assert [row["amount_cents"] for row in rows] == [10001, -50]
    assert rows[0]["external_id"] == "bank,ref"
    assert str(rows[0]["bank_account_id"]) == BANK_ID
    assert str(rows[1]["posted_on"]) == "2026-11-02"


@pytest.mark.parametrize("row", [
    f"{BANK_ID},event,10.01,2026-11-01\n",
    f"{BANK_ID},event,1e2,2026-11-01\n",
    f"{BANK_ID},event,9223372036854775808,2026-11-01\n",
    f"{BANK_ID},event,100,2026-02-30\n",
    f"{BANK_ID},event,100,20261101\n",
    "not-a-uuid,event,100,2026-11-01\n",
    f"{BANK_ID}, ,100,2026-11-01\n",
    f"{BANK_ID},nul\x00reference,100,2026-11-01\n",
    f"{BANK_ID},event,100,2026-11-01,extra\n",
    f'{BANK_ID},"unterminated,100,2026-11-01\n',
])
def test_csv_rejects_malformed_rows_without_echoing_sensitive_values(row):
    with pytest.raises(HTTPException) as exc:
        parse_canonical_csv(HEADER + row)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "INVALID_BANK_CSV"
    assert exc.value.detail["details"]["line"] == 2
    assert BANK_ID not in exc.value.detail["message"]


@pytest.mark.parametrize("contents", [None, "", HEADER, "amount,date\n100,2026-11-01", "x" * (MAX_CSV_BYTES + 1)], ids=["missing", "empty", "header-only", "unknown-header", "too-large"])
def test_csv_requires_supported_header_data_and_bounded_size(contents):
    with pytest.raises(HTTPException) as exc:
        parse_canonical_csv(contents)
    assert exc.value.status_code == 422


def test_csv_bounds_number_of_transactions():
    with pytest.raises(HTTPException):
        parse_canonical_csv(HEADER + f"{BANK_ID},event,1,2026-11-01\n" * (MAX_CSV_ROWS + 1))


def test_csv_api_import_replay_json_dedup_and_conflict(client, migrator_engine):
    world = _world(client, migrator_engine)
    transaction = {"bank_account_id": world["bank_id"], "external_id": "csv-reference", "amount_cents": 10001, "posted_on": "2026-11-01"}
    csv_text = HEADER + f"{world['bank_id']},csv-reference,10001,2026-11-01\n"
    headers = {**world["accounting"], "Idempotency-Key": "csv-canonical"}
    body = {"format": "canonical_csv_v1", "csv_text": csv_text}
    first = client.post("/v1/bank-imports", headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["created"] == 1
    replay = client.post("/v1/bank-imports", headers=headers, json=body)
    assert replay.json() == first.json()
    dedup = client.post("/v1/bank-imports", headers={**headers, "Idempotency-Key": "csv-as-json"}, json={"transactions": [transaction]})
    assert dedup.status_code == 201, dedup.text
    assert dedup.json()["existing"] == 1
    conflict = client.post("/v1/bank-imports", headers={**headers, "Idempotency-Key": "csv-conflict"}, json={**body, "csv_text": csv_text.replace(",10001,", ",20000,")})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "BANK_TRANSACTION_CONFLICT"


def test_csv_invalid_later_row_inserts_nothing_and_ai_cannot_import(client, migrator_engine):
    world = _world(client, migrator_engine)
    good = HEADER + f"{world['bank_id']},valid-prefix,100,2026-11-01\n"
    body = {"format": "canonical_csv_v1", "csv_text": good + "invalid,row\n"}
    response = client.post("/v1/bank-imports", headers={**world["accounting"], "Idempotency-Key": "invalid-csv"}, json=body)
    assert response.status_code == 422, response.text
    with migrator_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM bank_transactions WHERE bank_account_id = :bank_id"), {"bank_id": world["bank_id"]}).scalar_one() == 0
    forbidden = client.post("/v1/bank-imports", headers={**world["ai"], "Idempotency-Key": "ai-csv"}, json={**body, "csv_text": good})
    assert forbidden.status_code == 403


def test_csv_and_json_cannot_be_combined(client, migrator_engine):
    world = _world(client, migrator_engine)
    response = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "mixed-import"},
        json={"format": "canonical_csv_v1", "csv_text": HEADER, "transactions": [{"bank_account_id": world["bank_id"], "external_id": "mixed", "amount_cents": 1, "posted_on": "2026-11-01"}]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_BANK_IMPORT"
