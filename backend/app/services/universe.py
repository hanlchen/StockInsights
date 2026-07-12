"""
Full NYSE + NASDAQ common-stock universe (per project scope: US markets ==
NYSE and NASDAQ only). Source: Nasdaq Trader's free, no-key-required daily
symbol directory files, which cover every symbol listed on Nasdaq and every
"other listed" symbol (NYSE, NYSE American, Arca, Cboe, IEX, etc. -- we keep
only Exchange == 'N', i.e. NYSE proper, to match project scope):

    https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt
    https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt

These are pipe-delimited with a header row and a footer row starting with
"File Creation Time". Test issues and ETFs are excluded -- this app is about
common stocks, not funds or listing-infrastructure test symbols.

NOTE: this replaces the earlier S&P-500-only Wikipedia-scrape approach.
Full NYSE+NASDAQ is roughly 6,000-9,000 tickers vs. ~500 before -- see
scripts/refresh_cache.py for how that volume gets turned into computed
metrics (a scheduled batch job, not live-per-request).

I could not verify these URLs against the live internet while building this
(sandboxed environment, no outbound network access) -- if Nasdaq Trader has
moved/renamed these files, get_universe() will fall through to the bundled
fallback list and log a warning. Please confirm the first live run works
and let me know if the fetch fails so the URL/parsing can be fixed.
"""

import io
import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

DISK_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "universe_cache.json"
FALLBACK_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_fallback.json"
REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # daily -- Nasdaq Trader republishes these files daily

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-insights-app/0.1)"}

_memory_cache: list[dict] | None = None
_memory_cache_at: float = 0.0


def _fetch_pipe_delimited(url: str) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    # Last line is a "File Creation Time: ..." footer, not data.
    lines = [line for line in resp.text.splitlines() if not line.startswith("File Creation Time")]
    df = pd.read_csv(io.StringIO("\n".join(lines)), sep="|", dtype=str)
    return df


def _is_yes(value) -> bool:
    return str(value).strip().upper() == "Y"


def _clean_ticker(raw) -> str | None:
    """Yahoo uses '-' where these files use '.' for share classes (e.g.
    BRK.B -> BRK-B). Skip symbols with characters Yahoo won't recognize
    (warrants/units/rights typically carry '$', '+', '=', etc.).

    `raw` comes straight from a pandas row via `row.get(...)`, which can be
    `float('nan')` (not a string) for a blank cell -- pandas represents
    missing values that way even in an all-`dtype=str` read_csv when a row
    has fewer delimited fields than the header. Reject non-strings up front
    instead of calling .strip() on a float and crashing the whole fetch."""
    if not isinstance(raw, str) or not raw:
        return None
    raw = raw.strip()
    if not raw or any(ch in raw for ch in "$+=# "):
        return None
    return raw.replace(".", "-")


def _clean_str(raw) -> str:
    """Same non-string/NaN guard as `_clean_ticker`, for plain text fields
    (e.g. Exchange, Security Name) that get `.strip()`'d directly."""
    return raw.strip() if isinstance(raw, str) else ""


def _fetch_from_nasdaq_trader() -> list[dict]:
    records: list[dict] = []

    nasdaq_df = _fetch_pipe_delimited(NASDAQ_LISTED_URL)
    for _, row in nasdaq_df.iterrows():
        if _is_yes(row.get("Test Issue")) or _is_yes(row.get("ETF")):
            continue
        ticker = _clean_ticker(row.get("Symbol", ""))
        if not ticker:
            continue
        records.append({
            "ticker": ticker,
            "company_name": _clean_str(row.get("Security Name", "")) or ticker,
            "sector": None,  # Nasdaq Trader doesn't classify by sector; filled in on refresh
            "exchange": "NASDAQ",
        })

    other_df = _fetch_pipe_delimited(OTHER_LISTED_URL)
    for _, row in other_df.iterrows():
        if _clean_str(row.get("Exchange", "")).upper() != "N":  # NYSE only, per project scope
            continue
        if _is_yes(row.get("Test Issue")) or _is_yes(row.get("ETF")):
            continue
        ticker = _clean_ticker(row.get("ACT Symbol", ""))
        if not ticker:
            continue
        records.append({
            "ticker": ticker,
            "company_name": _clean_str(row.get("Security Name", "")) or ticker,
            "sector": None,
            "exchange": "NYSE",
        })

    if not records:
        raise ValueError("Parsed 0 rows from Nasdaq Trader symbol directory files")

    # De-dupe just in case a symbol shows up in both files.
    seen = set()
    deduped = []
    for r in records:
        if r["ticker"] in seen:
            continue
        seen.add(r["ticker"])
        deduped.append(r)
    return deduped


def _load_fallback() -> list[dict]:
    with open(FALLBACK_PATH) as f:
        records = json.load(f)
    logger.warning(
        "Using bundled ~70-ticker fallback list, NOT the full NYSE/NASDAQ universe -- "
        "Nasdaq Trader fetch failed or is unreachable."
    )
    return records


def _load_disk_cache() -> list[dict] | None:
    if not DISK_CACHE_PATH.exists():
        return None
    try:
        with open(DISK_CACHE_PATH) as f:
            payload = json.load(f)
        if time.time() - payload.get("cached_at", 0) > REFRESH_INTERVAL_SECONDS:
            return None
        return payload.get("records")
    except Exception:
        return None


def _write_disk_cache(records: list[dict]) -> None:
    try:
        DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DISK_CACHE_PATH, "w") as f:
            json.dump({"cached_at": time.time(), "records": records}, f)
    except Exception as exc:
        logger.warning("Failed to write universe disk cache: %s", exc)


def get_universe(force_refresh: bool = False) -> list[dict]:
    """Returns list of {ticker, company_name, sector, exchange} dicts for
    every non-test, non-ETF symbol on NASDAQ + NYSE. `sector` is None here
    (Nasdaq Trader doesn't provide it) -- it gets filled in per-ticker by
    the refresh job once fundamentals are fetched."""
    global _memory_cache, _memory_cache_at

    if not force_refresh and _memory_cache and (time.time() - _memory_cache_at) < 3600:
        return _memory_cache

    if not force_refresh:
        disk = _load_disk_cache()
        if disk:
            _memory_cache, _memory_cache_at = disk, time.time()
            return disk

    try:
        records = _fetch_from_nasdaq_trader()
        _write_disk_cache(records)
        logger.info("Refreshed NYSE+NASDAQ universe from Nasdaq Trader: %d tickers", len(records))
    except Exception as exc:
        logger.warning("Nasdaq Trader universe fetch failed (%s), using bundled fallback", exc)
        records = _load_fallback()

    _memory_cache, _memory_cache_at = records, time.time()
    return records


_lookup_cache: dict[str, dict] | None = None
_lookup_cache_source: list | None = None


def get_universe_lookup() -> dict[str, dict]:
    """ticker -> universe record, memoized against the current get_universe()
    list identity (so it stays in sync whenever the underlying cache
    refreshes, without rebuilding the dict on every call -- this gets
    looked up once per ticker during the full-universe refresh job, so
    rebuilding a ~7,000-entry dict thousands of times would be wasteful).

    This is the source of truth for a ticker's exchange (NYSE vs NASDAQ,
    per Nasdaq Trader's own classification) -- prefer it over whatever a
    live quote provider reports, since providers sometimes report a
    different/unmapped venue (e.g. BATS/Cboe) for the same instrument."""
    global _lookup_cache, _lookup_cache_source
    universe = get_universe()
    if _lookup_cache is None or _lookup_cache_source is not universe:
        _lookup_cache = {r["ticker"]: r for r in universe}
        _lookup_cache_source = universe
    return _lookup_cache


def search_universe(query: str, limit: int = 10) -> list[dict]:
    """Local, free ticker/company-name search -- no API call needed."""
    if not query:
        return []
    q = query.strip().upper()
    universe = get_universe()

    starts_with = [r for r in universe if r["ticker"].upper().startswith(q)]
    contains = [
        r for r in universe
        if r not in starts_with and (q in r["ticker"].upper() or q in r["company_name"].upper())
    ]
    return (starts_with + contains)[:limit]
