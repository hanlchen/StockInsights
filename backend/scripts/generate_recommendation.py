"""
Generates the "AI Pick of the Day" -- run once daily, AFTER
scripts/refresh_cache.py has refreshed computed_metrics (this reads from the
momentum screener, which is itself a DB read over computed_metrics, so
running this before a refresh would just re-analyze yesterday's numbers).

    python -m scripts.generate_recommendation

Deliberately best-effort / non-fatal: if ANTHROPIC_API_KEY isn't set, or the
Anthropic API call fails, or there aren't enough momentum candidates yet,
this logs a warning and exits 0 rather than failing the whole daily-refresh
workflow -- the AI pick is a supplementary feature, and a missing/failed pick
today shouldn't be treated the same as the core movers/momentum data failing
to refresh (see .github/workflows/daily-refresh.yml).
"""

import logging
import sys

from app.db.init_db import init_db
from app.services.recommendation_service import generate_daily_recommendation

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()  # safe/idempotent, same as refresh_cache.py

    try:
        result = generate_daily_recommendation()
    except Exception as exc:
        print(f"AI pick of the day: skipped -- {exc}")
        logger.warning("Daily recommendation generation failed: %s", exc)
        return

    print(f"AI pick of the day ({result['date']}): {result['ticker']}")
    print(f"  {result['reasoning']}")
    if result.get("risk_note"):
        print(f"  Risk: {result['risk_note']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
