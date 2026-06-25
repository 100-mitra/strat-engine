"""Pre-render the seeded strategy's backtest metrics + QuantStats tearsheet to static files.

Run at image-build time (before collectstatic), so the landing page can show the sample run's
headline metrics and link a one-click tearsheet without executing anything at request time. Uses the
engine directly on the committed CSV fixtures — no database, no network, fully deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand

from apps.core.data import get_data_source
from apps.core.management.commands.seed_demo import DEMO_RULES, DEMO_STRATEGY_NAME
from engine.metrics import generate_tearsheet_html
from engine.service import execute_backtest

# apps/core/static/sample
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "static" / "sample"

SNAPSHOT = {
    "name": DEMO_STRATEGY_NAME,
    "rules": DEMO_RULES,
    "universe": ["SPY"],
    "position_sizing": {"type": "fixed_fraction", "fraction": 1.0},
    "version": 1,
}
RUN_PARAMS = {
    "symbol": "SPY",
    "start": None,
    "end": None,
    "initial_capital": 100000.0,
    "fees_bps": 5,
    "slippage_bps": 5,
    "oos_split_date": "2022-01-01",
    "periods_per_year": 252,
}


class Command(BaseCommand):
    help = "Render the seeded strategy's sample metrics + tearsheet to static files."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=str(DEFAULT_DIR))

    def handle(self, *args, **options):
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        result = execute_backtest(get_data_source(), SNAPSHOT, RUN_PARAMS)

        payload = {
            "symbol": RUN_PARAMS["symbol"],
            "strategy": DEMO_STRATEGY_NAME,
            "oos_split_date": RUN_PARAMS["oos_split_date"],
            "fees_bps": RUN_PARAMS["fees_bps"],
            "slippage_bps": RUN_PARAMS["slippage_bps"],
            "metrics": result.metrics,
        }
        (out_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

        equity = pd.Series(
            [p["equity"] for p in result.equity_curve],
            index=pd.to_datetime([p["date"] for p in result.equity_curve]),
        )
        html = generate_tearsheet_html(
            equity.pct_change().dropna(),
            title=f"StratEngine — {RUN_PARAMS['symbol']} {DEMO_STRATEGY_NAME}",
            periods_per_year=RUN_PARAMS["periods_per_year"],
        )
        (out_dir / "tearsheet.html").write_text(html, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Rendered sample metrics + tearsheet to {out_dir}"))
