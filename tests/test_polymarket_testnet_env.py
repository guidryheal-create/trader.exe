import os
import pytest


def _is_hex_address(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith("0x"):
        return False
    if len(value) != 42:
        return False
    try:
        int(value[2:], 16)
        return True
    except ValueError:
        return False


@pytest.mark.skipif(
    not os.getenv("POLYGON_PRIVATE_KEY"),
    reason="POLYGON_PRIVATE_KEY not set; skipping testnet workforce env check.",
)
def test_polymarket_testnet_env():
    """Validate testnet env configuration when private key is provided."""
    chain_id = os.getenv("POLYMARKET_CHAIN_ID", "")
    assert chain_id == "80002", "POLYMARKET_CHAIN_ID should be 80002 for Amoy testnet"

    address = os.getenv("POLYGON_ADDRESS", "")
    assert _is_hex_address(address), "POLYGON_ADDRESS must be a valid 0x address"
