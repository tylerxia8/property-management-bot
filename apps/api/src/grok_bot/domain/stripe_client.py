import hashlib
import hmac
import json
import re
import time
from datetime import datetime

import httpx

from grok_bot.settings import Settings


class StripeError(Exception):
    def __init__(self, status_code: int, code: str, *, retryable: bool = False):
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.message = code.replace("_", " ").capitalize()
        super().__init__(self.message)


class StripeClient:
    def __init__(self, settings: Settings):
        self._secret = settings.stripe_secret_key.get_secret_value()
        if not re.fullmatch(r"(?:sk|rk)_test_[A-Za-z0-9]+", self._secret):
            raise StripeError(503, "STRIPE_SANDBOX_NOT_CONFIGURED")
        if settings.stripe_api_version != "2025-02-24.acacia":
            raise StripeError(503, "STRIPE_API_VERSION_INVALID")
        self._version = settings.stripe_api_version

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        idempotency_key: str | None = None,
        account: str | None = None,
    ) -> dict:
        if method not in {"GET", "POST"} or not re.fullmatch(
            r"/[a-z_]+(?:/[A-Za-z0-9_]+)*", path
        ):
            raise StripeError(500, "STRIPE_REQUEST_INVALID")
        if method == "POST" and not idempotency_key:
            raise StripeError(500, "STRIPE_IDEMPOTENCY_KEY_REQUIRED")
        if idempotency_key is not None and not re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,255}", idempotency_key
        ):
            raise StripeError(500, "STRIPE_IDEMPOTENCY_KEY_INVALID")
        if account is not None and not re.fullmatch(r"acct_[A-Za-z0-9]+", account):
            raise StripeError(500, "STRIPE_ACCOUNT_INVALID")
        headers = {
            "Authorization": f"Bearer {self._secret}",
            "Stripe-Version": self._version,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if account:
            headers["Stripe-Account"] = account
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=3.0), follow_redirects=False
        ) as client:
            for attempt in range(3):
                try:
                    response = client.request(
                        method,
                        f"https://api.stripe.com/v1{path}",
                        headers=headers,
                        params=data if method == "GET" else None,
                        data=data if method == "POST" else None,
                    )
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < 2:
                        time.sleep(0.5 * 2**attempt)
                        continue
                    raise StripeError(503, "STRIPE_UNAVAILABLE", retryable=True) from None
                except httpx.HTTPError:
                    raise StripeError(502, "STRIPE_REQUEST_FAILED") from None
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        time.sleep(0.5 * 2**attempt)
                        continue
                    raise StripeError(503, "STRIPE_UNAVAILABLE", retryable=True)
                if not response.is_success:
                    raise StripeError(502, "STRIPE_REQUEST_REJECTED")
                try:
                    result = response.json()
                except (ValueError, RecursionError):
                    raise StripeError(502, "STRIPE_RESPONSE_INVALID") from None
                if not isinstance(result, dict):
                    raise StripeError(502, "STRIPE_RESPONSE_INVALID")
                pending = [result]
                while pending:
                    value = pending.pop()
                    if isinstance(value, dict):
                        if value.get("livemode") is True:
                            raise StripeError(502, "STRIPE_LIVE_MODE_REJECTED")
                        pending.extend(value.values())
                    elif isinstance(value, list):
                        pending.extend(value)
                return result
        raise StripeError(503, "STRIPE_UNAVAILABLE", retryable=True)


def verify_webhook(
    body: bytes, signature: str | None, secret: str, now: datetime
) -> dict:
    if len(body) > 1024 * 1024:
        raise StripeError(413, "STRIPE_WEBHOOK_TOO_LARGE")
    if not signature or len(signature) > 8192 or not secret.startswith("whsec_"):
        raise StripeError(400, "STRIPE_WEBHOOK_SIGNATURE_INVALID")
    timestamps = []
    signatures = []
    for part in signature.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            raise StripeError(400, "STRIPE_WEBHOOK_SIGNATURE_INVALID")
        if key == "t":
            timestamps.append(value)
        elif key == "v1":
            signatures.append(value)
    if len(timestamps) != 1 or not re.fullmatch(r"[0-9]{1,12}", timestamps[0]):
        raise StripeError(400, "STRIPE_WEBHOOK_SIGNATURE_INVALID")
    timestamp = timestamps[0]
    if abs(now.timestamp() - int(timestamp)) > 300:
        raise StripeError(400, "STRIPE_WEBHOOK_SIGNATURE_EXPIRED")
    expected = hmac.new(
        secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    if not any(
        hmac.compare_digest(expected, value)
        for value in signatures
        if re.fullmatch(r"[0-9a-f]{64}", value)
    ):
        raise StripeError(400, "STRIPE_WEBHOOK_SIGNATURE_INVALID")
    try:
        event = json.loads(body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise StripeError(400, "STRIPE_WEBHOOK_PAYLOAD_INVALID") from None
    if (
        not isinstance(event, dict)
        or event.get("livemode") is not False
        or not isinstance(event.get("id"), str)
        or not re.fullmatch(r"evt_[A-Za-z0-9]+", event["id"])
        or not isinstance(event.get("type"), str)
        or not event["type"]
        or not isinstance(event.get("data"), dict)
        or not isinstance(event["data"].get("object"), dict)
        or event["data"]["object"].get("livemode") is True
    ):
        raise StripeError(400, "STRIPE_WEBHOOK_PAYLOAD_INVALID")
    return event
