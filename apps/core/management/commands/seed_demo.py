"""Seed a demo user, auth token, and a runnable demo strategy.

Idempotent: re-running updates in place. Prints the token and a ready-to-paste curl so a stranger
can clone, `docker compose up`, seed, and run the seeded backtest immediately.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from apps.strategies.models import Strategy

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-12345"  # noqa: S105 - intentional, documented demo credential
DEMO_STRATEGY_NAME = "RSI(2) mean reversion + SMA200 trend filter"

# A Connors-style mean-reversion strategy that trades frequently enough for a credible tearsheet
# (~38 round trips on SPY 2019-2023). Entry: RSI(2) < 15 AND close > SMA(200) (buy short-term dips
# only while the long-term trend is up). Exit: RSI(2) > 70 (exit once the bounce is overbought).
DEMO_RULES = {
    "entry": {
        "logic": "AND",
        "conditions": [
            {
                "left": {"type": "indicator", "name": "RSI", "params": {"window": 2}},
                "operator": "<",
                "right": {"type": "value", "value": 15},
            },
            {
                "left": {"type": "price", "field": "close"},
                "operator": ">",
                "right": {"type": "indicator", "name": "SMA", "params": {"window": 200}},
            },
        ],
    },
    "exit": {
        "logic": "OR",
        "conditions": [
            {
                "left": {"type": "indicator", "name": "RSI", "params": {"window": 2}},
                "operator": ">",
                "right": {"type": "value", "value": 70},
            }
        ],
    },
}


class Command(BaseCommand):
    help = "Seed a demo user, token, and demo strategy."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME, defaults={"email": "demo@example.com"}
        )
        user.set_password(DEMO_PASSWORD)
        user.save()

        token, _ = Token.objects.get_or_create(user=user)

        strategy, strat_created = Strategy.objects.get_or_create(
            owner=user,
            name=DEMO_STRATEGY_NAME,
            defaults={
                "universe": ["SPY"],
                "rules": DEMO_RULES,
                "position_sizing": {"type": "fixed_fraction", "fraction": 1.0},
            },
        )
        if not strat_created:
            strategy.universe = ["SPY"]
            strategy.rules = DEMO_RULES
            strategy.position_sizing = {"type": "fixed_fraction", "fraction": 1.0}
            strategy.save()

        self.stdout.write(self.style.SUCCESS("Demo seeded."))
        self.stdout.write(f"  user:      {DEMO_USERNAME} / {DEMO_PASSWORD}")
        self.stdout.write(f"  token:     {token.key}")
        self.stdout.write(f"  strategy:  #{strategy.id} {strategy.name!r} on {strategy.universe}")
        self.stdout.write("")
        self.stdout.write("Run the seeded backtest:")
        self.stdout.write(
            f"  curl -s -X POST http://localhost:8000/api/backtests/ \\\n"
            f'    -H "Authorization: Token {token.key}" \\\n'
            f'    -H "Content-Type: application/json" \\\n'
            f'    -d \'{{"strategy": {strategy.id}, "oos_split_date": "2022-01-01"}}\''
        )
