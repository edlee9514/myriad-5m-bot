"""Strategy engine — entry decisions and kill switches."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import config

log = logging.getLogger(__name__)


@dataclass
class Decision:
    action: str        # "buy", "skip", "stop"
    reason: str
    market_id: Optional[int] = None
    outcome_id: Optional[int] = None
    price: Optional[float] = None


def evaluate(market: Dict, daily_pnl: float, trade_history: List[Dict]) -> Decision:
    """Decide whether to buy, skip, or stop for this market.

    Args:
        market: Market dict from Myriad API.
        daily_pnl: Today's cumulative P&L in USD1.
        trade_history: Recent trade records for rolling win-rate check.

    Returns:
        Decision with action and reason.
    """
    market_id = market["id"]

    # ── Kill switch 1: daily loss limit ──────────────────────────────
    if daily_pnl <= config.DAILY_LOSS_LIMIT_USD:
        return Decision(
            action="stop",
            reason=f"Daily loss limit hit: ${daily_pnl:.2f} <= ${config.DAILY_LOSS_LIMIT_USD}",
        )

    # ── Kill switch 2: rolling green rate monitor ────────────────────
    if len(trade_history) >= config.ROLLING_WINDOW_SIZE:
        recent = trade_history[-config.ROLLING_WINDOW_SIZE:]
        green_wins = sum(1 for t in recent if t.get("result") == "More Green")
        green_rate = green_wins / len(recent)
        if green_rate > config.ROLLING_GREEN_PAUSE:
            return Decision(
                action="stop",
                reason=f"Rolling green rate {green_rate:.1%} > {config.ROLLING_GREEN_PAUSE:.0%} "
                       f"over last {config.ROLLING_WINDOW_SIZE} windows — regime shift?",
            )

    # ── Price check ──────────────────────────────────────────────────
    red_price = _get_outcome_price(market, config.TARGET_OUTCOME_ID)
    if red_price < 0:
        return Decision(action="skip", reason="Could not read 'More Red' price")

    if red_price > config.MAX_ENTRY_PRICE:
        return Decision(
            action="skip",
            reason=f"'More Red' price {red_price:.4f} > max {config.MAX_ENTRY_PRICE}",
            price=red_price,
        )

    # ── All clear → buy ──────────────────────────────────────────────
    return Decision(
        action="buy",
        reason=f"Entry signal: 'More Red' @ {red_price:.4f}",
        market_id=market_id,
        outcome_id=config.TARGET_OUTCOME_ID,
        price=red_price,
    )


def _get_outcome_price(market: dict, outcome_id: int) -> float:
    for outcome in market.get("outcomes", []):
        if outcome["id"] == outcome_id:
            return outcome["price"]
    return -1.0
