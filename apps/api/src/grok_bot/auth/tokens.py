import base64
import hashlib
import hmac
import json
import time
from uuid import UUID


class TokenError(Exception):
    pass


def mint_local_token(
    *,
    secret: str,
    user_id: UUID,
    organization_id: UUID,
    environment: str,
    ttl_seconds: int,
) -> str:
    payload = {
        "amr": "local_dev",
        "env": environment,
        "exp": int(time.time()) + ttl_seconds,
        "org": str(organization_id),
        "sub": str(user_id),
        "v": 1,
    }
    return _sign(payload, secret)


def verify_token(token: str, secret: str) -> dict:
    try:
        version, body, signature = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed") from exc
    if version != "v1":
        raise TokenError("version")
    expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise TokenError("signature")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise TokenError("payload") from exc
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise TokenError("expired")
    return payload


def _sign(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v1.{body}.{signature}"
