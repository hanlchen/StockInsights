"""Shared rate-limit detection for provider errors.

Both the single-ticker on-demand path (services/stock_service.py) and the
full-universe batch job (scripts/refresh_cache.py) need to tell "a provider
is throttling us right now" (worth retrying after a backoff) apart from
"this ticker is genuinely bad" (delisted, no data -- retrying won't help).
Kept in one place so the marker list can't drift between the two call
sites. Stooq's bot-detection HTML-block response is phrased to include
"rate limited" too (see providers/stooq_provider.py), so it's caught by the
same check.

ProviderChain (provider_chain.py) joins every provider's error into one
string when they *all* fail (" | ".join(errors)) -- so for a genuinely
delisted/unsupported ticker (e.g. hyphenated rights/units symbols like
"AIIA-U" that Stooq's ".us" symbol mapping doesn't recognize), the combined
message can contain BOTH yfinance's clear "no price history"/"no price"
signal AND Stooq's ambiguous "likely rate limited" text (Stooq labels *any*
non-CSV/HTML response that way -- it can't tell a real bot-block apart from
"this symbol format isn't recognized"). Naively matching on RATE_LIMIT_MARKERS
alone misreads that combination as rate-limited, and refresh_cache.py would
then retry it indefinitely at the 60s cap -- which is exactly why a handful
of tickers (AIIA-U, AIIA-R, ALUB-U observed in practice) never finish a run.
PERMANENT_FAILURE_MARKERS below take precedence: if any provider's failure
looks like a genuine "no data for this ticker" result, the whole combined
error is treated as a hard failure, not rate-limited, even if another
provider's text also happens to contain a rate-limit marker.
"""

RATE_LIMIT_MARKERS = ("too many requests", "rate limit")

# Matches the exact wording yfinance_provider.py raises when a ticker has no
# data at all (delisted, wrong symbol, etc.) -- not a throttling response.
# Kept narrow/literal (matching our own ProviderError text, not yfinance's
# internal log lines) so this can't accidentally swallow a real rate-limit.
PERMANENT_FAILURE_MARKERS = (
    "no price history",
    "returned no price",
    "no price data",
)


def looks_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    if any(marker in text for marker in PERMANENT_FAILURE_MARKERS):
        return False
    return any(marker in text for marker in RATE_LIMIT_MARKERS)
