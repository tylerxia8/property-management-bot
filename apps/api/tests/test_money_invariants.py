from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from grok_bot.domain.money import allocate_by_weights, round_half_up_ratio


@settings(max_examples=100, deadline=None)
@given(
    amount=st.integers(min_value=0, max_value=50_000_000),
    first=st.integers(min_value=1, max_value=999_999),
)
def test_allocation_conserves_exact_cents(amount, first):
    owners = [UUID(int=1), UUID(int=2)]
    shares = allocate_by_weights(amount, [(owners[0], first), (owners[1], 1_000_000 - first)])
    assert sum(shares.values()) == amount
    assert all(value >= 0 for value in shares.values())


@settings(max_examples=100, deadline=None)
@given(
    amount=st.integers(min_value=0, max_value=50_000_000),
    numerator=st.integers(min_value=0, max_value=100),
    denominator=st.integers(min_value=1, max_value=100),
)
def test_half_up_ratio_stays_a_non_negative_cent(amount, numerator, denominator):
    result = round_half_up_ratio(amount, numerator, denominator)
    assert isinstance(result, int)
    assert result >= 0
