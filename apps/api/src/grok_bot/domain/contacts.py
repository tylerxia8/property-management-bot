from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.crypto import decrypt_text, encrypt_text


def store_contact(
    session: Session,
    *,
    organization_id: UUID,
    party_id: UUID,
    kind: str,
    value: str,
    key: bytes,
) -> UUID:
    contact_id = uuid4()
    ciphertext, nonce, key_version = encrypt_text(value, key)
    session.execute(
        text(
            """
            INSERT INTO contacts (
              id, organization_id, party_id, kind, ciphertext, nonce, key_version
            ) VALUES (
              :id, :organization_id, :party_id, :kind, :ciphertext, :nonce, :key_version
            )
            """
        ),
        {
            "id": contact_id,
            "organization_id": organization_id,
            "party_id": party_id,
            "kind": kind,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "key_version": key_version,
        },
    )
    return contact_id


def read_contact_value(session: Session, *, organization_id: UUID, contact_id: UUID, key: bytes) -> str:
    row = session.execute(
        text(
            """
            SELECT ciphertext, nonce
            FROM contacts
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": contact_id},
    ).mappings().one()
    return decrypt_text(bytes(row["ciphertext"]), bytes(row["nonce"]), key)


def store_inbox_event(
    session: Session,
    *,
    organization_id: UUID,
    provider: str,
    provider_event_id: str,
    payload: bytes,
    key: bytes,
) -> UUID:
    event_id = uuid4()
    ciphertext, nonce, key_version = encrypt_text(payload.decode("utf-8"), key)
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
            "id": event_id,
            "organization_id": organization_id,
            "provider": provider,
            "provider_event_id": provider_event_id,
            "payload_ciphertext": ciphertext,
            "payload_nonce": nonce,
            "key_version": key_version,
        },
    )
    return event_id
