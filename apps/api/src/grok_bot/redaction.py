SENSITIVE_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "account_number",
        "routing_number",
        "door_code",
        "signed_url",
        "ssn",
        "email",
        "phone",
        "contact_value",
        "ciphertext",
        "dev_password_hash",
        "cookie",
        "set-cookie",
        "session_secret",
        "encryption_key",
    }
)


def redact(value):
    """Return a copy with sensitive object keys replaced. The input is not modified."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
