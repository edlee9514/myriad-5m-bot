"""Trade logger — CSV logging and P&L tracking."""

import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import config

log = logging.getLogger(__name__)

FIELDNAMES = [
    "timestamp",
    "market_id",
    "slug",
    "asset",
    "side",
    "entry_price",
    "value",
    "shares",
    "tx_hash",
    "result",
    "pnl",
]


class TradeLogger:
    def __init__(self, log_file: str = config.TRADE_LOG_FILE):
        self.log_file = log_file
        self._ensure_file()
        self.trades: List[Dict] = self._load_trades()

    def _ensure_file(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()

    def _load_trades(self) -> List[Dict]:
        trades = []
        if not os.path.exists(self.log_file):
            return trades
        with open(self.log_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("pnl"):
                    row["pnl"] = float(row["pnl"])
                if row.get("value"):
                    row["value"] = float(row["value"])
                if row.get("entry_price"):
                    row["entry_price"] = float(row["entry_price"])
                trades.append(row)
        return trades

    def log_entry(
        self,
        market_id: int,
        slug: str,
        asset: str,
        side: str,
        entry_price: float,
        value: float,
        shares: float,
        tx_hash: str,
    ) -> dict:
        """Log a new trade entry. Result and PnL filled in later."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_id": str(market_id),
            "slug": slug,
            "asset": asset,
            "side": side,
            "entry_price": entry_price,
            "value": value,
            "shares": shares,
            "tx_hash": tx_hash,
            "result": "",
            "pnl": "",
        }
        self.trades.append(record)
        self._append_row(record)
        return record

    def update_result(self, market_id: int, result: str, pnl: float):
        """Update a trade record with its resolution result and PnL."""
        for trade in reversed(self.trades):
            if trade["market_id"] == str(market_id) and not trade.get("result"):
                trade["result"] = result
                trade["pnl"] = pnl
                self._rewrite_all()
                return
        log.warning(f"No pending trade found for market {market_id}")

    def daily_pnl(self) -> float:
        """Sum of PnL for today's trades."""
        today = datetime.now(timezone.utc).date()
        total = 0.0
        for t in self.trades:
            if not t.get("pnl") or t["pnl"] == "":
                continue
            ts = t.get("timestamp", "")
            try:
                trade_date = datetime.fromisoformat(ts).date()
            except (ValueError, TypeError):
                continue
            if trade_date == today:
                total += float(t["pnl"])
        return total

    def pending_trades(self) -> List[Dict]:
        """Trades that have been entered but not yet resolved."""
        return [t for t in self.trades if not t.get("result")]

    def recent_trades(self, n: int = 2016) -> List[Dict]:
        """Last n trades with results (for rolling win-rate check)."""
        resolved = [t for t in self.trades if t.get("result")]
        return resolved[-n:]

    def summary(self) -> str:
        """Print a summary of today's trading."""
        resolved = [t for t in self.trades if t.get("result")]
        if not resolved:
            return "No resolved trades yet."

        today = datetime.now(timezone.utc).date()
        today_trades = [
            t for t in resolved
            if datetime.fromisoformat(t["timestamp"]).date() == today
        ]

        total_pnl = sum(float(t["pnl"]) for t in today_trades if t.get("pnl"))
        wins = sum(1 for t in today_trades if t.get("result") == config.TARGET_OUTCOME)
        total = len(today_trades)
        win_rate = wins / total if total else 0

        return (
            f"Today: {total} trades | "
            f"Win rate: {win_rate:.1%} | "
            f"PnL: ${total_pnl:+.2f}"
        )

    def _append_row(self, record: dict):
        with open(self.log_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow(record)

    def _rewrite_all(self):
        with open(self.log_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(self.trades)
