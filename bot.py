"""Myriad 5m candle bot — main event loop.

Unconditionally bets 'More Red' on every PENGU 5-minute candle market.
Run with --dry-run to simulate without sending transactions.

Usage:
    python bot.py              # live trading (requires .env with PRIVATE_KEY)
    python bot.py --dry-run    # simulate trades, no on-chain transactions
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone

import config
import myriad
import strategy
from execution import Executor
from logger import TradeLogger

log = logging.getLogger("bot")

# Track which markets we've already acted on this session
_traded_markets = set()  # type: set
_running = True


def _calc_sleep() -> float:
    """Sleep until just before the next market is expected to publish.

    Markets are on 5-minute boundaries (00:00, 00:05, 00:10, ...) and
    publish ~8 minutes early. So the market for 00:10 publishes at ~00:02.

    We want to poll ~5 seconds after each expected publish time to catch
    new markets immediately while keeping API calls low (~12/hour).
    """
    now = datetime.now(timezone.utc)
    # Minutes into the current 5-min block
    mins_into_block = now.minute % 5
    secs_into_block = mins_into_block * 60 + now.second

    # Next 5-min boundary is in (300 - secs_into_block) seconds
    # Markets publish ~2 min after the previous 5-min boundary
    # (i.e., 8 min before the window they cover)
    # So publish times are at :02, :07, :12, :17, ... (roughly)
    # We target 5 seconds after each publish: :02:05, :07:05, etc.
    target_offset = 2 * 60 + 5  # 2min 5sec into each 5-min block

    if secs_into_block < target_offset:
        wait = target_offset - secs_into_block
    else:
        wait = (300 - secs_into_block) + target_offset

    # Clamp: minimum 10s (don't spam), maximum 300s (don't oversleep)
    wait = max(10, min(wait, 300))
    log.debug(f"Next poll in {wait:.0f}s")
    return wait


def _shutdown(signum, frame):
    global _running
    log.info("Shutdown signal received — finishing current cycle...")
    _running = False


def resolve_pending(trade_logger: TradeLogger, executor: 'Executor'):
    """Check if any pending trades have resolved, claim winnings, update results."""
    pending = trade_logger.pending_trades()
    if not pending:
        return

    for trade in pending:
        market_id = int(trade["market_id"])
        slug = trade["slug"]

        try:
            market = myriad.get_market_by_slug(slug)
        except Exception as e:
            log.debug(f"Cannot fetch market {slug}: {e}")
            continue

        resolved_id = market.get("resolvedOutcomeId", -1)
        if resolved_id == -1:
            continue  # not yet resolved

        result_title = "More Red" if resolved_id == 1 else "More Green"
        value = float(trade["value"])

        if result_title == config.TARGET_OUTCOME:
            # Win — claim winnings from the contract
            try:
                executor.claim_winnings(market_id)
            except Exception as e:
                log.error(f"Failed to claim market {market_id}: {e}")
            pnl = float(trade["shares"]) - value
        else:
            # Loss: lose the entire stake
            pnl = -value

        trade_logger.update_result(market_id, result_title, round(pnl, 4))
        log.info(
            f"Resolved market {market_id}: {result_title} → "
            f"PnL: ${pnl:+.4f}"
        )


def run_cycle(executor: Executor, trade_logger: TradeLogger):
    """Run one poll-decide-execute cycle."""
    # 1. Resolve any pending trades
    resolve_pending(trade_logger, executor)

    # 2. Find next open PENGU candle market
    market = myriad.find_next_pengu_market()
    if not market:
        log.debug("No open PENGU candle market found")
        return

    market_id = market["id"]

    # Skip if we already traded this market
    if market_id in _traded_markets:
        secs = myriad.seconds_until_lock(market)
        log.debug(f"Already traded market {market_id}, locks in {secs:.0f}s")
        return

    # 3. Evaluate strategy
    daily_pnl = trade_logger.daily_pnl()
    recent = trade_logger.recent_trades()
    decision = strategy.evaluate(market, daily_pnl, recent)

    if decision.action == "stop":
        log.warning(f"STOP: {decision.reason}")
        global _running
        _running = False
        return

    if decision.action == "skip":
        log.info(f"Skip market {market_id}: {decision.reason}")
        _traded_markets.add(market_id)
        return

    # 4. Check balance before executing
    bet_size = decision.bet_size
    balance = executor.get_usd1_balance()
    if balance < bet_size:
        log.warning(f"Insufficient USD1 balance: {balance:.4f} < {bet_size}")
        return

    # 5. Execute trade
    log.info(f">>> {decision.reason} | bet ${bet_size:.2f}")
    try:
        result = executor.buy(
            market_id=market_id,
            outcome_id=config.TARGET_OUTCOME_ID,
            value=bet_size,
        )
    except Exception as e:
        log.error(f"Trade execution failed: {e}")
        return

    # 6. Log the trade
    trade_logger.log_entry(
        market_id=market_id,
        slug=market["slug"],
        asset=config.TARGET_ASSET,
        side=config.TARGET_OUTCOME,
        entry_price=decision.price,
        value=bet_size,
        shares=result["shares_expected"],
        tx_hash=result["tx_hash"],
    )

    _traded_markets.add(market_id)
    log.info(
        f"Trade logged: {config.BET_SIZE_USD} USD1 → "
        f"{result['shares_expected']:.4f} shares | "
        f"tx: {result['tx_hash'][:16]}..."
    )


def main():
    parser = argparse.ArgumentParser(description="Myriad 5m candle bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate trades without sending on-chain transactions",
    )
    args = parser.parse_args()

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"

    # Log to both console and file
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    root.addHandler(console)

    file_handler = logging.FileHandler("bot.log")
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    root.addHandler(file_handler)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    log.info(f"=== Myriad 5m Candle Bot ({mode}) ===")
    log.info(f"Asset: {config.TARGET_ASSET} | Side: {config.TARGET_OUTCOME}")
    log.info(f"Bet size: {config.BET_SIZE_USD} USD1 | Max price: {config.MAX_ENTRY_PRICE}")
    log.info(f"Poll interval: {config.POLL_INTERVAL_SECONDS}s")

    executor = Executor(dry_run=args.dry_run)
    trade_logger = TradeLogger()

    if executor.address:
        log.info(f"Wallet: {executor.address}")
        if not args.dry_run:
            usd1 = executor.get_usd1_balance()
            bnb = executor.get_bnb_balance()
            log.info(f"Balances: {usd1:.2f} USD1 | {bnb:.6f} BNB")
    else:
        if not args.dry_run:
            log.error("No PRIVATE_KEY in .env — cannot trade live. Use --dry-run.")
            sys.exit(1)
        log.info("No wallet configured (dry-run mode)")

    log.info("Starting main loop...")

    while _running:
        try:
            run_cycle(executor, trade_logger)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)

        # Print periodic summary
        summary = trade_logger.summary()
        if "No resolved" not in summary:
            log.info(summary)

        time.sleep(_calc_sleep())

    log.info("Bot stopped.")
    log.info(trade_logger.summary())


if __name__ == "__main__":
    main()
