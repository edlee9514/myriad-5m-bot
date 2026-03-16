"""On-chain trade execution via web3.py on BSC."""

import logging
from typing import Dict, Optional

from web3 import Web3

import config

log = logging.getLogger(__name__)


class Executor:
    """Handles USD1 approval and share purchases on the PredictionMarketV3 contract."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.w3 = Web3(Web3.HTTPProvider(config.BSC_RPC_URL))

        if not self.w3.isConnected():
            raise ConnectionError(f"Cannot connect to BSC RPC: {config.BSC_RPC_URL}")

        self.pm_address = Web3.toChecksumAddress(config.PREDICTION_MARKET_ADDRESS)
        self.usd1_address = Web3.toChecksumAddress(config.USD1_TOKEN_ADDRESS)

        self.pm = self.w3.eth.contract(
            address=self.pm_address, abi=config.PREDICTION_MARKET_ABI
        )
        self.usd1 = self.w3.eth.contract(
            address=self.usd1_address, abi=config.ERC20_ABI
        )

        if config.PRIVATE_KEY:
            self.account = self.w3.eth.account.from_key(config.PRIVATE_KEY)
            self.address = self.account.address
        else:
            self.account = None
            self.address = None

        # Myriad smart account holds the funds; signer wallet sends txs
        self.myriad_wallet = (
            Web3.toChecksumAddress(config.MYRIAD_WALLET)
            if config.MYRIAD_WALLET
            else self.address
        )

    def _to_wei(self, amount: float) -> int:
        return int(amount * 10 ** config.USD1_DECIMALS)

    def _from_wei(self, amount: int) -> float:
        return amount / 10 ** config.USD1_DECIMALS

    def get_usd1_balance(self) -> float:
        raw = self.usd1.functions.balanceOf(self.address).call()
        return self._from_wei(raw)

    def get_bnb_balance(self) -> float:
        raw = self.w3.eth.getBalance(self.address)
        return self.w3.fromWei(raw, "ether")

    def ensure_allowance(self, amount: float) -> Optional[str]:
        """Approve the prediction market contract to spend USD1 if needed.

        Returns the tx hash if an approval was sent, None if already sufficient.
        """
        amount_wei = self._to_wei(amount)
        current = self.usd1.functions.allowance(
            self.address, self.pm_address
        ).call()

        if current >= amount_wei:
            return None

        # Approve a large amount to avoid repeated approvals
        approve_amount = self._to_wei(10_000)
        return self._send_tx(
            self.usd1.functions.approve(self.pm_address, approve_amount)
        )

    def calc_buy_amount(self, market_id: int, outcome_id: int, value: float) -> float:
        """Calculate how many shares we'd receive for a given USD1 spend."""
        value_wei = self._to_wei(value)
        shares_wei = self.pm.functions.calcBuyAmount(
            value_wei, market_id, outcome_id
        ).call()
        return self._from_wei(shares_wei)

    def buy(
        self, market_id: int, outcome_id: int, value: float, slippage: float = 0.02
    ) -> dict:
        """Buy outcome shares on the prediction market.

        Args:
            market_id: On-chain market ID.
            outcome_id: 0 = More Green, 1 = More Red.
            value: USD1 amount to spend (before fees).
            slippage: Max slippage tolerance (default 2%).

        Returns:
            Dict with tx_hash, shares_expected, value.
        """
        shares = self.calc_buy_amount(market_id, outcome_id, value)
        min_shares = self._to_wei(shares * (1 - slippage))
        value_wei = self._to_wei(value)

        log.info(
            f"Buying: market={market_id} outcome={outcome_id} "
            f"value={value} USD1 → ~{shares:.4f} shares"
        )

        if self.dry_run:
            log.info("[DRY RUN] Skipping on-chain transaction")
            return {
                "tx_hash": "0x_dry_run",
                "shares_expected": shares,
                "value": value,
                "dry_run": True,
            }

        # Ensure allowance before buying
        self.ensure_allowance(value)

        tx_hash = self._send_tx(
            self.pm.functions.buy(market_id, outcome_id, min_shares, value_wei)
        )

        return {
            "tx_hash": tx_hash,
            "shares_expected": shares,
            "value": value,
            "dry_run": False,
        }

    def claim_winnings(self, market_id: int) -> str:
        """Claim winnings from a resolved market. Returns tx hash."""
        log.info(f"Claiming winnings for market {market_id}")
        if self.dry_run:
            log.info("[DRY RUN] Skipping claim")
            return "0x_dry_run"
        return self._send_tx(self.pm.functions.claimWinnings(market_id))

    def _send_tx(self, fn) -> str:
        """Build, sign, and send a transaction. Returns tx hash hex."""
        if not self.account:
            raise RuntimeError("No private key configured — cannot send transactions")

        tx = fn.buildTransaction(
            {
                "from": self.address,
                "chainId": config.CHAIN_ID,
                "nonce": self.w3.eth.getTransactionCount(self.address),
                "gas": 300_000,
                "gasPrice": self.w3.eth.gasPrice,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, config.PRIVATE_KEY)
        tx_hash = self.w3.eth.sendRawTransaction(signed.rawTransaction)
        receipt = self.w3.eth.waitForTransactionReceipt(tx_hash, timeout=60)

        if receipt["status"] != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

        log.info(f"TX confirmed: {tx_hash.hex()} (gas used: {receipt['gasUsed']})")
        return tx_hash.hex()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ex = Executor(dry_run=True)
    if ex.address:
        print(f"Wallet: {ex.address}")
        print(f"USD1 balance: {ex.get_usd1_balance():.4f}")
        print(f"BNB balance: {ex.get_bnb_balance():.6f}")
    else:
        print("No private key configured. Set PRIVATE_KEY in .env")
    print(f"Connected to BSC: {ex.w3.isConnected()}")
