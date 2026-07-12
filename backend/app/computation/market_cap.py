"""
Market-cap bucketing. Per user decision: a simple 3-tier scheme, not the
finer-grained "mega/large/mid/small/micro/nano" convention some data vendors
use -- keeps the filter UI to three obvious choices.

    Large: >= $10B
    Mid:   $2B - $10B
    Small: < $2B
"""

LARGE_CAP_MIN = 10_000_000_000
MID_CAP_MIN = 2_000_000_000

VALID_BUCKETS = ("Large", "Mid", "Small")


def market_cap_bucket(market_cap: float | None) -> str | None:
    """Returns one of VALID_BUCKETS, or None if market_cap is unknown."""
    if market_cap is None:
        return None
    if market_cap >= LARGE_CAP_MIN:
        return "Large"
    if market_cap >= MID_CAP_MIN:
        return "Mid"
    return "Small"
