import os
import time
import ast
from decimal import Decimal

from web3 import Web3
from web3.middleware import geth_poa_middleware

import httpx
from eth_account import Account
from eth_account.messages import encode_structured_data

# =========================
# CONFIG
# =========================

POLYGON_RPC = "https://polygon-rpc.com"
CHAIN_ID = 137

PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
assert PRIVATE_KEY, "Missing wallet key"

CLOB_ORDERBOOK = "https://clob.polymarket.com/orderbook"
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"

EXCHANGE = Web3.to_checksum_address(
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
)

USDC_DECIMALS = 6
FOLLOW_USD = Decimal("1")

# =========================
# WEB3 INIT
# =========================

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

account = Account.from_key(PRIVATE_KEY)
WALLET = account.address

# =========================
# HELPERS
# =========================

def get_market(token_id: str):
    res = httpx.get(GAMMA_MARKETS, params={"clob_token_ids": token_id})
    res.raise_for_status()
    return res.json()[0]


def get_orderbook(token_id: str):
    res = httpx.get(CLOB_ORDERBOOK, params={"token_id": token_id})
    res.raise_for_status()
    return res.json()


def find_market_leader(orderbook):
    """
    Leader = biggest size at best price
    """
    best_bid = orderbook["bids"][0]
    best_ask = orderbook["asks"][0]

    bid_size = Decimal(best_bid["size"])
    ask_size = Decimal(best_ask["size"])

    if bid_size >= ask_size:
        return {
            "side": 0,  # BUY
            "price": Decimal(best_bid["price"]),
        }
    else:
        return {
            "side": 1,  # SELL
            "price": Decimal(best_ask["price"]),
        }


def build_order_struct(token_id, side, price):
    """
    Polymarket Order struct (EIP-712)
    """
    usdc_amount = FOLLOW_USD / price
    maker_amount = int(usdc_amount * (10 ** USDC_DECIMALS)) if side == 0 else 0
    taker_amount = int(usdc_amount * (10 ** USDC_DECIMALS)) if side == 1 else 0

    return {
        "maker": WALLET,
        "tokenId": int(token_id),
        "makerAmount": maker_amount,
        "takerAmount": taker_amount,
        "feeRateBps": 1,
        "side": side,
        "nonce": int(time.time()),
        "expiration": 0,
    }


def sign_order(order):
    domain = {
        "name": "Polymarket CLOB",
        "version": "1",
        "chainId": CHAIN_ID,
        "verifyingContract": EXCHANGE,
    }

    types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Order": [
            {"name": "maker", "type": "address"},
            {"name": "tokenId", "type": "uint256"},
            {"name": "makerAmount", "type": "uint256"},
            {"name": "takerAmount", "type": "uint256"},
            {"name": "feeRateBps", "type": "uint256"},
            {"name": "side", "type": "uint8"},
            {"name": "nonce", "type": "uint256"},
            {"name": "expiration", "type": "uint256"},
        ],
    }

    message = {
        "domain": domain,
        "types": types,
        "primaryType": "Order",
        "message": order,
    }

    encoded = encode_structured_data(message)
    signed = Account.sign_message(encoded, PRIVATE_KEY)

    return signed.signature


# =========================
# TEST
# =========================

def test_follow_market_leader():
    token_id = "101669189743438912873361127612589311253202068943959811456820079057046819967115"

    print("Fetching orderbook…")
    orderbook = get_orderbook(token_id)
    print("order_book:", orderbook)
    
    leader = find_market_leader(orderbook)
    print("Leader:", leader)

    order = build_order_struct(
        token_id=token_id,
        side=leader["side"],
        price=leader["price"],
    )

    signature = sign_order(order)

    print("ORDER STRUCT")
    print(order)
    print("SIGNATURE")
    print(signature.hex())

    print(
        "\n✔ Order ready. Next step is Exchange.matchOrders() "
        "or adapter execution."
    )


if __name__ == "__main__":
    test_follow_market_leader()
