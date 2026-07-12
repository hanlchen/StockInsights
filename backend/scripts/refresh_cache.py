"""
Scheduled batch job that refreshes computed_metrics for the whole NYSE+NASDAQ
universe (~6,000-9,000 tickers). Run daily via cron/Task Scheduler:

    python -m scripts.refresh_cache
    python -m scripts.refresh_cache AAPL MSFT TSLA   # only these tickers (fast smoke test)
    python -m scripts.refresh_cache --resume         # full universe, but skip tickers already
                                                      # refreshed in the last RESUME_FRESHNESS_HOURS
                                                      # -- use this to pick back up after Ctrl+C'ing
                                                      # a run partway through, instead of re-hitting
                                                      # yfinance/Stooq for tickers already done
    python -m scripts.refresh_cache --sp500          # only the ~500 S&P 500 constituents instead of
                                                      # the full ~6,000-9,000 ticker universe -- an
                                                      # escape hatch for free/time-boxed schedulers
                                                      # (e.g. GitHub Actions' 6-hour job limit) where a
                                                      # full-universe run might not reliably finish in
                                                      # time. Movers/sectors/momentum/tickers would then
                                                      # only cover S&P 500 stocks, not the full exchange.

This is what makes /market/overview and /market/sectors possible at full-
exchange scale: those endpoints are now a pure DB read (see
services/market_service.py) instead of a live per-request fetch, because a
live fetch across the full universe on every request is exactly what caused
the "socket hang up" failures when this was ~500 S&P 500 tickers -- at 10-20x
that ticker count, live-per-request isn't viable at all. This script is the
only place that talks to yfinance/Stooq for market-wide data now.

Each ticker goes through stock_service.get_stock_metrics(), the same code
path the single-stock API endpoint uses -- so a ticker refreshed here and a
ticker looked up on-demand via /stock/{ticker} always compute metrics
identically and write to computed_metrics the same way (services/
persistence.py). Nothing is duplicated here except orchestration:
threading, progress reporting, and per-ticker error isolation.

Concurrency: a bounded thread pool (MAX_WORKERS) that processes tickers in
fixed-size batches with a pause between each batch, not one giant sequential
loop and not one continuous pool hammering the queue non-stop. Sequential
would take hours at this scale, and continuous unbroken parallelism against
an unofficial, rate-limit-prone API (yfinance/Yahoo) is a fast way to get
every request throttled at once even at a modest worker count -- it's the
*sustained* rate that trips providers' throttles, not the peak concurrency
of one batch. Batch+pause gets you a higher burst worker count (more
throughput per batch) while keeping the rate averaged over time low (thanks
to the pause), instead of trading one off against the other with a single
flat worker count.

Expect this to take a while on the full universe (thousands of tickers x
two network calls each, plus the BATCH_PAUSE_SECONDS pause after every
batch) -- run it as a background/cron job, not something you wait on
interactively.
"""

import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.providers.rate_limit import looks_rate_limited
from app.services import persistence, stock_service
from app.services.sp500 import get_sp500_tickers
from app.services.universe import get_universe

logger = logging.getLogger(__name__)

# How far back "--resume" looks to decide a ticker is already done. Short
# enough that a same-day resume after Ctrl+C doesn't skip stale data, long
# enough to cover realistic gaps between stopping and restarting a run.
RESUME_FRESHNESS_HOURS = 4

# Brought back down from 6 -- a full-universe run was observed taking over a
# day and still not finishing (see PERMANENT_FAILURE_MARKERS in
# app/providers/rate_limit.py for the other half of that bug: a handful of
# tickers were also stuck retrying forever, now fixed separately). Lower
# concurrency + more breathing room between batches reduces how hard/often
# yfinance and Stooq get hit, independent of that fix. The previous incident
# where 4 workers drove both yfinance AND our own Stooq fallback into a wall
# at the same time is the reason this stays conservative rather than going
# back up to 6+.
MAX_WORKERS = 3
PROGRESS_EVERY = 100

# Per-ticker jittered delay before each network call, applied inside every
# worker -- spreads requests within a batch out a bit further so a batch
# doesn't look like `workers` identical requests fired in the same instant.
# Widened (was 0.4-0.9s) alongside the MAX_WORKERS/BATCH_PAUSE_SECONDS
# changes above, same goal: ease off the sustained request rate.
REQUEST_DELAY_RANGE_SECONDS = (0.8, 1.5)

# Tickers are processed BATCH_SIZE at a time, with a real pause after each
# batch (except the last) -- this is what keeps the request rate "bursty
# with rest" instead of "constant hammering at a flat rate": MAX_WORKERS
# only bounds how many requests are in flight *within* a batch, it doesn't
# by itself create any downtime between batches. BATCH_SIZE lowered (was
# 150) and BATCH_PAUSE_SECONDS raised (was 8) so pauses land more often and
# last longer -- fewer requests between rests, more rest per batch.
BATCH_SIZE = 100
BATCH_PAUSE_SECONDS = 15

# Rate-limited tickers are retried (fewer workers, delay in between) rather
# than counted as permanent failures on the first pass -- a 429 almost always
# clears up given a backoff, unlike a genuinely delisted/bad ticker, which
# will just fail the same way again. Rate-limit detection (looks_rate_limited)
# is shared with stock_service.py's single-ticker retry so the marker list
# can't drift between the two call sites.
#
# Backoff grows round over round (3s, 6s, 10s, 20s, 30s, 45s, 60s) rather
# than jumping straight to a long delay -- most 429s clear within a few
# seconds so early rounds retry fast, but a throttle that's still active
# after 10s is more likely sustained, so later rounds wait longer. Once the
# schedule is exhausted, later rounds keep reusing the 60s cap rather than
# growing further or giving up -- a 429 is treated as always eventually
# recoverable, not a permanent failure, so retrying continues at the cap
# until every rate-limited ticker clears.
RETRY_BACKOFF_SCHEDULE_SECONDS = (3, 6, 10, 20, 30, 45, 60)
# Safety valve, not a real limit -- retries are meant to continue at the 60s
# cap indefinitely. This bound only guards against a genuine bug (e.g. a
# non-rate-limit failure misdetected as one) turning into a runaway process;
# it should never be hit in practice.
MAX_RETRY_ROUNDS = 50
RETRY_WORKERS = 2


def _retry_backoff_seconds(round_num: int) -> int:
    """round_num is 1-indexed (the round after the initial pass). Walks the
    schedule up to its last entry, then holds at that value (60s) for every
    later round instead of raising a KeyError/IndexError."""
    idx = min(round_num - 1, len(RETRY_BACKOFF_SCHEDULE_SECONDS) - 1)
    return RETRY_BACKOFF_SCHEDULE_SECONDS[idx]


def _refresh_one(ticker: str) -> tuple[str, Exception | None]:
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))
    try:
        stock_service.get_stock_metrics(ticker, use_cache=False)
        return ticker, None
    except Exception as exc:
        return ticker, exc


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _run_pass(
    tickers: list[str], workers: int, total: int, ok_so_far: int, failed_so_far: int, started: float
) -> tuple[int, list[str], list[str]]:
    """Runs one pass over `tickers`, in fixed-size batches (BATCH_SIZE) with
    a pause (BATCH_PAUSE_SECONDS) between each batch -- see the module
    docstring for why batch+pause, not just a worker-count cap, is what
    actually keeps the sustained request rate down. Returns
    (ok_count_this_pass, hard_failures, rate_limited_tickers) -- hard
    failures are reported to the user; rate-limited tickers get queued for
    another retry round instead. `ok_so_far`/`failed_so_far` are cumulative
    totals from prior rounds, used only so the progress line/ETA reflect the
    whole run instead of resetting each retry round."""
    ok_count = 0
    hard_failures: list[str] = []
    rate_limited: list[str] = []

    batches = _chunked(tickers, BATCH_SIZE)
    done_in_pass = 0
    for batch_num, batch in enumerate(batches):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_refresh_one, t): t for t in batch}
            for future in as_completed(futures):
                ticker, exc = future.result()
                done_in_pass += 1
                if exc is None:
                    ok_count += 1
                elif looks_rate_limited(exc):
                    rate_limited.append(ticker)
                else:
                    hard_failures.append(f"{ticker}: {exc}")

                done_overall = ok_so_far + failed_so_far + ok_count + len(hard_failures)
                if done_overall % PROGRESS_EVERY == 0 or done_in_pass == len(tickers):
                    elapsed = time.time() - started
                    rate = done_overall / elapsed if elapsed > 0 else 0
                    eta = (total - done_overall) / rate if rate > 0 else 0
                    print(
                        f"  {done_overall}/{total} done ({ok_so_far + ok_count} ok, "
                        f"{failed_so_far + len(hard_failures)} failed so far) -- "
                        f"{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining"
                    )

        is_last_batch = batch_num == len(batches) - 1
        if not is_last_batch:
            time.sleep(BATCH_PAUSE_SECONDS)

    return ok_count, hard_failures, rate_limited


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()  # safe to call even if the API server already has -- idempotent

    args = sys.argv[1:]
    resume = "--resume" in args
    sp500_only = "--sp500" in args
    explicit_tickers = [a for a in args if a not in ("--resume", "--sp500")]

    if explicit_tickers:
        tickers = explicit_tickers
    elif sp500_only:
        tickers = sorted(get_sp500_tickers())
        if not tickers:
            print(
                "--sp500: S&P 500 constituent list unavailable (Wikipedia fetch "
                "failed and no disk cache) -- nothing to refresh. Try again "
                "later or drop --sp500 to refresh the full universe instead."
            )
            return
        print(f"--sp500: restricting refresh to {len(tickers)} S&P 500 constituents, not the full universe")
    else:
        tickers = [r["ticker"] for r in get_universe()]

    # --resume only makes sense against a full-universe run -- explicit
    # ticker args are always processed regardless of freshness (that's the
    # existing "fast smoke test" behavior).
    if resume and not explicit_tickers:
        cutoff = datetime.utcnow() - timedelta(hours=RESUME_FRESHNESS_HOURS)
        with SessionLocal() as db:
            done = persistence.get_recently_computed_tickers(db, cutoff)
        before = len(tickers)
        tickers = [t for t in tickers if t not in done]
        print(
            f"--resume: skipping {before - len(tickers)} ticker(s) already refreshed "
            f"in the last {RESUME_FRESHNESS_HOURS}h ({len(tickers)} remaining)"
        )

    total = len(tickers)
    print(f"Refreshing {total} tickers with {MAX_WORKERS} concurrent workers...")

    ok = 0
    failures: list[str] = []
    started = time.time()

    pending = tickers
    workers = MAX_WORKERS
    round_num = 0
    while pending and round_num < MAX_RETRY_ROUNDS:
        if round_num > 0:
            backoff = _retry_backoff_seconds(round_num)
            print(
                f"\nRetry round {round_num}: {len(pending)} rate-limited "
                f"ticker(s), backing off {backoff}s and retrying with "
                f"{RETRY_WORKERS} worker(s)..."
            )
            time.sleep(backoff)
            workers = RETRY_WORKERS

        ok_count, hard_failures, rate_limited = _run_pass(pending, workers, total, ok, len(failures), started)
        ok += ok_count
        failures.extend(hard_failures)
        pending = rate_limited
        round_num += 1

    if pending:
        # Hit MAX_RETRY_ROUNDS -- the safety valve, not expected in normal
        # operation (see its comment). Reported separately from hard
        # failures since these are still rate-limited, not confirmed-bad
        # tickers -- rerunning `--resume` later will pick them back up.
        failures.extend(f"{t}: still rate-limited after {round_num} retries" for t in pending)

    failed = len(failures)
    print(f"\nDone: {ok} ok, {failed} failed out of {total} in {time.time() - started:.0f}s")
    if failures:
        print(f"First 20 of {len(failures)} failures:")
        for line in failures[:20]:
            print(f"  {line}")
    print(
        "computed_metrics is now up to date -- /market/overview and "
        "/market/sectors will read these rows on the next request."
    )


if __name__ == "__main__":
    main()
