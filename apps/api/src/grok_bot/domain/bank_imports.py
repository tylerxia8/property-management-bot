"""Versioned manual bank import format; never guesses a bank's export layout."""

import csv
import io
import re
from datetime import date
from uuid import UUID

from grok_bot.errors import problem

CSV_FORMAT = "canonical_csv_v1"
CSV_COLUMNS = ["bank_account_id", "external_id", "amount_cents", "posted_on"]
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 10_000


def bank_import_transactions(body: dict) -> list[dict]:
    format_name = body.get("format")
    if format_name == CSV_FORMAT:
        if body.get("transactions"):
            problem(422, "INVALID_BANK_IMPORT", "Send CSV or transaction JSON, not both.")
        return parse_canonical_csv(body.get("csv_text"))
    if format_name == "csv" or body.get("csv_text") is not None:
        problem(409, "BANK_IMPORT_FORMAT_UNCONFIGURED", "Map bank CSV columns to canonical_csv_v1 before importing.")
    if format_name not in (None, "json"):
        problem(422, "INVALID_BANK_IMPORT", "Unsupported bank import format.")
    return body["transactions"]


def parse_canonical_csv(csv_text: str | None) -> list[dict]:
    if not csv_text or len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        problem(422, "INVALID_BANK_CSV", "Supply a nonempty UTF-8 CSV of at most 2 MiB.")
    reader = csv.reader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""), strict=True)
    transactions = []
    try:
        if next(reader, None) != CSV_COLUMNS:
            problem(422, "INVALID_BANK_CSV", "CSV header must be bank_account_id,external_id,amount_cents,posted_on.")
        for row in reader:
            if not row:  # Blank lines are harmless, but partial rows are errors.
                continue
            if len(transactions) >= MAX_CSV_ROWS:
                problem(422, "INVALID_BANK_CSV", "CSV may contain at most 10000 transactions.")
            try:
                if len(row) != len(CSV_COLUMNS):
                    raise ValueError
                bank_id, external_id, amount, posted_on = (value.strip() for value in row)
                if not external_id or len(external_id) > 200 or re.search(r"[\x00-\x1f\x7f]", external_id) or not re.fullmatch(r"-?[0-9]+", amount):
                    raise ValueError
                cents = int(amount)
                if not -(2**63) <= cents < 2**63 or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", posted_on):
                    raise ValueError
                transactions.append({
                    "bank_account_id": UUID(bank_id),
                    "external_id": external_id,
                    "amount_cents": cents,
                    "posted_on": date.fromisoformat(posted_on),
                })
            except ValueError:
                problem(422, "INVALID_BANK_CSV", "Invalid bank transaction row; check columns, UUID, ID, integer cents, and date.", details={"line": reader.line_num})
    except csv.Error:
        problem(422, "INVALID_BANK_CSV", "Malformed CSV quoting or field size.", details={"line": reader.line_num})
    if not transactions:
        problem(422, "INVALID_BANK_CSV", "CSV must contain at least one transaction.")
    return transactions
