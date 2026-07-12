"""
S&P 500 constituent membership flag -- a supplementary annotation on the
full NYSE+NASDAQ ticker list (services/universe.py), not part of the core
universe pull. Fetched live from Wikipedia's "List of S&P 500 companies"
page, the standard free, no-key-required source for this (there's no free
official index-membership API).

Deliberately does NOT bundle a static fallback ticker list the way
universe.py does. S&P 500 membership changes periodically (quarterly
rebalances plus ad-hoc swaps), and a stale bundled list would silently
mislabel tickers as members/non-members with no way for a user to notice --
unlike the full ticker universe, where a stale-but-mostly-right list is
still useful, a wrong membership flag is actively misleading. If the live
fetch fails, this falls back to a same-shape disk cache (even if stale) and
only returns an empty set -- meaning "membership unknown for every ticker,
not confirmed non-member" -- if there's truly nothing cached yet. Callers
must treat an empty set as "data unavailable", not "no S&P 500 stocks
exist".

I could not verify this live in the sandboxed build environment (no
outbound network access) -- please confirm the first live run logs
"Refreshed S&P 500 constituent list" and not a fetch-failure warning. If
Wikipedia's page structure has changed, get_sp500_tickers() will fall
through to disk cache / empty set and log why.
"""

import io
import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DISK_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_cache.json"
REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # daily -- rebalances are infrequent, no need to hammer Wikipedia

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-insights-app/0.1)"}

# Real S&P 500 membership is ~500-503 tickers (occasionally a company has
# dual share classes counted once each). If a parse returns far fewer,
# Wikipedia's table structure likely changed -- treat it as a failure
# rather than silently serving a garbage subset.
MIN_PLAUSIBLE_COUNT = 400

_memory_cache: set[str] | None = None
_memory_cache_at: float = 0.0


def _fetch_from_wikipedia() -> set[str]:
    resp = requests.get(WIKIPEDIA_SP500_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = next((t for t in tables if "Symbol" in t.columns), None)
    if df is None:
        raise ValueError("No table with a 'Symbol' column found on the Wikipedia S&P 500 page")

    # Yahoo (our data providers) uses '-' where Wikipedia/exchange filings
    # use '.' for share classes (e.g. BRK.B -> BRK-B) -- same normalization
    # universe.py applies, so tickers compare equal against our stored data.
    tickers = {str(s).strip().upper().replace(".", "-") for s in df["Symbol"] if str(s).strip()}

    if len(tickers) < MIN_PLAUSIBLE_COUNT:
        raise ValueError(
            f"Parsed only {len(tickers)} tickers from Wikipedia S&P 500 page, "
            f"expected >= {MIN_PLAUSIBLE_COUNT} -- page structure may have changed"
        )
    return tickers


def _read_cache_file() -> set[str] | None:
    if not DISK_CACHE_PATH.exists():
        return None
    try:
        with open(DISK_CACHE_PATH) as f:
            return set(json.load(f).get("tickers", []))
    except Exception:
        return None


def _load_fresh_disk_cache() -> set[str] | None:
    if not DISK_CACHE_PATH.exists():
        return None
    try:
        with open(DISK_CACHE_PATH) as f:
            payload = json.load(f)
        if time.time() - payload.get("cached_at", 0) > REFRESH_INTERVAL_SECONDS:
            return None
        return set(payload.get("tickers", []))
    except Exception:
        return None


def _write_disk_cache(tickers: set[str]) -> None:
    try:
        DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DISK_CACHE_PATH, "w") as f:
            json.dump({"cached_at": time.time(), "tickers": sorted(tickers)}, f)
    except Exception as exc:
        logger.warning("Failed to write S&P 500 disk cache: %s", exc)


def get_sp500_tickers(force_refresh: bool = False) -> set[str]:
    """Returns the current set of S&P 500 constituent tickers (Yahoo-style
    symbols, e.g. BRK-B not BRK.B). An empty return means "couldn't confirm
    membership right now" -- callers must treat that as unknown/unavailable,
    never as "no ticker is an S&P 500 member"."""
    global _memory_cache, _memory_cache_at

    if not force_refresh and _memory_cache is not None and (time.time() - _memory_cache_at) < 3600:
        return _memory_cache

    if not force_refresh:
        fresh_disk = _load_fresh_disk_cache()
        if fresh_disk:
            _memory_cache, _memory_cache_at = fresh_disk, time.time()
            return fresh_disk

    try:
        tickers = _fetch_from_wikipedia()
        _write_disk_cache(tickers)
        logger.info("Refreshed S&P 500 constituent list from Wikipedia: %d tickers", len(tickers))
    except Exception as exc:
        stale = _read_cache_file()
        if stale:
            logger.warning("S&P 500 fetch failed (%s), using stale disk cache (%d tickers)", exc, len(stale))
            tickers = stale
        else:
            logger.warning(
                "S&P 500 fetch failed (%s) and no cache available -- "
                "S&P 500 membership flag will be unavailable this request", exc
            )
            tickers = set()

    _memory_cache, _memory_cache_at = tickers, time.time()
    return tickers
