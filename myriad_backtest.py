"""
Myriad Markets — "More Green or More Red?" Backtest
====================================================
Pulls 1m candles from Binance and analyses patterns in
5-minute windows (5 candles each, majority colour wins).

Supports: BTC, ETH, BNB, ZEC (Zcash), PENGU

Usage:
    pip install requests pandas numpy openpyxl

    python myriad_backtest.py                           # BTC, last 30 days
    python myriad_backtest.py --symbol ETH --days 90
    python myriad_backtest.py --symbol PENGU --days 30
    python myriad_backtest.py --all --days 30           # run all assets
"""

import argparse
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# ── Binance public API — no key needed ────────────────────────────
BINANCE_URL = "https://api.binance.com/api/v3/klines"
INTERVAL    = "1m"
MAX_PER_REQ = 1000   # Binance limit per call

# Myriad-supported assets → Binance pair mapping
ASSET_MAP = {
    "BTC":   "BTCUSDT",
    "ETH":   "ETHUSDT",
    "BNB":   "BNBUSDT",
    "ZEC":   "ZECUSDT",
    "PENGU": "PENGUUSDT",
}
ALL_ASSETS = list(ASSET_MAP.keys())


# ─────────────────────────────────────────────────────────────────
#  1. DATA FETCH
# ─────────────────────────────────────────────────────────────────

def fetch_1m_candles(days: int, symbol: str = "BTCUSDT",
                     start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Fetch 1m candles from Binance. Uses start_date/end_date if provided, else last N days."""
    if start_date:
        start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc).timestamp() * 1000)
        if end_date:
            end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp() * 1000)
        else:
            end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        days = (end_ms - start_ms) // (24 * 3600 * 1000)
    else:
        end_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - days * 24 * 3600 * 1000

    all_rows = []
    current  = start_ms

    label = f"{start_date or ''} → {end_date or 'now'}".strip(" →") or f"last {days}d"
    print(f"Fetching {symbol} 1m candles ({label})...")
    while current < end_ms:
        resp = requests.get(BINANCE_URL, params={
            "symbol":    symbol,
            "interval":  INTERVAL,
            "startTime": current,
            "endTime":   end_ms,
            "limit":     MAX_PER_REQ,
        }, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        current = rows[-1][0] + 60_000   # next minute
        print(f"  {len(all_rows):,} candles so far...", end="\r")
        time.sleep(0.1)

    print(f"\nFetched {len(all_rows):,} 1m candles total.")

    df = pd.DataFrame(all_rows, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_vol","trades","taker_buy_base",
        "taker_buy_quote","ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index()
    return df[["open","high","low","close","volume"]]


# ─────────────────────────────────────────────────────────────────
#  2. BUILD 5-MINUTE WINDOWS
# ─────────────────────────────────────────────────────────────────

def classify_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Add colour column and snap each candle to its 5-min window."""
    df = df.copy()
    # Green = close > open, Red = close <= open (doji counts as red)
    df["green"] = (df["close"] > df["open"]).astype(int)
    df["red"]   = (df["close"] <= df["open"]).astype(int)
    # Clock-aligned 5-min window label (floor to 5m)
    df["window"] = df.index.floor("5min")
    return df


def build_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1m candles into 5m window summary rows."""
    grp = df.groupby("window")
    w = pd.DataFrame({
        "n_candles":   grp["green"].count(),
        "n_green":     grp["green"].sum(),
        "n_red":       grp["red"].sum(),
        "open":        grp["open"].first(),
        "close":       grp["close"].last(),
        "high":        grp["high"].max(),
        "low":         grp["low"].min(),
        "volume":      grp["volume"].sum(),
    })
    # Only keep complete 5-candle windows
    w = w[w["n_candles"] == 5].copy()
    w["result"]    = np.where(w["n_green"] > w["n_red"], "green", "red")
    w["score"]     = w[["n_green","n_red"]].max(axis=1).astype(str) + "-" + \
                     w[["n_green","n_red"]].min(axis=1).astype(str)
    w["net_move"]  = w["close"] - w["open"]
    w["net_pct"]   = w["net_move"] / w["open"] * 100
    w["hour"]      = w.index.hour
    w["day_of_week"] = w.index.dayofweek   # 0=Mon, 6=Sun
    return w


# ─────────────────────────────────────────────────────────────────
#  3. FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────

def add_features(w: pd.DataFrame, df1m: pd.DataFrame) -> pd.DataFrame:
    """Add MA relationships, momentum, and lag features."""
    w = w.copy()

    # ── Previous window outcome (lag 1, 2, 3) ────────────────────
    w["prev1"] = w["result"].shift(1)
    w["prev2"] = w["result"].shift(2)
    w["prev3"] = w["result"].shift(3)

    # ── Score of previous window ──────────────────────────────────
    w["prev_n_green"] = w["n_green"].shift(1)
    w["prev_n_red"]   = w["n_red"].shift(1)

    # ── Rolling win rates (last 12 windows = 1h, last 48 = 4h) ───
    green_bin = (w["result"] == "green").astype(int)
    w["green_rate_1h"]  = green_bin.shift(1).rolling(12, min_periods=6).mean()
    w["green_rate_4h"]  = green_bin.shift(1).rolling(48, min_periods=24).mean()

    # ── Moving averages on 1m close (computed on 1m df) ──────────
    df1m = df1m.copy()
    df1m["ma20"]  = df1m["close"].rolling(20).mean()
    df1m["ma50"]  = df1m["close"].rolling(50).mean()
    df1m["ma200"] = df1m["close"].rolling(200).mean()

    # Snapshot MA values at the start of each 5m window
    # (last 1m close before window opens = window open time - 1 tick)
    for ma, col in [("ma20","ma20"), ("ma50","ma50"), ("ma200","ma200")]:
        snapped = df1m[ma].resample("5min").last().shift(1)  # value just before window
        w[col] = snapped.reindex(w.index)

    # Price vs MA at window open
    w["above_ma20"]  = (w["open"] > w["ma20"]).astype(float)
    w["above_ma50"]  = (w["open"] > w["ma50"]).astype(float)
    w["above_ma200"] = (w["open"] > w["ma200"]).astype(float)

    # Distance from MA as % (momentum proxy)
    w["dist_ma20_pct"]  = (w["open"] - w["ma20"])  / w["ma20"]  * 100
    w["dist_ma200_pct"] = (w["open"] - w["ma200"]) / w["ma200"] * 100

    # ── Volatility (ATR proxy: rolling 5m high-low range) ─────────
    w["range_pct"] = (w["high"] - w["low"]) / w["open"] * 100
    w["vol_regime"] = pd.qcut(
        w["range_pct"].rolling(48, min_periods=12).mean(),
        q=3, labels=["low_vol","mid_vol","high_vol"]
    )

    # ── Previous 5m net move ──────────────────────────────────────
    w["prev_net_pct"] = w["net_pct"].shift(1)

    # ── Prior-period momentum (5m / 10m / 15m lookback) ─────────
    for mins in [5, 10, 15]:
        n_windows = mins // 5  # how many prior 5m windows to look back
        pfx = f"prior{mins}m"

        # Net return over lookback
        w[f"{pfx}_ret"] = (w["close"].shift(1) - w["open"].shift(n_windows)) \
                          / w["open"].shift(n_windows) * 100

        # Green candle count in lookback (from 1m data)
        m1_green = df1m["close"] > df1m["open"]
        green_roll = m1_green.astype(int).rolling(mins).sum()
        snapped_green = green_roll.resample("5min").last().shift(1)
        w[f"{pfx}_n_green"] = snapped_green.reindex(w.index)

        # Range % (high-low / open) over lookback
        roll_high = df1m["high"].rolling(mins).max()
        roll_low  = df1m["low"].rolling(mins).min()
        roll_open = df1m["open"].shift(mins - 1)
        range_pct = (roll_high - roll_low) / roll_open * 100
        snapped_range = range_pct.resample("5min").last().shift(1)
        w[f"{pfx}_range"] = snapped_range.reindex(w.index)

        # Close position in range: (close - low) / (high - low)
        close_pos = (df1m["close"] - roll_low) / (roll_high - roll_low)
        snapped_pos = close_pos.resample("5min").last().shift(1)
        w[f"{pfx}_close_pos"] = snapped_pos.reindex(w.index)

        # Volume trend: ratio of last-half volume to first-half volume
        vol_recent = df1m["volume"].rolling(mins // 2 or 1).sum()
        vol_full   = df1m["volume"].rolling(mins).sum()
        vol_ratio  = vol_recent / (vol_full - vol_recent + 1e-9)
        snapped_vol = vol_ratio.resample("5min").last().shift(1)
        w[f"{pfx}_vol_trend"] = snapped_vol.reindex(w.index)

    # Acceleration: is 5m move stronger than 15m average?
    w["accel_5v15"] = w["prior5m_ret"] - (w["prior15m_ret"] / 3)

    # Alignment: do all 3 lookbacks agree on direction?
    w["lookback_align"] = (
        (np.sign(w["prior5m_ret"]) == np.sign(w["prior10m_ret"])) &
        (np.sign(w["prior10m_ret"]) == np.sign(w["prior15m_ret"]))
    ).astype(int)
    w["lookback_dir"] = np.where(
        w["lookback_align"] == 1,
        np.where(w["prior5m_ret"] > 0, "all_up", "all_down"),
        "mixed"
    )

    return w.dropna(subset=["prev1","above_ma20","above_ma200"])


# ─────────────────────────────────────────────────────────────────
#  4. ANALYSIS
# ─────────────────────────────────────────────────────────────────

def hr(label="", width=70):
    print(f"\n{'─'*width}")
    if label:
        print(f"  {label}")
        print(f"{'─'*width}")


def pct(n, d):
    return f"{n/d*100:.1f}%" if d else "n/a"


def analyse(w: pd.DataFrame, verbose: bool = False):
    total = len(w)
    n_green = (w["result"] == "green").sum()
    n_red   = (w["result"] == "red").sum()

    hr("BASE RATES")
    print(f"  Total 5m windows : {total:,}")
    print(f"  Green majority   : {n_green:,}  ({pct(n_green, total)})")
    print(f"  Red majority     : {n_red:,}  ({pct(n_red, total)})")

    hr("SCORE DISTRIBUTION  (how decisive is the majority?)")
    score_counts = w["score"].value_counts().sort_index()
    for score, cnt in score_counts.items():
        bar = "█" * int(cnt / total * 60)
        print(f"  {score}  {cnt:6,}  {pct(cnt, total):6}  {bar}")

    hr("MOMENTUM — does the previous window predict the next?")
    for prev in ["green", "red"]:
        sub = w[w["prev1"] == prev]
        ng  = (sub["result"] == "green").sum()
        print(f"  After {prev:5}: next green {pct(ng, len(sub)):6}  "
              f"next red {pct(len(sub)-ng, len(sub)):6}  (n={len(sub):,})")

    hr("STREAK — after 2 consecutive same-colour windows")
    for colour in ["green", "red"]:
        sub = w[(w["prev1"] == colour) & (w["prev2"] == colour)]
        ng  = (sub["result"] == "green").sum()
        print(f"  After {colour}+{colour}: next green {pct(ng, len(sub)):6}  "
              f"next red {pct(len(sub)-ng, len(sub)):6}  (n={len(sub):,})")

    hr("SCORE MOMENTUM — does a decisive previous window (5-0, 4-1) predict continuation?")
    for score in ["5-0", "4-1", "3-2"]:
        sub_g = w[(w["score"].shift(1) == score) & (w["prev1"] == "green")]
        sub_r = w[(w["score"].shift(1) == score) & (w["prev1"] == "red")]
        if len(sub_g) > 20:
            ng = (sub_g["result"] == "green").sum()
            print(f"  Prev {score} green → next green {pct(ng, len(sub_g)):6}  (n={len(sub_g):,})")
        if len(sub_r) > 20:
            nr = (sub_r["result"] == "red").sum()
            print(f"  Prev {score} red   → next red   {pct(nr, len(sub_r)):6}  (n={len(sub_r):,})")

    hr("PRICE vs MA20 at window open")
    for above, label in [(1, "Above MA20"), (0, "Below MA20")]:
        sub = w[w["above_ma20"] == above]
        ng  = (sub["result"] == "green").sum()
        print(f"  {label}: green {pct(ng, len(sub)):6}  red {pct(len(sub)-ng, len(sub)):6}  (n={len(sub):,})")

    hr("PRICE vs MA200 at window open  (macro regime)")
    for above, label in [(1, "Above MA200 (bull)"), (0, "Below MA200 (bear)")]:
        sub = w[w["above_ma200"] == above]
        ng  = (sub["result"] == "green").sum()
        print(f"  {label}: green {pct(ng, len(sub)):6}  red {pct(len(sub)-ng, len(sub)):6}  (n={len(sub):,})")

    hr("MA ALIGNMENT  (all three MAs same side)")
    bull = w[(w["above_ma20"]==1) & (w["above_ma50"]==1) & (w["above_ma200"]==1)]
    bear = w[(w["above_ma20"]==0) & (w["above_ma50"]==0) & (w["above_ma200"]==0)]
    ng_bull = (bull["result"] == "green").sum()
    ng_bear = (bear["result"] == "green").sum()
    print(f"  Full bull stack : green {pct(ng_bull, len(bull)):6}  (n={len(bull):,})")
    print(f"  Full bear stack : green {pct(ng_bear, len(bear)):6}  (n={len(bear):,})")

    hr("VOLATILITY REGIME")
    if "vol_regime" in w.columns:
        for regime in ["low_vol","mid_vol","high_vol"]:
            sub = w[w["vol_regime"] == regime]
            ng  = (sub["result"] == "green").sum()
            print(f"  {regime:10}: green {pct(ng, len(sub)):6}  (n={len(sub):,})")

    hr("TIME OF DAY  (UTC hour)")
    hourly = w.groupby("hour").apply(
        lambda x: pd.Series({
            "n": len(x),
            "green_pct": (x["result"]=="green").mean()*100
        })
    )
    print(f"  {'Hour':>5}  {'n':>6}  {'green%':>7}")
    for hour, row in hourly.iterrows():
        bar = "█" * int(row["green_pct"] / 2)
        flag = " ◄ hot" if abs(row["green_pct"] - 50) > 5 else ""
        print(f"  {hour:02d}:00  {int(row['n']):6,}  {row['green_pct']:6.1f}%  {bar}{flag}")

    hr("DAY OF WEEK  (0=Mon … 6=Sun)")
    days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    dow = w.groupby("day_of_week").apply(
        lambda x: pd.Series({
            "n": len(x),
            "green_pct": (x["result"]=="green").mean()*100
        })
    )
    for d, row in dow.iterrows():
        flag = " ◄" if abs(row["green_pct"] - 50) > 4 else ""
        print(f"  {days[d]}  n={int(row['n']):5,}  green={row['green_pct']:.1f}%{flag}")

    hr("1H ROLLING GREEN RATE → next window prediction")
    bins = [0, 0.35, 0.45, 0.55, 0.65, 1.01]
    labels = ["<35%","35-45%","45-55%","55-65%",">65%"]
    w["rate_bin"] = pd.cut(w["green_rate_1h"], bins=bins, labels=labels)
    for lb in labels:
        sub = w[w["rate_bin"] == lb]
        if len(sub) < 20:
            continue
        ng = (sub["result"] == "green").sum()
        print(f"  1h green rate {lb:>7}: next green {pct(ng, len(sub)):6}  (n={len(sub):,})")

    hr("SUMMARY — edges worth investigating")
    edges = []

    # check each factor for meaningful edge (>53% or <47%)
    checks = [
        ("prev1==green → green", w[w["prev1"]=="green"], "green"),
        ("prev1==red   → green", w[w["prev1"]=="red"],   "green"),
        ("above MA20   → green", w[w["above_ma20"]==1],  "green"),
        ("below MA20   → green", w[w["above_ma20"]==0],  "green"),
        ("above MA200  → green", w[w["above_ma200"]==1], "green"),
        ("below MA200  → green", w[w["above_ma200"]==0], "green"),
        ("full bull MA → green", bull,                   "green"),
        ("full bear MA → green", bear,                   "green"),
    ]
    for label, sub, target in checks:
        if len(sub) < 50:
            continue
        rate = (sub["result"] == target).mean()
        if abs(rate - 0.5) > 0.03:
            edges.append((label, rate, len(sub)))

    if edges:
        edges.sort(key=lambda x: abs(x[1]-0.5), reverse=True)
        for label, rate, n in edges:
            direction = "↑ green" if rate > 0.5 else "↓ red"
            print(f"  {direction}  {rate*100:.1f}%  |  {label}  (n={n:,})")
    else:
        print("  No factors found with >3% edge over base rate.")

    print()


# ─────────────────────────────────────────────────────────────────
#  5. ENTRY TIMING ANALYSIS
# ─────────────────────────────────────────────────────────────────

def analyse_entry_timing(df1m: pd.DataFrame, w: pd.DataFrame):
    """
    Key question: if you wait for candles 1-3 to print, how predictive
    is the running score for the final outcome?
    """
    hr("ENTRY TIMING — predictive value of partial scores")

    df1m = df1m.copy()
    df1m["green"] = (df1m["close"] > df1m["open"]).astype(int)
    df1m["window"] = df1m.index.floor("5min")

    # For each window, get the sequence of candle colours
    sequences = df1m.groupby("window")["green"].apply(list)
    sequences = sequences[sequences.apply(len) == 5]

    results = []
    for ts, seq in sequences.items():
        if ts not in w.index:
            continue
        final = w.loc[ts, "result"]
        for after_n in range(1, 5):   # after seeing 1, 2, 3, 4 candles
            running_green = sum(seq[:after_n])
            running_red   = after_n - running_green
            # Candles remaining
            remaining = 5 - after_n
            # Can red still win?
            # Current: running_green green, running_red red
            # Need majority of 5 → need 3+
            # After n candles, if green leads, can red catch up?
            results.append({
                "window":        ts,
                "after_n":       after_n,
                "running_green": running_green,
                "running_red":   running_red,
                "score_str":     f"{running_green}-{running_red}",
                "final":         final,
            })

    timing_df = pd.DataFrame(results)

    print(f"\n  {'After N':>8}  {'Score':>6}  {'→ Green%':>9}  {'→ Red%':>8}  {'n':>6}  {'Certainty':>10}")
    print(f"  {'─'*65}")

    for after_n in [1, 2, 3, 4]:
        sub = timing_df[timing_df["after_n"] == after_n]
        for score in sorted(sub["score_str"].unique()):
            s = sub[sub["score_str"] == score]
            ng = (s["final"] == "green").sum()
            nr = (s["final"] == "red").sum()
            n  = len(s)
            if n < 10:
                continue
            green_pct = ng / n * 100
            certainty = abs(green_pct - 50)
            flag = " ◄◄ strong" if certainty > 20 else (" ◄ edge" if certainty > 8 else "")
            print(f"  After {after_n} candle{'s' if after_n>1 else ' '}  "
                  f"{score:>5}  "
                  f"{green_pct:8.1f}%  "
                  f"{100-green_pct:7.1f}%  "
                  f"{n:6,}  "
                  f"{certainty:8.1f}pp{flag}")
        print()


# ─────────────────────────────────────────────────────────────────
#  6. MOMENTUM LOOKBACK ANALYSIS
# ─────────────────────────────────────────────────────────────────

def _quintile_analysis(w, col, section_label):
    """Bucket col into quintiles, print green% for each."""
    valid = w.dropna(subset=[col]).copy()
    if len(valid) < 100:
        print(f"  (skipped {col} — insufficient data)")
        return []

    try:
        valid["_q"] = pd.qcut(valid[col], q=5, duplicates="drop")
    except ValueError:
        print(f"  (skipped {col} — not enough unique values)")
        return []

    rows_out = []
    for q_label, grp in valid.groupby("_q", observed=True):
        ng = int((grp["result"] == "green").sum())
        n  = len(grp)
        gp = round(ng / n * 100, 1)
        flag = " ◄" if abs(gp - 50) > 3 else ""
        lo = q_label.left
        hi = q_label.right
        range_str = f"[{lo:+.4f}, {hi:+.4f}]" if abs(hi) < 10 else f"[{lo:+.1f}, {hi:+.1f}]"
        print(f"    {range_str:>28}  green {gp:5.1f}%  (n={n:,}){flag}")
        rows_out.append((section_label, f"{col} {range_str}", f"{gp}%", n))
    return rows_out


def analyse_momentum_lookback(w: pd.DataFrame):
    """Print momentum lookback analysis for 5/10/15 min prior periods."""
    hr("MOMENTUM LOOKBACK — prior 5m / 10m / 15m periods")

    all_rows = []

    for mins in [5, 10, 15]:
        pfx = f"prior{mins}m"
        print(f"\n  ── Prior {mins}m ──")

        for col, desc in [
            (f"{pfx}_ret",       "Net return %"),
            (f"{pfx}_n_green",   "Green candle count"),
            (f"{pfx}_range",     "Range % (volatility)"),
            (f"{pfx}_close_pos", "Close position in range"),
            (f"{pfx}_vol_trend", "Volume trend (recent/early)"),
        ]:
            if col not in w.columns:
                continue
            print(f"\n    {desc} ({col}):")
            rows = _quintile_analysis(w, col, f"Prior {mins}m Momentum")
            all_rows.extend(rows)

    # Acceleration
    print(f"\n  ── Acceleration (5m vs 15m avg) ──")
    print(f"\n    5m return minus 15m/3 avg:")
    rows = _quintile_analysis(w, "accel_5v15", "Acceleration")
    all_rows.extend(rows)

    # Lookback alignment
    hr("LOOKBACK ALIGNMENT — do all 3 periods agree?")
    for direction in ["all_up", "all_down", "mixed"]:
        sub = w[w["lookback_dir"] == direction]
        if len(sub) < 20:
            continue
        ng = int((sub["result"] == "green").sum())
        gp = round(ng / len(sub) * 100, 1)
        flag = " ◄" if abs(gp - 50) > 3 else ""
        print(f"  {direction:>10}: green {gp:5.1f}%  (n={len(sub):,}){flag}")
        all_rows.append(("Lookback Alignment", direction, f"{gp}%", len(sub)))

    return all_rows


# ─────────────────────────────────────────────────────────────────
#  7. EXCEL RESULTS SHEET
# ─────────────────────────────────────────────────────────────────

def _pct_val(n, d):
    return round(n / d * 100, 1) if d else None


def build_results_sheet(w: pd.DataFrame, df1m: pd.DataFrame, momentum_rows=None) -> pd.DataFrame:
    """Build a DataFrame that mirrors the terminal analysis output."""
    rows = []

    def add(section, label, value="", n=""):
        rows.append({"Section": section, "Label": label, "Value": value, "n": n})

    total = len(w)
    n_green = int((w["result"] == "green").sum())
    n_red   = int((w["result"] == "red").sum())

    # ── BASE RATES ─────────────────────────────────────────────────
    add("Base Rates", "Total 5m windows", total)
    add("Base Rates", "Green majority", f"{_pct_val(n_green, total)}%", n_green)
    add("Base Rates", "Red majority",   f"{_pct_val(n_red, total)}%",  n_red)

    # ── SCORE DISTRIBUTION ─────────────────────────────────────────
    for score, cnt in w["score"].value_counts().sort_index().items():
        add("Score Distribution", score, f"{_pct_val(cnt, total)}%", int(cnt))

    # ── MOMENTUM ───────────────────────────────────────────────────
    for prev in ["green", "red"]:
        sub = w[w["prev1"] == prev]
        ng  = int((sub["result"] == "green").sum())
        add("Momentum", f"After {prev} → green",
            f"{_pct_val(ng, len(sub))}%", len(sub))

    # ── STREAKS ────────────────────────────────────────────────────
    for colour in ["green", "red"]:
        sub = w[(w["prev1"] == colour) & (w["prev2"] == colour)]
        ng  = int((sub["result"] == "green").sum())
        add("Streaks", f"After {colour}+{colour} → green",
            f"{_pct_val(ng, len(sub))}%", len(sub))

    # ── SCORE MOMENTUM ─────────────────────────────────────────────
    for score in ["5-0", "4-1", "3-2"]:
        for prev_col, target, lbl in [("green","green","green"), ("red","red","red")]:
            sub = w[(w["score"].shift(1) == score) & (w["prev1"] == prev_col)]
            if len(sub) > 20:
                nt = int((sub["result"] == target).sum())
                add("Score Momentum", f"Prev {score} {prev_col} → next {target}",
                    f"{_pct_val(nt, len(sub))}%", len(sub))

    # ── MA ANALYSIS ────────────────────────────────────────────────
    for above, label in [(1,"Above MA20"), (0,"Below MA20")]:
        sub = w[w["above_ma20"] == above]
        ng  = int((sub["result"] == "green").sum())
        add("Price vs MA20", f"{label} → green", f"{_pct_val(ng, len(sub))}%", len(sub))

    for above, label in [(1,"Above MA200 (bull)"), (0,"Below MA200 (bear)")]:
        sub = w[w["above_ma200"] == above]
        ng  = int((sub["result"] == "green").sum())
        add("Price vs MA200", f"{label} → green", f"{_pct_val(ng, len(sub))}%", len(sub))

    bull = w[(w["above_ma20"]==1) & (w["above_ma50"]==1) & (w["above_ma200"]==1)]
    bear = w[(w["above_ma20"]==0) & (w["above_ma50"]==0) & (w["above_ma200"]==0)]
    add("MA Alignment", "Full bull stack → green",
        f"{_pct_val(int((bull['result']=='green').sum()), len(bull))}%", len(bull))
    add("MA Alignment", "Full bear stack → green",
        f"{_pct_val(int((bear['result']=='green').sum()), len(bear))}%", len(bear))

    # ── VOLATILITY REGIME ──────────────────────────────────────────
    if "vol_regime" in w.columns:
        for regime in ["low_vol", "mid_vol", "high_vol"]:
            sub = w[w["vol_regime"] == regime]
            ng  = int((sub["result"] == "green").sum())
            add("Volatility Regime", regime, f"{_pct_val(ng, len(sub))}%", len(sub))

    # ── TIME OF DAY ────────────────────────────────────────────────
    for hour, grp in w.groupby("hour"):
        ng = int((grp["result"] == "green").sum())
        gp = _pct_val(ng, len(grp))
        flag = " HOT" if abs(gp - 50) > 5 else ""
        add("Time of Day (UTC)", f"{hour:02d}:00{flag}", f"{gp}%", len(grp))

    # ── DAY OF WEEK ────────────────────────────────────────────────
    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    for d, grp in w.groupby("day_of_week"):
        ng = int((grp["result"] == "green").sum())
        add("Day of Week", day_names[d], f"{_pct_val(ng, len(grp))}%", len(grp))

    # ── 1H ROLLING GREEN RATE ─────────────────────────────────────
    bins = [0, 0.35, 0.45, 0.55, 0.65, 1.01]
    labels = ["<35%","35-45%","45-55%","55-65%",">65%"]
    w_copy = w.copy()
    w_copy["rate_bin"] = pd.cut(w_copy["green_rate_1h"], bins=bins, labels=labels)
    for lb in labels:
        sub = w_copy[w_copy["rate_bin"] == lb]
        if len(sub) < 20:
            continue
        ng = int((sub["result"] == "green").sum())
        add("1h Rolling Green Rate", f"{lb} → next green", f"{_pct_val(ng, len(sub))}%", len(sub))

    # ── ENTRY TIMING ───────────────────────────────────────────────
    df1m_c = df1m.copy()
    df1m_c["green"] = (df1m_c["close"] > df1m_c["open"]).astype(int)
    df1m_c["window"] = df1m_c.index.floor("5min")
    sequences = df1m_c.groupby("window")["green"].apply(list)
    sequences = sequences[sequences.apply(len) == 5]

    timing_rows = []
    for ts, seq in sequences.items():
        if ts not in w.index:
            continue
        final = w.loc[ts, "result"]
        for after_n in range(1, 5):
            rg = sum(seq[:after_n])
            rr = after_n - rg
            timing_rows.append({
                "after_n": after_n, "score_str": f"{rg}-{rr}", "final": final
            })
    timing_df = pd.DataFrame(timing_rows)

    for after_n in [1, 2, 3, 4]:
        sub = timing_df[timing_df["after_n"] == after_n]
        for score in sorted(sub["score_str"].unique()):
            s = sub[sub["score_str"] == score]
            n = len(s)
            if n < 10:
                continue
            green_pct = _pct_val(int((s["final"] == "green").sum()), n)
            certainty = round(abs(green_pct - 50), 1)
            flag = " STRONG" if certainty > 20 else (" EDGE" if certainty > 8 else "")
            add("Entry Timing",
                f"After {after_n} candle{'s' if after_n > 1 else ''} @ {score}{flag}",
                f"green {green_pct}% / red {round(100-green_pct,1)}%", n)

    # ── MOMENTUM LOOKBACK ────────────────────────────────────────
    if momentum_rows:
        for section, label, value, n in momentum_rows:
            add(section, label, value, n)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def run_backtest(asset: str, days: int, verbose: bool = False,
                 start_date: str = None, end_date: str = None):
    """Run full backtest for a single asset."""
    symbol = ASSET_MAP[asset]
    label = f"{start_date} → {end_date}" if start_date else f"{days}d"
    print(f"\n{'█'*70}")
    print(f"  {asset} ({symbol})  —  {label} backtest")
    print(f"{'█'*70}")

    # 1. Fetch
    df1m = fetch_1m_candles(days, symbol=symbol,
                            start_date=start_date, end_date=end_date)

    # 2. Build windows
    df_c = classify_candles(df1m)
    w    = build_windows(df_c)
    print(f"Built {len(w):,} complete 5-minute windows.")

    # 3. Add features
    w = add_features(w, df1m)
    print(f"Feature engineering done. Analysing {len(w):,} windows.")

    # 4. Main analysis
    analyse(w, verbose=verbose)

    # 5. Entry timing
    analyse_entry_timing(df1m, w)

    # 6. Momentum lookback
    momentum_rows = analyse_momentum_lookback(w)

    # 7. Export to Excel (data + results sheets)
    import shutil, tempfile
    tag = f"{start_date}_{end_date}" if start_date else f"{days}d"
    out = f"myriad_backtest_{asset}_{tag}.xlsx"
    results_df = build_results_sheet(w, df1m, momentum_rows)
    w_export = w.copy()
    w_export.index = w_export.index.tz_localize(None)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    with pd.ExcelWriter(tmp.name, engine="openpyxl") as writer:
        w_export.to_excel(writer, sheet_name="Data")
        results_df.to_excel(writer, sheet_name="Results", index=False)
    shutil.move(tmp.name, out)
    print(f"\nExported {len(w):,} windows to {out} (sheets: Data, Results)")

    hr("DONE")
    print(f"  {asset} data range: {df1m.index[0].strftime('%Y-%m-%d')} → {df1m.index[-1].strftime('%Y-%m-%d')}")
    print()

    return results_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",    type=int, default=30, help="Days of history (default 30)")
    parser.add_argument("--start",   type=str, default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     type=str, default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--symbol",  type=str, default="BTC",
                        choices=ALL_ASSETS, help="Asset to backtest (default BTC)")
    parser.add_argument("--all",     action="store_true", help="Run all assets")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    assets = ALL_ASSETS if args.all else [args.symbol.upper()]

    for asset in assets:
        run_backtest(asset, args.days, args.verbose,
                     start_date=args.start, end_date=args.end)


if __name__ == "__main__":
    main()
