# Myriad 5m Candle Bot — Strategy Document

## Market Structure

Myriad Markets runs "More Green or More Red?" prediction markets on 5-minute candle windows for **BTC, ETH, BNB, ZEC, and PENGU** (USDT pairs on Binance).

- Each market observes 5 consecutive 1-minute candles
- Resolves "More Green" if 3+ candles close >= open, "More Red" otherwise
- Markets are published ~8 minutes before the observation window opens
- **Betting locks when the window starts** — no in-play trading
- AMM-based pricing, seeded at 50/50 (0.50 each side, 500 liquidity)
- 1% buy fee, 0% sell fee
- Token: USD1 on BSC (chain ID 56)
- Resolution is automatic via Binance API

## Backtest Summary

Data: 90 days of 1-minute Binance candles (Dec 15 2025 — Mar 15 2026), ~25,900 five-minute windows per asset.

### Base Rates

| Asset | Green% | Red% | Red Edge vs 50/50 |
|-------|--------|------|-------------------|
| BTC   | 47.4%  | 52.6% | +2.6pp |
| ETH   | 49.9%  | 50.1% | +0.1pp |
| BNB   | 48.9%  | 51.1% | +1.1pp |
| ZEC   | 48.2%  | 51.8% | +1.8pp |
| **PENGU** | **43.6%** | **56.4%** | **+6.4pp** |

### Key Findings

1. **PENGU has a persistent, strong red bias (56.4% over 90 days).** This holds across all slices — time of day, day of week, MA regime, momentum, volatility. No feature modulates it meaningfully. The bias is consistent between the 30-day and 90-day samples.

2. **BTC/ETH show weak mean-reversion in close position.** When price closes near the lows of the prior 5-15 minutes, the next window is slightly more likely green (up to ~5pp in 30d, ~3pp in 90d). Effect halves with more data — likely regime-dependent noise.

3. **No momentum, streak, or MA signal provides a durable edge** on any asset after accounting for base rates and the 1% fee.

4. **Entry timing (partial scores mid-window) matches coin-flip combinatorics exactly** — candles within a window are independent. This is moot anyway since betting locks before the window.

5. **Low volatility periods are redder** across all assets (39-42% green in bottom quintile). This is correlated with the broader downtrend, not independently tradeable.

## Strategy

### Primary: PENGU "More Red" — Systematic

**Thesis:** PENGU's 56.4% red base rate vs the AMM's 50/50 starting price gives ~5.4% expected edge per trade after the 1% fee. This is a pure base-rate exploitation play.

**Rules:**
- Bet "More Red" on every PENGU 5-minute candle market
- Enter as soon as the market is published (~8 min before window)
- Only enter if the implied probability of "More Red" is <= 58% (price <= 0.58). Above that, the edge is consumed by the market price.
- Fixed position size per trade (e.g. 5 USD1)

**Expected performance (theoretical):**
- Win rate: ~56%
- Average payout per $1 risked at 0.50 entry: $1.00 win / $1.00 loss (minus 1% fee)
- Edge per trade: ~5.4%
- ~288 trades/day (one per 5-min window)
- Variance is high per trade but law of large numbers applies at scale

**Risks:**
- Base rate is measured over a 90-day window where PENGU trended down. If PENGU enters a sustained uptrend, the bias may flip.
- Liquidity is thin (500 USD1 seed) — large bets will move the price against us.
- Smart money or the market creator may adjust initial odds if they detect systematic betting.

### Secondary: BTC/ETH Conditional — Selective

**Thesis:** After the prior 5-15 minutes close near the range lows, the next window shows a slight green bias (~3-5pp). This is a weaker, less proven signal.

**Rules:**
- Monitor the prior 15-minute close position in range: (close - low) / (high - low)
- If close_pos < 0.15 (bottom quintile), bet "More Green"
- If close_pos > 0.85 (top quintile), bet "More Red"
- Only enter if implied probability is <= 55% for the target side
- Fixed position size, smaller than PENGU (e.g. 2 USD1) given lower confidence

**Status:** Experimental. The 30d→90d comparison showed this signal weakening. Use with caution and track live performance.

### Kill Switch Conditions

Do not trade when:
- Binance API is unreachable or returning errors
- The market's implied probability already exceeds our edge threshold
- We've hit a daily loss limit (e.g. 50 USD1)
- Manual override flag is set

## Architecture

```
myriad-5m-bot/
├── bot.py              # Main event loop
├── binance.py          # Binance websocket / REST for 1m candle data
├── myriad.py           # Myriad API client (market discovery, odds reading)
├── execution.py        # Trade execution via polkamarkets-js / Myriad API
├── strategy.py         # Strategy logic (entry signals, position sizing)
├── config.py           # Configuration (assets, thresholds, sizing)
├── backtest/
│   └── myriad_backtest.py
├── STRATEGY.md
└── README.md
```

### Bot Loop (every ~30 seconds)

1. **Discover** — Query Myriad API for upcoming candle markets (state=open, not yet locked)
2. **Evaluate** — For each market, check:
   - Is this a PENGU market? → Apply primary strategy
   - Is this BTC/ETH? → Fetch prior 15m candle data from Binance, compute close_pos, apply secondary strategy
   - Are current odds within our edge threshold?
3. **Execute** — If entry criteria met, place buy order for target outcome
4. **Log** — Record trade details, market ID, entry price, outcome (filled in after resolution)
5. **Monitor** — Track P&L, check kill switch conditions

### Execution

Myriad uses an on-chain AMM on BSC. Execution options:
- **polkamarkets-js SDK** — JavaScript SDK for direct smart contract interaction
- **Myriad REST API** — If they expose a trade endpoint (needs investigation)
- **Direct contract calls** — via web3.py / ethers.js to the market contract

The bot will need:
- A BSC wallet with USD1 balance
- Private key for signing transactions
- BSC RPC endpoint (public or Ankr/QuickNode)

## Monitoring & Evaluation

- Log every trade with: timestamp, market_id, asset, side, entry_price, outcome, pnl
- Daily summary: trades, win rate, total PnL, max drawdown
- Weekly review: compare live win rate to backtest expectations
- If live PENGU green rate exceeds 50% over a rolling 7-day window (2,016 markets), pause and reassess

## Open Questions

1. Can we get USD1 tokens efficiently? What's the on/off ramp?
2. Does the Myriad API expose trade/buy endpoints, or must we go through the smart contract?
3. What's the gas cost per trade on BSC? Need to factor into edge calculation.
4. Are there rate limits on market discovery API calls?
5. Will Myriad adjust initial odds if they detect systematic one-sided betting?
