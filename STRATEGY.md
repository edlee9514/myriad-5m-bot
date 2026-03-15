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

---

## Backtest Results

Data: Multiple periods of 1-minute Binance candles, cross-validated for stability.

| Period | Dates | Context | Windows per asset |
|--------|-------|---------|-------------------|
| Bull 6m | Jan 1 — Jul 1, 2025 | PENGU rally period | ~52,100 |
| Bear 90d | Dec 15, 2025 — Mar 15, 2026 | Broad downturn | ~25,900 |
| Bear 30d | Feb 13 — Mar 15, 2026 | Recent subset | ~8,600 |

### 1. Base Rates

```
Asset     Green%   Red%    Red Edge vs 50/50    Verdict
────────────────────────────────────────────────────────
BTC       47.4%    52.6%   +2.6pp               Weak, regime-dependent
ETH       49.9%    50.1%   +0.1pp               Coin flip
BNB       48.9%    51.1%   +1.1pp               Marginal
ZEC       48.2%    51.8%   +1.8pp               Marginal
PENGU     43.6%    56.4%   +6.4pp               ██████ STRONG
```

PENGU's red bias is 2.5x stronger than the next asset (BTC). It is the only asset where the edge exceeds the 1% buy fee with comfortable margin.

### 2. Score Distribution (how decisive is the majority?)

Consistent across all assets and timeframes:

```
Score    Frequency    Meaning
──────────────────────────────────────────────
3-2      ~63%         Close call — majority wins by 1 candle
4-1      ~31%         Clear majority
5-0      ~6%          Sweep — all candles same colour
```

This matches binomial distribution expectations for p≈0.5 independent trials. Roughly 2/3 of all windows are decided by a single candle.

### 3. Momentum — Does the Previous Window Predict the Next?

```
                                30d                     90d
Condition               Green%    n            Green%    n         Stable?
──────────────────────────────────────────────────────────────────────────
After green window      49.1%     4,345        47.5%     12,289    ~flat
After red window        51.5%     4,293        47.3%     13,630    Unstable
After green+green       47.9%     2,133        46.9%     5,841     ~flat
After red+red           53.0%     2,080        46.4%     7,182     FLIPPED ✗

Verdict: No usable momentum or mean-reversion signal in window outcomes.
The 30d "after red+red → green 53%" was noise — it collapsed to 46.4% at 90d.
```

### 4. Score Momentum — Does a Decisive Window Predict the Next?

```
                                30d                     90d
Condition               Rate      n            Rate      n         Stable?
──────────────────────────────────────────────────────────────────────────
Prev 5-0 green → green  51.8%     226          49.1%     636       ~flat
Prev 5-0 red → red      47.8%     226          54.1%     918       Unstable
Prev 4-1 green → green  45.8%     1,281        45.9%     3,662     ✓ Stable
Prev 4-1 red → red      47.7%     1,241        53.3%     4,378     Unstable
Prev 3-2 green → green  50.4%     2,838        48.1%     7,990     ~flat
Prev 3-2 red → red      48.8%     2,825        52.2%     8,333     Unstable

Verdict: No consistent signal. The 90d red-continuation rates are likely
driven by the broader BTC downtrend, not a tradeable pattern.
```

### 5. Moving Average Regime

```
                                30d                     90d
Condition               Green%    n            Green%    n         Delta
──────────────────────────────────────────────────────────────────────────
Above MA20              47.7%     4,378        45.9%     13,104    -1.8pp
Below MA20              53.0%     4,260        49.0%     12,814    -4.0pp ✗
Above MA200 (bull)      48.7%     4,341        45.9%     13,117    -2.8pp
Below MA200 (bear)      51.9%     4,297        49.0%     12,801    -2.9pp
Full bull stack         47.1%     2,486        45.0%     7,540     -2.1pp
Full bear stack         54.0%     2,397        50.0%     7,227     -4.0pp ✗

Verdict: "Below MA → greener" looked promising at 30d (bear stack 54%) but
collapsed to 50.0% at 90d. Not stable enough to trade.
```

### 6. Volatility Regime

```
                                30d                     90d
Regime              Green%    n            Green%    n         Delta
──────────────────────────────────────────────────────────────────────────
Low volatility      50.5%     2,876        42.5%     8,636     -8.0pp ✗✗
Mid volatility      49.7%     2,876        50.0%     8,636     +0.3pp
High volatility     50.7%     2,876        49.7%     8,636     -1.0pp

Verdict: Low-vol looked neutral at 30d but is strongly red at 90d.
This is regime-dependent (low vol = grinding sell-offs), not a standalone signal.
```

### 7. Time of Day (UTC)

```
Hour   30d green%   90d green%   Delta    Note
──────────────────────────────────────────────────
06:00  43.9%        43.1%        -0.8pp   ◄ Consistently weakest hour
21:00  53.6%        47.4%        -6.2pp   Collapsed at 90d
16:00  52.8%        47.6%        -5.2pp   Collapsed at 90d
09:00  49.2%        47.7%        -1.5pp   Stable but no edge

Verdict: 06:00 UTC is consistently the reddest hour (Asian close / European
pre-open), but the effect is only ~3-4pp from base rate — not enough to trade
after fees. All other hourly "edges" from 30d disappeared at 90d.
```

### 8. Day of Week

```
Day    30d green%   90d green%   Delta    Note
──────────────────────────────────────────────────
Mon    52.6%        50.5%        -2.1pp   Stable-ish
Sat    49.0%        41.8%        -7.2pp   ◄ Weekend red bias emerged
Sun    50.4%        45.1%        -5.3pp   ◄ Weekend red bias emerged
Fri    49.8%        49.5%        -0.3pp   Stable

Verdict: Weekends show a red bias at 90d (~42-45% green) that was invisible
at 30d. Likely driven by thin weekend liquidity amplifying the downtrend.
Not a stable standalone signal — will flip in a bull market.
```

### 9. Momentum Lookback — Prior 5m / 10m / 15m

This is the most granular analysis. For each lookback period, we computed 5 features from the 1-minute candle data immediately preceding the target window, bucketed into quintiles, and checked green% for each bucket.

#### 9a. Net Return (prior period close vs open)

```
                        30d Q1          30d Q5          90d Q1          90d Q5
                      (most neg)      (most pos)      (most neg)      (most pos)
──────────────────────────────────────────────────────────────────────────────────
Prior 5m return       55.0% green     47.3% green     51.7% green     47.0% green
Prior 10m return      54.4%           46.4%           53.0%           47.7%
Prior 15m return      56.1%           47.4%           52.9%           47.8%

Direction consistent? ✓ Yes — negative prior returns → greener next window
Magnitude stable?     ✗ No — halved from 30d to 90d (8pp → 5pp spread)
```

Interpretation: mild mean-reversion. After price drops, next window is slightly more likely green. But the effect weakens with more data.

#### 9b. Close Position in Range — (close - low) / (high - low)

```
                        30d Q1          30d Q5          90d Q1          90d Q5
                      (near lows)     (near highs)    (near lows)     (near highs)
──────────────────────────────────────────────────────────────────────────────────
Prior 5m close pos    56.4% green     44.7% green     48.6% green     44.3% green
Prior 10m close pos   56.1%           45.4%           49.2%           44.0%
Prior 15m close pos   57.3%           45.2%           49.4%           44.3%

Direction consistent? ✓ Yes — closing near highs → redder next window
Magnitude stable?     ✗ Partially — top quintile stable (44-45%), bottom quintile weakened
```

This was the strongest signal in the dataset. The "closing near highs → next window red" side held at both 30d and 90d. The "closing near lows → green" side faded.

#### 9c. Range % (Volatility)

```
                        30d Q1          30d Q5          90d Q1          90d Q5
                      (tight)         (wide)          (tight)         (wide)
──────────────────────────────────────────────────────────────────────────────────
Prior 5m range        48.1% green     49.4% green     39.5% green     49.6% green
Prior 10m range       48.9%           49.9%           39.8%           50.2%
Prior 15m range       48.4%           50.2%           39.9%           50.0%

Direction consistent? ✓ Yes — low range → redder
Magnitude stable?     ✗ AMPLIFIED at 90d — 30d missed this entirely
```

Very tight prior ranges (low vol) predict red at 90d (39-40% green). This likely captures compression before continuation moves in a downtrend.

#### 9d. Volume Trend & Acceleration

```
Volume trend (recent/early ratio):    No consistent pattern at either timeframe.
Acceleration (5m vs 15m avg):         Weak negative = slightly greener. Not stable.

Verdict: Neither is tradeable.
```

### 10. Lookback Alignment — Do All 3 Periods Agree?

```
                        30d                     90d
Direction       Green%    n            Green%    n         Delta
──────────────────────────────────────────────────────────────────
All up          46.2%     2,693        44.9%     7,856     -1.3pp ✓
All down        54.5%     2,617        49.6%     7,872     -4.9pp ✗
Mixed           50.3%     3,328        47.7%     10,190    -2.6pp

Verdict: "All down → green" collapsed from 54.5% to 49.6% (flat).
"All up → red" held directionally but is only ~5pp and noisy.
```

### 11. PENGU Regime Test — Bull vs Bear

The critical question: is PENGU's red bias a downtrend artifact, or structural?

We tested PENGU during its Jan–Jul 2025 bull rally (the token rallied significantly) and compared against the recent bear period.

```
PENGU Base Rates Across Market Regimes
════════════════════════════════════════════════════════════════════
Period              Context          Green%   Red%    n         Edge*
────────────────────────────────────────────────────────────────────
Jan-Jul 2025        Bull rally       45.1%    54.9%   52,127    +3.9pp
Dec 2025-Mar 2026   Bear (90d)       43.6%    56.4%   25,918    +5.4pp
Feb-Mar 2026        Bear (30d)       42.5%    57.5%    8,638    +6.5pp
────────────────────────────────────────────────────────────────────
ALL DATA combined                    44.5%    55.5%   ~86,000   +4.5pp

* Edge = red% - 50% - 1% fee
```

```
PENGU green% by regime (visual)

              40%    42%    44%    46%    48%    50%
               ├──────┼──────┼──────┼──────┼──────┤
               │                                   │
 Bull 6m       │             ████████ 45.1%         │  ◄ STILL RED
               │                                   │
 Bear 90d      │        ████████ 43.6%              │
               │                                   │
 Bear 30d      │     ████████ 42.5%                 │
               │                                   │
               │  ALL PERIODS BELOW 46%            │
               │  Red bias persists in bull ✓       │
               └───────────────────────────────────┘
```

**The red bias held during the bull rally.** 45.1% green across 52,000+ windows — even when PENGU was ripping higher. The bias deepens in bear markets (42.5–43.6%) but never flips to green-majority.

This means PENGU's red bias is **structural to how the token trades at the 1-minute level**. Even during a sustained uptrend, more individual 1m candles close red than green. The price goes up via larger green candles, not more of them.

#### PENGU bull period — factor breakdown

Every factor was also tested during the bull period. The result is the same: nothing flips PENGU green.

```
PENGU factor analysis — Bull period (Jan-Jul 2025, n=52,127)
──────────────────────────────────────────────────────────────────
Feature                         Green% range     All red-biased?
──────────────────────────────────────────────────────────────────
Momentum (after green/red)      45.1% — 45.1%    ✓ Yes (identical)
Streaks (green+green/red+red)   44.4% — 45.2%    ✓ Yes
Score momentum                  44.3% — 45.2%    ✓ Yes
MA regime (bull/bear stack)     44.8% — 46.2%    ✓ Yes
Volatility regime               44.2% — 45.8%    ✓ Yes
Time of day                     43.4% — 47.1%    ✓ Yes (every hour < 48%)
Day of week                     44.2% — 45.9%    ✓ Yes (every day < 46%)
Prior 5m net return             44.2% — 46.5%    ✓ Yes
Prior 15m close position        43.9% — 46.2%    ✓ Yes
Lookback alignment              44.3% — 46.1%    ✓ Yes
──────────────────────────────────────────────────────────────────

Not a single factor, in any quintile, in any regime, produces
a PENGU green rate above 47.1%.
```

### 12. PENGU Summary — Why Nothing Else Matters

Across **all three test periods** (bull 6m, bear 90d, bear 30d) and **every factor tested**, PENGU's green rate ranges from ~39% to ~47%, but never reaches majority-green. The red bias is:

- **Persistent** — holds across 12+ months of data
- **Regime-independent** — present in both bull rallies and bear sell-offs
- **Unconditional** — no feature modulates it meaningfully
- **Structural** — likely caused by PENGU's microstructure (low-liquidity alt with wider spreads, more doji/red closes even during upward moves)

---

## Chosen Strategy

### Decision Framework

```
                          Edge after 1% fee
                    ◄─────────────────────────────►
                    -2%     0%     +2%     +4%     +6%

ETH (50/50)          ────●────                         ✗ No trade
BNB (+1.1pp)              ──●──                        ✗ Below fee
ZEC (+1.8pp)               ──●──                       ✗ Marginal
BTC (+2.6pp)                 ──●──                     ? Marginal
PENGU (+6.4pp)                        ────────●──────  ✓ TRADE
                                              ▲
                                        Clear edge
                                        after fees
```

### The Strategy: Bet "More Red" on PENGU — Every Window

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ENTRY SIGNAL:   PENGU candle market exists & is open          │
│   SIDE:           Always "More Red"                             │
│   POSITION SIZE:  Fixed (e.g. 5 USD1 per trade)                 │
│   MAX ENTRY PRICE: 0.58 (implied prob ≤ 58%)                   │
│                                                                 │
│   That's it. No indicators. No conditions. Pure base rate.      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

This is a **systematic, unconditional strategy**. We bet the same side, same size, every window. The edge comes from the market's structural mispricing (50/50 AMM seed) against a biased underlying (54.9–56.4% red depending on regime).

### Why Unconditional?

We tested every conditioning variable. None materially improves on the base rate:

```
            PENGU green% by condition (90d, n≈25,900)

     39%  40%  41%  42%  43%  44%  45%  46%  47%
      ├────┼────┼────┼────┼────┼────┼────┼────┤
      │                                        │
 Base │              ████████ 43.6%             │  ← bet against this
      │                                        │
 Mon  │                 ████████ 44.5%          │
 Sat  │         ████████ 42.3%                  │
 06h  │    ████████ 38.8%                       │
 16h  │                    ████████ 46.2%       │
      │                                        │
 Bull │               ████████ 44.3%            │
 Bear │               ████████ 44.3%            │
      │                                        │
 LowV │          ████████ 41.5%                 │
 HiV  │                  ████████ 45.4%         │
      │                                        │
      │    ALL BARS ARE BELOW 47%               │
      │    Every slice is red-biased ✓          │
      └────────────────────────────────────────┘
```

Adding conditions would only reduce trade frequency without meaningfully improving win rate. The Myriad market resets to 50/50 every window regardless, so there's no information in current odds to time entries.

### Trade Flow

```
Every 30 seconds:

    ┌──────────────┐
    │ Poll Myriad  │──── No PENGU market open? ──→ Wait
    │ API for open │
    │ candle mkts  │
    └──────┬───────┘
           │
           ▼ PENGU market found
    ┌──────────────┐
    │ Check price  │──── "More Red" price > 0.58? ──→ Skip (edge consumed)
    │ of "More Red"│
    └──────┬───────┘
           │
           ▼ Price ≤ 0.58
    ┌──────────────┐
    │ Check kill   │──── Daily loss limit hit? ──→ Stop for today
    │ switches     │──── Binance API down? ──→ Skip
    └──────┬───────┘
           │
           ▼ All clear
    ┌──────────────┐
    │ Buy "More    │
    │ Red" shares  │──→ Log trade (market_id, price, timestamp)
    │ (5 USD1)     │
    └──────┬───────┘
           │
           ▼ Wait for resolution (~13 min)
    ┌──────────────┐
    │ Check result │──→ Log outcome, update P&L
    └──────────────┘
```

### Expected Performance

```
                          Bear regime          Bull regime
                          (win rate 56.4%)     (win rate 54.9%)
─────────────────────────────────────────────────────────────────
Entry price:              0.50                 0.50
Buy fee:                  1%                   1%
Payout on win:            $0.99                $0.99
Loss on loss:             -$0.50               -$0.50

Per $1 wagered:
  E[win]                  0.564 × $0.49        0.549 × $0.49
                          = $0.276             = $0.269
  E[loss]                 0.436 × -$0.50       0.451 × -$0.50
                          = -$0.218            = -$0.226
  E[net]                  +$0.058 (5.8%)       +$0.044 (4.4%)

Per day (288 windows × $5 per trade = $1,440 wagered):
  Expected daily P&L:     +$84                 +$63
  Std dev per trade:      ~$2.50               ~$2.50
  Daily std dev:          ~$42                 ~$42
  Sharpe (daily):         ~2.0                 ~1.5

Per month (30 days):
  Expected monthly P&L:   +$2,520              +$1,890
  Monthly std dev:        ~$230                ~$230
```

The bull regime is the conservative case. Even there, the edge is +4.4% per dollar wagered — well above zero. The strategy is profitable in both regimes.

Note: These assume we can enter at 0.50 every trade (no price impact from prior bettors or our own volume). If the market moves to 0.52-0.55 before we enter, the edge compresses but remains positive up to ~0.56 in bull, ~0.58 in bear.

### Risk Management

```
┌─────────────────────────────────────────────────────────────────┐
│ KILL SWITCHES                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ 1. DAILY LOSS LIMIT         -50 USD1 → stop trading for 24h    │
│                                                                 │
│ 2. ROLLING WIN RATE         If green rate > 50% over trailing   │
│    MONITOR                  2,016 windows (7 days) → pause      │
│                             and reassess regime                 │
│                                                                 │
│ 3. PRICE GUARD              Never buy "More Red" above 0.58     │
│                             (edge must exceed fee + spread)     │
│                                                                 │
│ 4. BINANCE HEALTH           Skip if Binance API errors or      │
│                             PENGUUSDT is suspended              │
│                                                                 │
│ 5. MANUAL OVERRIDE          Config flag to pause bot            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### What Could Go Wrong

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PENGU enters sustained uptrend, red bias flips | Medium | Fatal — strategy reverses to negative EV | Rolling win rate monitor, auto-pause at 50% green |
| Myriad adjusts initial odds away from 50/50 | Low-Medium | Reduces or eliminates edge | Price guard at 0.58; if systematically priced >0.55, reassess |
| No liquidity / no markets created for PENGU | Medium | Zero trades, zero P&L | Fall back to BTC/ETH secondary strategy |
| BSC gas costs eat the edge | Low | Reduces edge by fixed cost per trade | BSC gas is typically <$0.05; monitor and size positions to maintain edge |
| Smart contract risk / USD1 depeg | Low | Loss of capital | Limit total capital deployed |

---

## Secondary Strategy: BTC/ETH Close-Position Mean Reversion

**Status: Experimental — disabled by default**

The one signal that showed directional consistency across both 30d and 90d:

```
Prior 15m close position in range     30d green%     90d green%
─────────────────────────────────────────────────────────────────
Q1 (closing near lows, < 0.18)        57.3%          49.4%
Q5 (closing near highs, > 0.83)       45.2%          44.3%

The "near highs → red" side held (44-45% green in both periods).
The "near lows → green" side faded (57% → 49%).
```

Not recommended for live trading until validated with more data. If enabled:
- Only trade BTC/ETH when prior 15m close_pos > 0.85 → bet "More Red"
- Smaller size (2 USD1), wider price guard (≤ 0.55)
- Track separately from primary strategy

---

## Architecture

```
myriad-5m-bot/
├── bot.py              # Main event loop
├── binance.py          # Binance REST client for 1m candle data
├── myriad.py           # Myriad API client (market discovery, odds reading)
├── execution.py        # Trade execution via polkamarkets-js / contract calls
├── strategy.py         # Strategy logic (entry signals, position sizing)
├── config.py           # Configuration (assets, thresholds, sizing)
├── logger.py           # Trade logging and P&L tracking
├── backtest/
│   └── myriad_backtest.py
├── STRATEGY.md
└── README.md
```

### Bot Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                        MAIN LOOP (30s)                          │
│                                                                 │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────────┐  │
│  │ Myriad  │──▶│ Strategy │──▶│ Execute  │──▶│   Logger    │  │
│  │ Client  │   │ Engine   │   │          │   │             │  │
│  │         │   │          │   │          │   │ - trades.csv│  │
│  │ - find  │   │ - PENGU  │   │ - BSC tx │   │ - daily P&L │  │
│  │   open  │   │   red?   │   │ - confirm│   │ - win rate  │  │
│  │   mkts  │   │ - price  │   │          │   │             │  │
│  │ - read  │   │   check  │   │          │   │             │  │
│  │   odds  │   │ - kill   │   │          │   │             │  │
│  │         │   │   switch │   │          │   │             │  │
│  └─────────┘   └──────────┘   └──────────┘   └─────────────┘  │
│       ▲                                                         │
│       │        ┌──────────┐                                     │
│       └────────│ Binance  │  (secondary strategy only)          │
│                │ Client   │                                     │
│                └──────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Execution

Myriad uses an on-chain AMM on BSC. Execution options:
- **polkamarkets-js SDK** — JavaScript SDK for direct smart contract interaction
- **Myriad REST API** — If they expose a trade endpoint (needs investigation)
- **Direct contract calls** — via web3.py / ethers.js to the market contract

Requirements:
- BSC wallet with USD1 balance
- Private key for signing transactions (stored in .env, never committed)
- BSC RPC endpoint (public or Ankr/QuickNode)

---

## Monitoring & Evaluation

- Log every trade: timestamp, market_id, asset, side, entry_price, outcome, pnl
- Daily summary: trades, win rate, total PnL, max drawdown
- Weekly review: compare live win rate to backtest expectations
- If live PENGU green rate exceeds 50% over a rolling 7-day window (2,016 markets), pause and reassess

---

## Open Questions

1. Can we get USD1 tokens efficiently? What's the on/off ramp?
2. Does the Myriad API expose trade/buy endpoints, or must we go through the smart contract?
3. What's the gas cost per trade on BSC? Need to factor into edge calculation.
4. Are there rate limits on market discovery API calls?
5. Will Myriad adjust initial odds if they detect systematic one-sided betting?
