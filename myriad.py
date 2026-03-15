"""Myriad API client — discover open PENGU candle markets and read prices."""

import logging
from typing import Dict, List, Optional

import requests
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)


def _get(path: str, params: Optional[Dict] = None) -> Dict:
    url = f"{config.MYRIAD_API_BASE}{path}"
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_open_candle_markets(asset: str = "pengu") -> List[Dict]:
    """Return all open candle markets for the given asset.

    Scans paginated results looking for markets whose title matches
    '<asset> candles from ...' and are still in 'open' state.
    """
    markets = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        data = _get("/markets", params={"state": "open", "limit": 50, "page": page})
        items = data.get("data", data) if isinstance(data, dict) else data

        if not items:
            break

        for m in items:
            title = m.get("title", "").lower()
            if asset.lower() in title and "candle" in title:
                markets.append(m)

        page += 1

    return markets


def find_next_pengu_market() -> Optional[Dict]:
    """Find the next open PENGU candle market that hasn't locked yet.

    Returns the market dict if found, None if no eligible market exists.
    Markets lock at expiresAt (when the 5-min window starts).
    """
    markets = fetch_open_candle_markets(config.TARGET_ASSET)

    if not markets:
        return None

    now = datetime.now(timezone.utc)
    eligible = []

    for m in markets:
        expires = datetime.fromisoformat(m["expiresAt"].replace("Z", "+00:00"))
        if expires > now and m.get("state") == "open":
            eligible.append((expires, m))

    if not eligible:
        return None

    # Return the soonest-expiring market (next to lock)
    eligible.sort(key=lambda x: x[0])
    return eligible[0][1]


def get_outcome_price(market: dict, outcome_id: int) -> float:
    """Get the current price for a specific outcome from market data."""
    for outcome in market.get("outcomes", []):
        if outcome["id"] == outcome_id:
            return outcome["price"]
    return -1.0


def get_market_by_slug(slug: str) -> dict:
    """Fetch a single market by its slug."""
    return _get(f"/markets/{slug}")


def seconds_until_lock(market: dict) -> float:
    """Seconds remaining until betting locks for this market."""
    expires = datetime.fromisoformat(market["expiresAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (expires - now).total_seconds()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    market = find_next_pengu_market()
    if market:
        price = get_outcome_price(market, config.TARGET_OUTCOME_ID)
        secs = seconds_until_lock(market)
        print(f"Found: {market['title']}")
        print(f"  Market ID: {market['id']}")
        print(f"  'More Red' price: {price}")
        print(f"  Locks in: {secs:.0f}s")
        print(f"  Slug: {market['slug']}")
    else:
        print("No open PENGU candle market found.")
