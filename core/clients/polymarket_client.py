"""
Polymarket client supporting both public APIs and authenticated CLOB trading.

Supports two modes:
1. Public API (Gamma & CLOB read-only): https://gamma-api.polymarket.com, https://clob.polymarket.com
2. Authenticated CLOB client (py-clob-client): Private key + chain ID for trading

Reference: https://github.com/polymarket/py-clob-client
"""

from asyncio import events
from asyncio import events
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
import httpx
import json
import time
from decimal import Decimal, ROUND_DOWN
from core.logging import log
from core.config import settings
from core.models.polymarket import SimpleMarket, SimpleEvent, SimpleMarketQuery, SimpleEventQuery

from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware import ExtraDataToPOAMiddleware

# Public API URLs (no auth required)
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
DEFAULT_CLOB_EXCHANGE_ADDRESS = os.getenv(
    "POLYMARKET_EXCHANGE_ADDRESS",
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
)

# Try to import py-clob-client for authenticated trading
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        ApiCreds,
        OrderArgs,
        OrderType,
        OpenOrderParams,
        TradeParams,
        OrderScoringParams,
        BalanceAllowanceParams,
        AssetType,
    )
    from py_clob_client.endpoints import ORDERS
    from py_clob_client.order_builder.constants import BUY, SELL
    from py_clob_client.constants import AMOY
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    ClobClient = None  # type: ignore
    ApiCreds = None  # type: ignore
    OrderArgs = None  # type: ignore
    OrderType = None  # type: ignore
    OpenOrderParams = None  # type: ignore
    TradeParams = None  # type: ignore
    OrderScoringParams = None  # type: ignore
    BalanceAllowanceParams = None  # type: ignore
    AssetType = None  # type: ignore
    AMOY = 80002
    BUY = "BUY"
    SELL = "SELL"
    ORDERS = "/orders"
    CLOB_CLIENT_AVAILABLE = False

# Optional low-level order builder utilities
try:
    from py_order_utils.builders import OrderBuilder
    from py_order_utils.model import OrderData
    from py_order_utils.signer import Signer
    ORDER_UTILS_AVAILABLE = True
except ImportError:
    OrderBuilder = None  # type: ignore
    OrderData = None  # type: ignore
    Signer = None  # type: ignore
    ORDER_UTILS_AVAILABLE = False

try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
except ImportError:
    Account = None  # type: ignore
    ETH_ACCOUNT_AVAILABLE = False

try:
    from web3 import Web3
    from web3.constants import MAX_INT
    WEB3_AVAILABLE = True
except ImportError:
    Web3 = None  # type: ignore
    MAX_INT = None  # type: ignore
    WEB3_AVAILABLE = False

DEFAULT_USDC_ADDRESS = os.getenv(
    "POLYMARKET_USDC_ADDRESS",
    "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
)
DEFAULT_USDC_DECIMALS = int(os.getenv("POLYMARKET_USDC_DECIMALS", "6"))
DEFAULT_SHARE_DECIMALS = int(os.getenv("POLYMARKET_SHARE_DECIMALS", "6"))
DEFAULT_CTF_ADDRESS = os.getenv(
    "POLYMARKET_CTF_ADDRESS",
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
)
DEFAULT_CTF_EXCHANGE = os.getenv(
    "POLYMARKET_CTF_EXCHANGE",
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
)
DEFAULT_NEG_RISK_CTF_EXCHANGE = os.getenv(
    "POLYMARKET_NEG_RISK_CTF_EXCHANGE",
    "0xC5d563A36AE78145C45a50134d48A1215220f80a",
)
DEFAULT_NEG_RISK_ADAPTER = os.getenv(
    "POLYMARKET_NEG_RISK_ADAPTER",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
)
ERC20_BALANCEOF_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]
ERC20_ALLOWANCE_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]
ERC1155_APPROVAL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "address", "name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class PolymarketClient:
    """Polymarket client supporting public APIs and authenticated CLOB trading.
    
    Can operate in two modes:
    1. Public API mode (no authentication): read-only market data
    2. Authenticated mode: full trading capabilities via py-clob-client
    """
    
    def __init__(
        self,
        timeout: float = 30.0,
        private_key: Optional[str] = None,
        polygon_address: Optional[str] = None,
        chain_id: Optional[int] = None,
        host: Optional[str] = None
    ):
        """Initialize client.
        
        Args:
            timeout: Request timeout in seconds (default: 30.0)
            private_key: Wallet private key for authenticated mode (from env: POLYGON_PRIVATE_KEY)
            polygon_address: Wallet address (from env: POLYGON_ADDRESS)
            chain_id: Polygon chain ID (from env: POLYMARKET_CHAIN_ID, default: 80002 for testnet)
            host: CLOB API endpoint (default: https://clob.polymarket.com)
        """
        self.timeout = timeout
        self._clob_client: Optional[Any] = None  # ClobClient instance
        
        # Get credentials from settings, allowing override by direct arguments.
        self.private_key = private_key or settings.polygon_private_key
        self.polygon_address = polygon_address or settings.polygon_address
        self.chain_id = chain_id or settings.polymarket_chain_id
        self.exchange_address = os.getenv("POLYMARKET_EXCHANGE_ADDRESS", DEFAULT_CLOB_EXCHANGE_ADDRESS)
        self.usdc_address = os.getenv("POLYMARKET_USDC_ADDRESS", DEFAULT_USDC_ADDRESS)
        self.ctf_address = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E" 
        
        self.ctf_exchange = os.getenv("POLYMARKET_CTF_EXCHANGE", DEFAULT_CTF_EXCHANGE)
        self.neg_risk_ctf_exchange = os.getenv("POLYMARKET_NEG_RISK_CTF_EXCHANGE", DEFAULT_NEG_RISK_CTF_EXCHANGE)
        self.neg_risk_adapter = os.getenv("POLYMARKET_NEG_RISK_ADAPTER", DEFAULT_NEG_RISK_ADAPTER)
        self.polygon_rpc = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
        self.web3 = Web3(Web3.HTTPProvider(self.polygon_rpc)) if WEB3_AVAILABLE else None

        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        
        self.erc20_approve = """[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"owner","type":"address"},{"indexed":true,"internalType":"address","name":"spender","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationCanceled","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationUsed","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"Blacklisted","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"address","name":"userAddress","type":"address"},{"indexed":false,"internalType":"address payable","name":"relayerAddress","type":"address"},{"indexed":false,"internalType":"bytes","name":"functionSignature","type":"bytes"}],"name":"MetaTransactionExecuted","type":"event"},{"anonymous":false,"inputs":[],"name":"Pause","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"newRescuer","type":"address"}],"name":"RescuerChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"previousAdminRole","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"newAdminRole","type":"bytes32"}],"name":"RoleAdminChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleGranted","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleRevoked","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"from","type":"address"},{"indexed":true,"internalType":"address","name":"to","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"UnBlacklisted","type":"event"},{"anonymous":false,"inputs":[],"name":"Unpause","type":"event"},{"inputs":[],"name":"APPROVE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"BLACKLISTER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"CANCEL_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DECREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEFAULT_ADMIN_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEPOSITOR_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DOMAIN_SEPARATOR","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"EIP712_VERSION","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"INCREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"META_TRANSACTION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PAUSER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PERMIT_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"RESCUER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"TRANSFER_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"WITHDRAW_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"approveWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"authorizationState","outputs":[{"internalType":"enum GasAbstraction.AuthorizationState","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"blacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"blacklisters","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"cancelAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"subtractedValue","type":"uint256"}],"name":"decreaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"decrement","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"decreaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"user","type":"address"},{"internalType":"bytes","name":"depositData","type":"bytes"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"userAddress","type":"address"},{"internalType":"bytes","name":"functionSignature","type":"bytes"},{"internalType":"bytes32","name":"sigR","type":"bytes32"},{"internalType":"bytes32","name":"sigS","type":"bytes32"},{"internalType":"uint8","name":"sigV","type":"uint8"}],"name":"executeMetaTransaction","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleAdmin","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"uint256","name":"index","type":"uint256"}],"name":"getRoleMember","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleMemberCount","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"grantRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"hasRole","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"addedValue","type":"uint256"}],"name":"increaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"increment","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"increaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"},{"internalType":"uint8","name":"newDecimals","type":"uint8"},{"internalType":"address","name":"childChainManager","type":"address"}],"name":"initialize","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"initialized","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"isBlacklisted","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"paused","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pausers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"permit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"renounceRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"tokenContract","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"rescueERC20","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"rescuers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"revokeRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transferFrom","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"transferWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"unBlacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"unpause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"}],"name":"updateMetadata","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"withdrawWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"}]"""
        self.erc1155_set_approval = """[{"inputs": [{ "internalType": "address", "name": "operator", "type": "address" },{ "internalType": "bool", "name": "approved", "type": "bool" }],"name": "setApprovalForAll","outputs": [],"stateMutability": "nonpayable","type": "function"}]"""






        self.usdc = self.web3.eth.contract(
            address=self.usdc_address, abi=self.erc20_approve
        )

        self._ctf_contract = (
            self.web3.eth.contract(address=self.ctf_address, abi=self.erc1155_set_approval)
            if self.web3
            else None
        )

        self.usdc_decimals = int(os.getenv("POLYMARKET_USDC_DECIMALS", DEFAULT_USDC_DECIMALS))
        self.share_decimals = int(os.getenv("POLYMARKET_SHARE_DECIMALS", DEFAULT_SHARE_DECIMALS))

        
        self.host = host or os.getenv("CLOB_API_URL") or CLOB_API_URL
        self._api_creds = self._load_api_creds()
        self.polygon_rpc = "https://polygon-rpc.com"
        self.w3 = Web3(Web3.HTTPProvider(self.polygon_rpc))

        self.usdc = self.web3.eth.contract(
            address=self.usdc_address, abi=self.erc20_approve
        )


        self.ctf = self.web3.eth.contract(
            address=self.ctf_address, abi=self.erc1155_set_approval
        )
        
        # Initialize authenticated CLOB client if credentials provided
        if self.private_key and CLOB_CLIENT_AVAILABLE:
            self._init_clob_client()
        else:
            if self.private_key or self.polygon_address:
                log.warning(
                    "CLOB client not available: py-clob-client not installed or missing credentials. "
                    "Falling back to public API mode."
                )

        self.init_approvals(False) # Set up approvals on init (can be toggled off for testing or if not needed)

    def refresh_from_env(self) -> None:
        """Reload credentials from environment and (re)initialize CLOB client."""
        print(settings.polygon_private_key)
        self.private_key = os.getenv("POLYGON_PRIVATE_KEY", settings.polygon_private_key)
        self.polygon_address = os.getenv("POLYGON_ADDRESS", settings.polygon_address) 
        self.chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", settings.polymarket_chain_id) or 137)
        self.host = os.getenv("CLOB_API_URL") or self.host or CLOB_API_URL
        self._api_creds = self._load_api_creds()
        if self.private_key and CLOB_CLIENT_AVAILABLE:
            self._init_clob_client()

    def auth_diagnostics(self) -> Dict[str, Any]:
        """Return diagnostic info for auth readiness."""
        return {
            "clob_client_available": CLOB_CLIENT_AVAILABLE,
            "has_private_key": bool(self.private_key),
            "has_polygon_address": bool(self.polygon_address),
            "has_api_creds": bool(self._api_creds),
            "chain_id": self.chain_id,
            "host": self.host,
            "is_authenticated": self.is_authenticated,
        }
    
    def _load_api_creds(self) -> Optional[Any]:
        """Load API credentials from environment if available."""
        if not CLOB_CLIENT_AVAILABLE or ApiCreds is None:
            return None
        api_key = os.getenv("POLYMARKET_API_KEY")
        api_secret = os.getenv("POLYMARKET_API_SECRET")
        api_passphrase = os.getenv("POLYMARKET_PASSPHRASE")
        if api_key and api_secret and api_passphrase:
            return ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        return None

    def _init_clob_client(self) -> None:
        """Initialize the authenticated CLOB client."""
        try:
            if not CLOB_CLIENT_AVAILABLE:
                log.warning("py-clob-client not available. Install with: pip install py-clob-client")
                return

            # Create CLOB client with wallet credentials (py-clob-client examples methodology)
            # ClobClient(host, key=key, chain_id=chain_id, signature_type=1, funder=POLYMARKET_PROXY_ADDRESS)
            self._clob_client = ClobClient(
                host=self.host,
                key=self.private_key,
                chain_id=self.chain_id,
                signature_type=2,
                funder= self.polygon_address
            )
            self._api_creds = self._clob_client.create_or_derive_api_creds()
            self._clob_client.set_api_creds(self._api_creds) 

            log.info(f"✅ Authenticated CLOB client initialized (chain_id={self.chain_id}, address={self.polygon_address})")
        except Exception as e:
            log.warning(f"Failed to initialize CLOB client: {e}. Falling back to public API mode.")
            self._clob_client = None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if client has authenticated CLOB access."""
        return self._clob_client is not None
    
    async def close(self):
        """Close any authenticated client resources."""
        self._clob_client = None
    
    async def _fetch_gamma_api(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Fetch from Gamma API."""
        try:
            url = f"{GAMMA_API_URL}{endpoint}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params or {})
                response.raise_for_status()
                return response.json()
        except Exception as e:
            log.error(f"Gamma API error for {endpoint}: {e}")
            raise
    
    async def _fetch_clob_api(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Fetch from CLOB public API."""
        try:
            url = f"{CLOB_API_URL}{endpoint}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params or {})
                response.raise_for_status()
                return response.json()
        except Exception as e:
            log.error(f"CLOB API error for {endpoint}: {e}")
            raise
    
    async def get_market_details(
        self,
        market_id: Optional[str] = None,
        condition_id: Optional[str] = None,
        slug: Optional[str] = None,
        market_maker_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get complete market information.
        
        Args:
            market_id: Market ID
            condition_id: Condition ID (alternative identifier)
            slug: Market slug (alternative identifier)
            market_maker_address: Market maker address (alternative identifier)
        
        Returns:
            Full market object with all metadata
        """
        try:
            # Determine which identifier to use
            if market_maker_address:
                data = await self._fetch_gamma_api("/markets", {"marketMakerAddress": market_maker_address})
            elif slug:
                data = await self._fetch_gamma_api("/markets", {"slug": slug})
                if isinstance(data, list) and len(data) > 0:
                    return SimpleMarketQuery(**data[0])
                data = await self._fetch_gamma_api(f"/markets/{slug}")
            elif condition_id:
                data = await self._fetch_gamma_api("/markets", {"condition_id": condition_id})
            elif market_id:
                if isinstance(market_id, str) and market_id.startswith("0x") and len(market_id) == 42:
                    data = await self._fetch_gamma_api("/markets", {"marketMakerAddress": market_id})
                    if isinstance(data, list) and len(data) > 0:
                        return SimpleMarketQuery(**data[0])
                data = await self._fetch_gamma_api(f"/markets/{market_id}")
            else:
                raise ValueError("One of market_id, condition_id, or slug must be provided")
            
            # Handle list response
            if isinstance(data, list) and len(data) > 0:
                return SimpleMarketQuery(**data[0])
            
            return SimpleMarketQuery(**data)
        except Exception as e:
            log.error(f"Failed to get market details: {e}")
            raise

    async def search_markets(
        self,
        query: str = "",
        limit: int = 5,
        page: int = 1,
        active_only: bool = True,
        sort: str = "volume_24hr",
    ) -> List[Dict[str, Any]]:
        """
        Search active Polymarket markets using the Gamma public search API.

        Server-side filtering & sorting to minimize payload size.
        """
        try:
            params = {
                "q": query,
                "page": page,
                "type": "events",
                "sort": sort,
                "presets": ["EventsTitle", "Events"],
            }

            if active_only:
                params["events_status"] = "active"

            data = await self._fetch_gamma_api("/public-search", params)
            resp =[
                        SimpleMarketQuery(**m)
                        for e in data["events"][:limit]
                        for m in e.get("markets", [])
                    ]
            return resp

        except Exception as e:
            log.error(f"Gamma market search failed: {e}")
            raise
    
    async def get_event_markets(
        self,
        event_slug: Optional[str] = None,
        event_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all markets for a specific event.
        
        Args:
            event_slug: Event slug (e.g., "presidential-election-2024")
            event_id: Event ID (alternative to slug)
        
        Returns:
            All markets belonging to the event
        """
        try:
            if not event_slug and not event_id:
                raise ValueError("Either event_slug or event_id must be provided")
            
            # First, get the event details
            if event_slug:
                event_data = await self._fetch_gamma_api(f"/events/{event_slug}")
            else:
                event_data = await self._fetch_gamma_api(f"/events/{event_id}")
            
            # Extract markets from event
            if isinstance(event_data, list) and len(event_data) > 0:
                event = event_data[0]
            else:
                event = event_data
            
            markets = [SimpleMarket(**m) for m in event.get("markets", [])]
            return markets
        except Exception as e:
            log.error(f"Failed to get event markets: {e}")
            raise
    
    async def get_orderbook(
        self,
        token_id: str,
        depth: int = 20
    ) -> Dict[str, Any]:
        """Get complete order book.
        
        Args:
            token_id: Token ID
            depth: Number of price levels to return per side (default 20)
        
        Returns:
            Order book with bids and asks
        """
        try:
            book_data = await self._fetch_clob_api("/book", {"token_id": token_id})
            
            # Parse bids and asks
            bids = [
                {"price": float(entry["price"]), "size": float(entry["size"])}
                for entry in book_data.get("bids", [])[:depth]
            ]
            
            asks = [
                {"price": float(entry["price"]), "size": float(entry["size"])}
                for entry in book_data.get("asks", [])[:depth]
            ]
            
            return {
                "token_id": token_id,
                "bids": bids,
                "asks": asks
            }
        except Exception as e:
            log.error(f"Failed to get orderbook: {e}")
            raise

    def map_api_to_event(self, event) -> SimpleEvent:
        description = event["description"] if "description" in event.keys() else ""
        return {
            "id": int(event["id"]),
            "ticker": event["ticker"],
            "slug": event["slug"],
            "title": event["title"],
            "description": description,
            "active": event["active"],
            "closed": event["closed"],
            "archived": event["archived"],
            "new": event["new"],
            "featured": event["featured"],
            "restricted": event["restricted"],
            "end": event["endDate"],
            "markets": ",".join([x["id"] for x in event["markets"]]),
        }

    async def get_trending_markets(
        self,
        timeframe: str = "24hr",
        limit: int = 20,
        slug: Optional[str] = "crypto",
    ) -> List[SimpleEvent]:
        """
        Get trending events sorted by volume.
        """
        params = {
            "limit": limit,
            "active": "true",
            "archived": "false",
            "tag_slug": slug,
            "closed": "false",
            "order": f"volume{timeframe}",
            "ascending": "false",
            "offset": 0,
        }

        url = f"{GAMMA_API_URL}/events/pagination"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            log.error(f"Gamma API error (trending markets): {e}")
            raise

        events = []

        for event in payload.get("data", []):
            try:
                mapped = self.map_api_to_event(event)
                events.append(SimpleEvent(**mapped))
            except Exception as e:
                log.warning(f"Event cast skipped: {e}")

        return events

    async def get_closing_soon_markets(
        self,
        hours: int = 24,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get markets closing within the next N hours."""
        markets = await self._clob_client.get_markets(f"active=true&archived=false&tag_slug=crypto&closed=false&order=volume24hr&ascending=false&offset=0&limit={limit}")
        now = datetime.utcnow()
        # maybe not close time and etc
        closing = []
        for m in markets:
            close_time = m.get("close_time") or m.get("closing_time") or m.get("end_time")
            if isinstance(close_time, str):
                try:
                    dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except Exception:
                    continue
            elif isinstance(close_time, datetime):
                dt = close_time
            else:
                continue
            delta_hours = (dt - now).total_seconds() / 3600
            if 0 <= delta_hours <= hours:
                closing.append(m)
        return closing[:limit]


    async def get_outcome_token_ids(
        self,
        market_id: Optional[str] = None,
        condition_id: Optional[str] = None,
        slug: Optional[str] = None,
        market_maker_address: Optional[str] = None,
    ) -> Dict[str, str]:
        """Get YES/NO token IDs for a market."""
        details = await self.get_market_details(
            market_id=market_id,
            condition_id=condition_id,
            slug=slug,
            market_maker_address=market_maker_address,
        )
        try:
            raw = details.clobTokenIds
        except Exception:
            raw = getattr(details, "clobTokenIds", None)
        if raw is None and isinstance(details, dict):
            raw = details.get("clobTokenIds") or details.get("clob_token_ids")
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, (list, tuple)) and len(parsed) >= 2:
            return {"YES": str(parsed[0]), "NO": str(parsed[1])}
        return {}

    def extract_outcome_token_ids(self, details: Any) -> Dict[str, str]:
        """Extract YES/NO token IDs from a market details object/dict."""
        if details is None:
            return {}
        try:
            # Pydantic model
            clob_token_ids = getattr(details, "clobTokenIds", None)
            if clob_token_ids is None and hasattr(details, "dict"):
                payload = details.dict()
                clob_token_ids = payload.get("clobTokenIds") or payload.get("clob_token_ids")
            if clob_token_ids is None and isinstance(details, dict):
                clob_token_ids = details.get("clobTokenIds") or details.get("clob_token_ids")
            if not clob_token_ids:
                return {}
            if isinstance(clob_token_ids, str):
                return json.loads(clob_token_ids)
            if isinstance(clob_token_ids, dict):
                return clob_token_ids
        except Exception:
            pass
        return {}
    
    # ========================================
    # Authenticated Trading Methods (requires CLOB client)
    # ========================================
    
    async def get_balance(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Get account balance (authenticated mode only).
        
        Args:
            token: Optional token address. If None, returns USDC balance.
        
        Returns:
            Balance information
        """
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated. Provide private_key and polygon_address to enable trading.")
        
        try:
            if token:
                balance = self._clob_client.get_balance(token)
            else:
                # Get USDC balance by default
                balance = self._clob_client.get_balance()
            
            log.debug(f"Balance retrieved: {balance}")
            return {"balance": balance, "token": token or "USDC"}
        except Exception as e:
            log.error(f"Failed to get balance: {e}")
            raise

    def get_address_for_private_key(self):
        account = self.w3.eth.account.from_key(str(self.private_key))
        return account.address

    def get_usdc_balance(self) -> float:
        balance_res = self.usdc.functions.balanceOf(
            self.get_address_for_private_key()
        ).call()
        return float(balance_res / 10e5)

    def get_eth_balance(self) -> float:
        """Get wallet native token balance (on-chain)."""
        if not self.web3:
            raise RuntimeError("Web3 not available. Install web3 and set POLYGON_RPC_URL.")
        if not self.polygon_address:
            raise RuntimeError("polygon_address not configured.")
        balance_res = self.web3.eth.get_balance(self.polygon_address)
        return float(Decimal(balance_res) / Decimal("1000000000000000000"))

    def get_polymarket_usdc_balance(self, token_id: str) -> Dict[str, Any]:
        """
        Returns Polymarket vault balance (free + locked).
        This is NOT wallet USDC.
        """
        if BalanceAllowanceParams is None or AssetType is None:
            raise RuntimeError("py-clob-client BalanceAllowanceParams not available.")
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated. Provide private_key to enable trading.")
        return self._clob_client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
        )

    def init_approvals(self, run: bool = False) -> None:
        if not run:
            return

        priv_key = self.private_key
        pub_key = self.get_address_for_private_key()
        chain_id = self.chain_id
        web3 = self.web3
        nonce = web3.eth.get_transaction_count(pub_key)
        usdc = self.usdc
        ctf = self.ctf

        # CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk Adapter
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)
    
    async def place_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        quantity: float,
        price: float,
        expiration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a limit order via low-level CLOB flow (authenticated mode only)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated. Provide private_key to enable trading.")

        try:
            side_upper = side.upper()
            if side_upper not in ("BUY", "SELL"):
                raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

            if OrderArgs is None or OrderType is None:
                raise RuntimeError("py-clob-client is not available for order placement.")
            # Prefer low-level create_order + post_order to avoid create_and_post_order issues.
            expiration_value = expiration or os.getenv("CLOB_ORDER_EXPIRATION") or "1000000000000"
            if ORDER_UTILS_AVAILABLE and self.exchange_address and self.private_key:
                signed_order = self.build_order(
                    market_token=str(token_id),
                    size=float(quantity),
                    price=float(price),
                    side=side_upper,
                    expiration=str(expiration_value),
                )
                resp = self._clob_client.post_order(signed_order, OrderType.GTD)
            else:
                order_args = OrderArgs(
                    price=float(price),
                    size=float(quantity),
                    side=BUY if side_upper == "BUY" else SELL,
                    token_id=str(token_id),
                    expiration=str(expiration_value),
                )
                if hasattr(self._clob_client, "create_order"):
                    signed_order = self._clob_client.create_order(order_args)
                    resp = self._clob_client.post_order(signed_order, OrderType.GTD)
                else:
                    resp = self._clob_client.create_and_post_order(order_args)
   

            log.info(f"Order placed: {side_upper} {quantity} @ {price} (token_id={token_id})")
            return resp if isinstance(resp, dict) else {"response": resp}
        except Exception as e:
            log.error(f"Failed to place order: {e}")
            raise


    def build_order(
        self,
        market_token: str,
        size: float,
        price: float,
        nonce: Optional[str] = None,
        side: str = "BUY",
        expiration: str = "0",
    ) -> Dict[str, Any]:
        """Build a signed order using low-level order utils."""
        if not ORDER_UTILS_AVAILABLE or OrderBuilder is None or OrderData is None or Signer is None:
            raise RuntimeError("py-order-utils not available for low-level order building.")
        if not self.private_key:
            raise RuntimeError("Private key required for low-level order building.")
        if not self.exchange_address:
            raise RuntimeError("Exchange address required for low-level order building.")
        maker = self.get_address_for_private_key()
        if not maker:
            raise RuntimeError("Unable to resolve signer address for low-level order building.")

        signer = Signer(self.private_key)
        builder = OrderBuilder(self.exchange_address, self.chain_id, signer)

        buy = side.upper() == "BUY"
        side_value = 0 if buy else 1
        size_d = Decimal(str(size))
        price_d = Decimal(str(price))
        quote_d = (size_d * price_d).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

        def _to_base_units(value: Decimal, decimals: int) -> int:
            scale = Decimal(10) ** Decimal(decimals)
            return int((value * scale).to_integral_value(rounding=ROUND_DOWN))

        size_base = _to_base_units(size_d, self.share_decimals)
        quote_base = _to_base_units(quote_d, self.usdc_decimals)
        # makerAmount/takerAmount must both be > 0
        if buy:
            maker_amount = quote_base
            taker_amount = size_base
        else:
            maker_amount = size_base
            taker_amount = quote_base

        order_data = OrderData(
            maker=maker,
            tokenId=market_token,
            makerAmount=str(maker_amount),
            takerAmount=str(taker_amount),
            feeRateBps="0",
            nonce=nonce or str(round(time.time())),
            side=side_value,
            expiration=expiration,
        )
        return builder.build_signed_order(order_data)
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order (authenticated mode only).
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            Cancellation result
        """
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        
        try:
            result = self._clob_client.cancel(order_id)
            log.info(f"Order cancelled: {order_id}")
            return result
        except Exception as e:
            log.error(f"Failed to cancel order: {e}")
            raise
    
    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders (authenticated mode only).
        
        Returns:
            List of open orders
        """
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        
        try:
            orders = self._clob_client.get_orders()
            log.debug(f"Retrieved {len(orders)} open orders")
            return orders
        except Exception as e:
            log.error(f"Failed to get orders: {e}")
            raise

    async def get_open_orders(
        self,
        market: Optional[str] = None,
        maker_address: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get open orders with optional filtering (py-clob-client OpenOrderParams)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        if OpenOrderParams is None:
            raise RuntimeError("py-clob-client OpenOrderParams unavailable.")

        try:
            if maker_address is None:
                params = OpenOrderParams(
                    market=market,
                    # taker=maker_address or self._clob_client.get_address(),
                )
                orders = self._clob_client.get_orders(params)
                log.debug(f"Retrieved {len(orders)} open orders (filtered)")
                return orders
            else :
                params = TradeParams(market=market, maker_address=maker_address)
                trades = self._clob_client.get_trades(params)
                return trades
        except Exception as e:
            log.error(f"Failed to get open orders: {e}")
            raise

    async def get_trades(
        self,
        market: Optional[str] = None,
        maker_address: Optional[str] = None,
        taker_address: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get trades (py-clob-client TradeParams)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        if TradeParams is None:
            raise RuntimeError("py-clob-client TradeParams unavailable.")

        try:
            params = TradeParams(
                maker_address=maker_address or self._clob_client.get_address(),
                market=market,
            )
            trades = self._clob_client.get_trades(params)
            log.debug(f"Retrieved {len(trades)} trades")
            return trades
        except Exception as e:
            log.error(f"Failed to get trades: {e}")
            raise

    async def get_price(self, token_id: str, side: str = "BUY") -> Dict[str, Any]:
        """Get best price for a token and side (py-clob-client get_price)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        try:
            result = self._clob_client.get_price(str(token_id), side.upper())
            return {"token_id": token_id, "side": side.upper(), "price": result}
        except Exception as e:
            log.error(f"Failed to get price: {e}")
            raise

    async def is_order_scoring(self, order_id: str) -> Dict[str, Any]:
        """Check if an order is scoring (py-clob-client OrderScoringParams)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        if OrderScoringParams is None:
            raise RuntimeError("py-clob-client OrderScoringParams unavailable.")

        try:
            scoring = self._clob_client.is_order_scoring(
                OrderScoringParams(orderId=order_id)
            )
            return {"order_id": order_id, "scoring": scoring}
        except Exception as e:
            log.error(f"Failed to check order scoring: {e}")
            raise

    async def get_readonly_api_keys(self) -> Dict[str, Any]:
        """Get readonly API keys (py-clob-client get_readonly_api_keys)."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        try:
            keys = self._clob_client.get_readonly_api_keys()
            return {"keys": keys}
        except Exception as e:
            log.error(f"Failed to get readonly API keys: {e}")
            raise
    
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details (authenticated mode only).
        
        Args:
            order_id: Order ID
        
        Returns:
            Order details
        """
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated.")
        
        try:
            order = self._clob_client.get_order(order_id)
            return order
        except Exception as e:
            log.error(f"Failed to get order: {e}")
            raise

    # Additional methods for authenticated trading can be added here (e.g., modify_order, get_position, etc.)
    def get_open_positions(self) -> Dict[str, Any]:
        """Get open positions (authenticated or readonly CLOB access).

        Returns:
            Dict mapping market_id -> list of open orders/positions.
        """
        try:
            # Prefer authenticated client if available
            if self.is_authenticated:
                orders = self._clob_client.get_orders()
            else:
                host = self.host or os.getenv("CLOB_API_URL", CLOB_API_URL)
                address = self.polygon_address or os.getenv("POLYGON_ADDRESS") or settings.polygon_address
                readonly_api_key = os.getenv("CLOB_READONLY_API_KEY")
                if not readonly_api_key or not address:
                    log.warning(
                        "Readonly CLOB access not configured (missing CLOB_READONLY_API_KEY or address)."
                    )
                    return {}

                response = httpx.get(
                    f"{host}{ORDERS}",
                    headers={
                        "POLY_READONLY_API_KEY": readonly_api_key,
                        "POLY_ADDRESS": address,
                        "Content-Type": "application/json",
                    },
                    params={"maker_address": address},
                    follow_redirects=True,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                orders = response.json()

            if isinstance(orders, dict) and "data" in orders and isinstance(orders["data"], list):
                orders = orders["data"]
            if not isinstance(orders, list):
                log.warning("Unexpected open orders response format: %s", type(orders).__name__)
                return {}

            positions_by_market: Dict[str, List[Dict[str, Any]]] = {}
            for order in orders:
                market_id = order.get("market") or order.get("market_id")
                if not market_id:
                    continue
                positions_by_market.setdefault(str(market_id), []).append(order)

            log.debug("Retrieved %d markets with open positions", len(positions_by_market))
            return positions_by_market
        except Exception as exc:
            log.error(f"Failed to get open positions: {exc}")
            return {}

    def get_open_position(self, market_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get open positions for a single market_id."""
        if not market_id:
            return None
        positions = self.get_open_positions()
        return positions.get(str(market_id))
