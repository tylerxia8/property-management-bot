"""Read-only readiness checks for the loopback fictional demo; prints no tokens."""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


def check_demo(base_url: str = "http://127.0.0.1:3000") -> list[str]:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Demo readiness checks require a loopback HTTP URL.")
    base_url = base_url.rstrip("/")

    def request(path, *, body=None, token=None, html=False):
        headers = {"Accept": "text/html" if html else "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None if body is None else json.dumps(body).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(base_url + path, data=data, headers=headers), timeout=10) as response:
                raw = response.read()
        except urllib.error.HTTPError as failure:
            raise RuntimeError(f"Demo check failed: HTTP {failure.code} at {path}") from None
        return raw.decode() if html else json.loads(raw)

    if request("/v1/health").get("status") != "ok":
        raise RuntimeError("The local API is not healthy.")
    home = request("/", html=True)
    if "Fixture sample." not in home or "Choose a walkthrough" not in home:
        raise RuntimeError("The updated fictional demo home screen is not running.")
    results = ["Local home and API are ready"]
    for role, path in [
        ("accounting_staff", "/v1/properties"),
        ("prospect", "/v1/listings"),
        ("tenant", "/v1/me"),
        ("property_manager", "/v1/human-reviews"),
        ("owner", "/v1/statements"),
    ]:
        token = request("/v1/demo/session", body={"role": role})["token"]
        me = request("/v1/me", token=token)
        if role not in me["roles"]:
            raise RuntimeError(f"The {role} sample role is not configured.")
        result = request(path, token=token)
        if role == "owner" and not result.get("items"):
            raise RuntimeError("The owner walkthrough statement is missing.")
        if role == "property_manager":
            switches = request("/v1/kill-switches", token=token)
            if any(switches.get(name) is not False for name in ("payment_enabled", "messaging_enabled", "calendar_enabled")):
                raise RuntimeError("Demo outbound capabilities must remain disabled.")
        results.append(f"{role}: access verified")
    results.append("Payment, messaging, and calendar outbound are disabled")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    try:
        for result in check_demo(args.base_url):
            print(result)
    except (ValueError, RuntimeError, urllib.error.URLError, TimeoutError) as failure:
        raise SystemExit(str(failure)) from None
