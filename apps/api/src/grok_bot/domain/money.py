from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID


def round_half_up_ratio(amount_cents: int, numerator: int, denominator: int) -> int:
    if amount_cents < 0 or numerator < 0 or denominator <= 0:
        raise ValueError("fee inputs must be non-negative and the denominator must be positive")
    quotient = (Decimal(amount_cents) * Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    return int(quotient)


def allocate_by_weights(amount_cents: int, weights: list[tuple[UUID, int]]) -> dict[UUID, int]:
    """Largest-remainder allocation. Ties break by ascending UUID text."""
    if amount_cents < 0:
        raise ValueError("amount must be non-negative")
    total = sum(weight for _, weight in weights)
    if total != 1_000_000:
        raise ValueError("ownership weights must total 1000000")
    if any(weight <= 0 for _, weight in weights):
        raise ValueError("ownership weights must be positive")
    shares = {owner_id: (amount_cents * weight) // 1_000_000 for owner_id, weight in weights}
    leftover = amount_cents - sum(shares.values())
    ranked = sorted(
        weights,
        key=lambda item: (-((amount_cents * item[1]) % 1_000_000), str(item[0])),
    )
    for index in range(leftover):
        shares[ranked[index][0]] += 1
    return shares
