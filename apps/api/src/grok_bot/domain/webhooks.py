"""Signed local webhook inbox. Production ingress stays closed."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from grok_bot.crypto import encrypt_text
from grok_bot.db import set_tenant
from grok_bot.errors import problem


def accept_webhook(session, settings, provider: str, body: bytes, signature: str | None, now: datetime) -> dict:
    if not settings.webhook_ingress_enabled:
        problem(409, "WEBHOOK_NOT_CONFIGURED", "Webhook ingress is disabled. Nothing was stored.")
    if provider != "local":
        problem(404, "NOT_FOUND", "That provider is not configured.")
    expected = hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if signature is None or not hmac.compare_digest(expected, signature):
        problem(401, "INVALID_SIGNATURE", "The webhook signature is not valid.")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        problem(422, "VALIDATION_ERROR", "The webhook body is not JSON.")
    sent_at = _sent_at(payload)
    if abs((now - sent_at).total_seconds()) > settings.webhook_replay_seconds:
        problem(401, "WEBHOOK_STALE", "The webhook timestamp is outside the replay window.")
    organization_id = UUID(payload["organization_id"])
    provider_event_id = str(payload["provider_event_id"])
    set_tenant(session, organization_id, None, access_mode="webhook")
    ciphertext, nonce, key_version = encrypt_text(body.decode("utf-8"), settings.contact_key_bytes)
    try:
        with session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO inbox_events (
                      id, organization_id, provider, provider_event_id,
                      payload_ciphertext, payload_nonce, key_version
                    ) VALUES (
                      :id, :organization_id, :provider, :provider_event_id,
                      :payload_ciphertext, :payload_nonce, :key_version
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "provider": provider,
                    "provider_event_id": provider_event_id,
                    "payload_ciphertext": ciphertext,
                    "payload_nonce": nonce,
                    "key_version": key_version,
                },
            )
            session.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                      id, organization_id, event_type, payload, dedup_key, status
                    ) VALUES (
                      :id, :organization_id, :event_type, CAST(:payload AS jsonb), :dedup_key, 'PENDING'
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "event_type": payload["event_type"],
                    "payload": json.dumps(
                        {
                            "actor_id": payload["actor_id"],
                            "invoice_id": payload.get("invoice_id"),
                            "posting_date": payload.get("posting_date"),
                        },
                        sort_keys=True,
                    ),
                    "dedup_key": f"webhook:{provider}:{provider_event_id}",
                },
            )
    except IntegrityError:
        return {"status": "duplicate", "provider_event_id": provider_event_id, "delivered": False}
    return {"status": "accepted", "provider_event_id": provider_event_id, "delivered": False}


def _sent_at(payload: dict) -> datetime:
    raw = payload.get("sent_at")
    if not isinstance(raw, str):
        problem(422, "VALIDATION_ERROR", "sent_at is required.")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
