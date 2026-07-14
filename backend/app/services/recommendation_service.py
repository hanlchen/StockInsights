"""
"AI Pick of the Day": once a day, after scripts/refresh_cache.py has
refreshed computed_metrics, this asks Claude to pick ONE ticker out of the
current momentum-screener candidate pool and explain why in plain language.

Design choices (see conversation/project decisions):
- Candidate pool = the existing quarterly momentum screener's top results
  (get_momentum_screener in market_service.py), not the full ~6,000-9,000
  ticker universe. Those tickers are already the ones showing sustained
  quarter-over-quarter strength, and reusing them means no extra
  computation here -- this module only adds a reasoning/selection step on
  top of numbers the batch job already produced.
- "Pure LLM judgment": the model chooses which candidate to highlight and
  writes the reasoning itself, rather than a fixed formula deciding the
  pick and the model only writing prose around it. This is intentionally
  more flexible than a deterministic score, at the cost of being less
  reproducible run to run -- documented here since it's a real tradeoff,
  not an oversight.
- Generation happens ONCE A DAY in the batch job (scripts/
  generate_recommendation.py), not live per page load: the API endpoint
  that serves this to the frontend (see api/routes/market.py) is a pure DB
  read of whatever this module last wrote, same pattern as movers/sectors/
  momentum. Keeps latency and Anthropic API cost bounded regardless of how
  many people load the dashboard.
- This is explicitly NOT financial advice -- the prompt asks the model to
  reason from the numbers it's given and to hedge appropriately, and the
  API response / frontend card both carry a disclaimer independent of
  whatever the model itself says.
"""

import json
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db.session import SessionLocal
from app.services import market_service, persistence

logger = logging.getLogger(__name__)

# How many candidates from the momentum screener to show the model. Kept
# small deliberately -- this is a single Claude call, not a batch scoring
# job, so the point is "give it a short, high-quality shortlist to reason
# over," not "have it re-rank the whole universe."
CANDIDATE_POOL_SIZE = 15

MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are a equity research assistant helping a personal-use \
stock screening app surface one "pick of the day" from a pre-filtered \
shortlist of momentum candidates.

You will be given a JSON list of candidate US-listed (NYSE/NASDAQ) stocks, \
each already confirmed to have positive momentum in every one of the last \
4 trailing quarters (that filtering already happened upstream -- you are \
choosing among stocks that already cleared that bar, not screening from \
scratch). Each candidate includes its momentum by quarter, market cap, \
sector, and trailing-twelve-months revenue where available.

Pick exactly ONE ticker from the provided list (never invent a ticker that \
isn't in the list). Then explain your pick in 3-5 sentences, citing the \
SPECIFIC numbers you were given (e.g. actual momentum percentages, revenue, \
market cap) rather than generic language. Also include a short, honest \
risk_note (1-2 sentences) naming a concrete reason this pick could be wrong \
-- e.g. valuation looks stretched, small-cap volatility, a single quarter \
skewing the average, sector-specific risk, no earnings/revenue data \
available, etc.

This is for informational/educational purposes only, not investment \
advice, and you should write with that framing in mind -- describe what \
the data shows, not what the person should do with their money.

Respond with ONLY a single JSON object, no other text, in exactly this \
shape:
{"ticker": "XXXX", "reasoning": "...", "risk_note": "..."}"""


def _build_candidates(top_n: int) -> list[dict]:
    screener = market_service.get_momentum_screener(top_n=top_n)
    return [
        {
            "ticker": e["ticker"],
            "company_name": e["company_name"],
            "sector": e["sector"],
            "market_cap": e["market_cap"],
            "market_cap_bucket": e["market_cap_bucket"],
            "revenue_ttm": e["revenue_ttm"],
            "momentum_9_to_12_months_ago_pct": round(e["momentum_m9_12"] * 100, 1),
            "momentum_6_to_9_months_ago_pct": round(e["momentum_m6_9"] * 100, 1),
            "momentum_3_to_6_months_ago_pct": round(e["momentum_m3_6"] * 100, 1),
            "momentum_last_3_months_pct": round(e["momentum_m0_3"] * 100, 1),
            "avg_quarterly_momentum_pct": round(e["avg_momentum"] * 100, 1),
        }
        for e in screener["results"]
    ]


def _call_claude(candidates: list[dict]) -> dict:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set -- cannot generate the AI pick of "
            "the day. Set it wherever scripts/generate_recommendation.py "
            "runs (see .env.example / DEPLOYMENT.md)."
        )

    # Imported lazily so the rest of the app (and its tests/py_compile)
    # doesn't hard-require the anthropic package if this feature is unused.
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_message = (
        "Candidates (JSON array):\n" + json.dumps(candidates, indent=2)
    )
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        # Model occasionally wraps JSON in prose/code fences despite
        # instructions -- fall back to extracting the first {...} block
        # before giving up, rather than failing the whole daily job.
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Could not parse a JSON object out of model output: {raw_text!r}")
        parsed = json.loads(raw_text[start:end + 1])

    if "ticker" not in parsed or "reasoning" not in parsed:
        raise ValueError(f"Model response missing required fields: {parsed!r}")

    valid_tickers = {c["ticker"] for c in candidates}
    if parsed["ticker"] not in valid_tickers:
        raise ValueError(
            f"Model picked {parsed['ticker']!r}, which isn't in the candidate "
            f"list it was given -- refusing to persist an unverified ticker."
        )

    return parsed


def generate_daily_recommendation(candidate_pool_size: int = CANDIDATE_POOL_SIZE) -> dict:
    """Builds today's candidate pool from the momentum screener, asks Claude
    to pick one and explain why, and persists the result. Raises on any
    failure (network, parsing, no candidates) -- the caller (scripts/
    generate_recommendation.py) decides whether that should fail the whole
    daily job or just be logged and skipped, since this feature is
    supplementary to the core dashboard/momentum data, not required for it."""
    candidates = _build_candidates(candidate_pool_size)
    if not candidates:
        raise RuntimeError(
            "No momentum-screener candidates available yet -- run "
            "scripts/refresh_cache.py first so computed_metrics is populated."
        )

    picked = _call_claude(candidates)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        persistence.upsert_daily_recommendation(
            db,
            date=today,
            ticker=picked["ticker"],
            reasoning=picked["reasoning"],
            risk_note=picked.get("risk_note"),
            candidate_count=len(candidates),
            model_used=settings.anthropic_model,
        )
        db.commit()

    logger.info("Generated daily recommendation for %s: %s", today, picked["ticker"])
    return {"date": today, **picked, "candidate_count": len(candidates)}
