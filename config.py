"""Configuration for the Myriad 5m candle bot."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── BSC / Web3 ──────────────────────────────────────────────────────
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
MYRIAD_WALLET = os.getenv("MYRIAD_WALLET", "")  # smart account that holds funds
CHAIN_ID = 56

# ── Contracts ───────────────────────────────────────────────────────
PREDICTION_MARKET_ADDRESS = "0x39e66ee6b2ddaf4defded3038e0162180dbef340"
USD1_TOKEN_ADDRESS = "0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d"
USD1_DECIMALS = 18

# ── Myriad API ──────────────────────────────────────────────────────
MYRIAD_API_BASE = "https://api-v2.myriadprotocol.com"

# ── Strategy ────────────────────────────────────────────────────────
TARGET_ASSET = "PENGU"
TARGET_OUTCOME = "More Red"
TARGET_OUTCOME_ID = 1
BET_SIZE_USD = 2.0           # USD1 base bet per trade
MAX_ENTRY_PRICE = 0.58       # skip if "More Red" price exceeds this
POLL_INTERVAL_SECONDS = 120     # markets publish ~8min early, new one every 5min

# Hour-based bet multiplier (UTC). Default 1.0x for unlisted hours.
HOUR_MULTIPLIER = {
    6: 2.0,    # 61% red, +10pp edge
    10: 2.0,   # 60% red, +9pp edge
    9: 0.5,    # 54% red, +3pp edge
    15: 0.5,   # 55% red, +4pp edge
    16: 0.5,   # 54% red, +3pp edge
    22: 0.5,   # 54% red, +3pp edge
}

# ── Kill switches ───────────────────────────────────────────────────
DAILY_LOSS_LIMIT_USD = -50.0
ROLLING_WINDOW_SIZE = 2016   # 7 days of 5-min windows (288/day × 7)
ROLLING_GREEN_PAUSE = 0.50   # pause if green rate exceeds 50% over rolling window

# ── Logging ─────────────────────────────────────────────────────────
TRADE_LOG_FILE = "backtest_data/trades.csv"

# ── Minimal ABIs ────────────────────────────────────────────────────
ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PREDICTION_MARKET_ABI = [
    {
        "inputs": [
            {"name": "marketId", "type": "uint256"},
            {"name": "outcomeId", "type": "uint256"},
            {"name": "minOutcomeSharesToBuy", "type": "uint256"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "buy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "value", "type": "uint256"},
            {"name": "marketId", "type": "uint256"},
            {"name": "outcomeId", "type": "uint256"},
        ],
        "name": "calcBuyAmount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "uint256"}],
        "name": "getMarketData",
        "outputs": [
            {"name": "state", "type": "uint256"},
            {"name": "closesAtTimestamp", "type": "uint256"},
            {"name": "liquidityAmount", "type": "uint256"},
            {"name": "resolvedOutcomeId", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "uint256"}],
        "name": "getMarketPrices",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "uint256"}],
        "name": "claimWinnings",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
