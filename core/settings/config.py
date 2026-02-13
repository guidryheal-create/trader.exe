"""
Configuration management for the Agentic Trading System.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Union, TYPE_CHECKING
from pydantic import Field, ConfigDict, model_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from core.models.chain import (
    CHAIN_KEY_BY_ID,
    DEFAULT_PERMIT2,
    TRADING_CHAIN_CONFIGS,
    ChainConfig,
)
import json

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Load environment variables from .env file if it exists (for Windows debugging)
try:
    from dotenv import load_dotenv
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file, override=False)  # Don't override existing env vars
    else:
        # Fallback to .env in project root
        load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    # python-dotenv not installed, pydantic-settings will handle env vars
    pass

if TYPE_CHECKING:
    from core.models.base import AgentType

CHAIN_CONFIGS: dict[str, ChainConfig] = TRADING_CHAIN_CONFIGS
ROUTER_ADDRESSES: dict[str, str] = {
    name: chain_config.universal_router for name, chain_config in CHAIN_CONFIGS.items()
}
CHAIN_BY_ID: dict[int, str] = dict(CHAIN_KEY_BY_ID)
ETHEREUM_MAINNET: ChainConfig = CHAIN_CONFIGS["ethereum"]


def get_chain_config(chain: str | int | None) -> ChainConfig | None:
    """Return chain configuration by chain name or chain id."""
    if chain is None:
        return None
    if isinstance(chain, int):
        chain_key = CHAIN_BY_ID.get(chain)
        return CHAIN_CONFIGS.get(chain_key) if chain_key else None
    return CHAIN_CONFIGS.get(chain.strip().lower())

UNIVERSAL_ROUTER_EXECUTE_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
]

V3_QUOTER_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        extra="ignore",
        env_ignore_empty=True,
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
    )
    
    # API Configuration
    app_name: str = "Agentic Trading System"
    app_version: str = "1.0.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    cors_origins: str = Field(
        default="https://forecasting.guidry-cloud.com,https://www.forecasting.guidry-cloud.com,http://localhost:3000,http://localhost:5173",
        validation_alias="CORS_ORIGINS"
    )
    
    # Redis Configuration
    redis_host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(default=0, validation_alias="REDIS_DB")
    
    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(default="trading_system", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="trading_user", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="trading_pass", validation_alias="POSTGRES_PASSWORD")

    CHAIN_CONFIGS: ClassVar[dict[str, ChainConfig]] = CHAIN_CONFIGS
    ROUTER_ADDRESSES: ClassVar[dict[str, str]] = ROUTER_ADDRESSES

    # ✅ Universal Router ABI (Stored as JSON String)
    UNIVERSAL_ROUTER_ABI_JSON: ClassVar[str] = "[{\"inputs\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"permit2\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"weth9\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"v2Factory\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"v3Factory\",\"type\":\"address\"},{\"internalType\":\"bytes32\",\"name\":\"pairInitCodeHash\",\"type\":\"bytes32\"},{\"internalType\":\"bytes32\",\"name\":\"poolInitCodeHash\",\"type\":\"bytes32\"},{\"internalType\":\"address\",\"name\":\"v4PoolManager\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"v3NFTPositionManager\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"v4PositionManager\",\"type\":\"address\"}],\"internalType\":\"struct RouterParameters\",\"name\":\"params\",\"type\":\"tuple\"}],\"stateMutability\":\"nonpayable\",\"type\":\"constructor\"},{\"inputs\":[],\"name\":\"BalanceTooLow\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"ContractLocked\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"Currency\",\"name\":\"currency\",\"type\":\"address\"}],\"name\":\"DeltaNotNegative\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"Currency\",\"name\":\"currency\",\"type\":\"address\"}],\"name\":\"DeltaNotPositive\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"ETHNotAccepted\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"commandIndex\",\"type\":\"uint256\"},{\"internalType\":\"bytes\",\"name\":\"message\",\"type\":\"bytes\"}],\"name\":\"ExecutionFailed\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"FromAddressIsNotOwner\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InputLengthMismatch\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InsufficientBalance\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InsufficientETH\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InsufficientToken\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"bytes4\",\"name\":\"action\",\"type\":\"bytes4\"}],\"name\":\"InvalidAction\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidBips\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"commandType\",\"type\":\"uint256\"}],\"name\":\"InvalidCommandType\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidEthSender\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidPath\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidReserves\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"LengthMismatch\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"tokenId\",\"type\":\"uint256\"}],\"name\":\"NotAuthorizedForToken\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"NotPoolManager\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"OnlyMintAllowed\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"SliceOutOfBounds\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"TransactionDeadlinePassed\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"UnsafeCast\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"action\",\"type\":\"uint256\"}],\"name\":\"UnsupportedAction\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V2InvalidPath\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V2TooLittleReceived\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V2TooMuchRequested\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3InvalidAmountOut\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3InvalidCaller\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3InvalidSwap\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3TooLittleReceived\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3TooMuchRequested\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"minAmountOutReceived\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"amountReceived\",\"type\":\"uint256\"}],\"name\":\"V4TooLittleReceived\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"maxAmountInRequested\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"amountRequested\",\"type\":\"uint256\"}],\"name\":\"V4TooMuchRequested\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"V3_POSITION_MANAGER\",\"outputs\":[{\"internalType\":\"contract INonfungiblePositionManager\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"V4_POSITION_MANAGER\",\"outputs\":[{\"internalType\":\"contract IPositionManager\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"bytes\",\"name\":\"commands\",\"type\":\"bytes\"},{\"internalType\":\"bytes[]\",\"name\":\"inputs\",\"type\":\"bytes[]\"}],\"name\":\"execute\",\"outputs\":[],\"stateMutability\":\"payable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"bytes\",\"name\":\"commands\",\"type\":\"bytes\"},{\"internalType\":\"bytes[]\",\"name\":\"inputs\",\"type\":\"bytes[]\"},{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"name\":\"execute\",\"outputs\":[],\"stateMutability\":\"payable\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"msgSender\",\"outputs\":[{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"poolManager\",\"outputs\":[{\"internalType\":\"contract IPoolManager\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"int256\",\"name\":\"amount0Delta\",\"type\":\"int256\"},{\"internalType\":\"int256\",\"name\":\"amount1Delta\",\"type\":\"int256\"},{\"internalType\":\"bytes\",\"name\":\"data\",\"type\":\"bytes\"}],\"name\":\"uniswapV3SwapCallback\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"bytes\",\"name\":\"data\",\"type\":\"bytes\"}],\"name\":\"unlockCallback\",\"outputs\":[{\"internalType\":\"bytes\",\"name\":\"\",\"type\":\"bytes\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"stateMutability\":\"payable\",\"type\":\"receive\"}]"

    # ✅ Permit2 ABI (Stored as JSON String)
    PERMIT2_ABI_JSON: ClassVar[str] = "[{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"name\":\"AllowanceExpired\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"ExcessiveInvalidation\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"name\":\"InsufficientAllowance\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"maxAmount\",\"type\":\"uint256\"}],\"name\":\"InvalidAmount\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidContractSignature\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidNonce\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidSignature\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidSignatureLength\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"InvalidSigner\",\"type\":\"error\"},{\"inputs\":[],\"name\":\"LengthMismatch\",\"type\":\"error\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"signatureDeadline\",\"type\":\"uint256\"}],\"name\":\"SignatureExpired\",\"type\":\"error\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"indexed\":false,\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"}],\"name\":\"Approval\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"}],\"name\":\"Lockdown\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint48\",\"name\":\"newNonce\",\"type\":\"uint48\"},{\"indexed\":false,\"internalType\":\"uint48\",\"name\":\"oldNonce\",\"type\":\"uint48\"}],\"name\":\"NonceInvalidation\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"indexed\":false,\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"},{\"indexed\":false,\"internalType\":\"uint48\",\"name\":\"nonce\",\"type\":\"uint48\"}],\"name\":\"Permit\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"word\",\"type\":\"uint256\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"mask\",\"type\":\"uint256\"}],\"name\":\"UnorderedNonceInvalidation\",\"type\":\"event\"},{\"inputs\":[],\"name\":\"DOMAIN_SEPARATOR\",\"outputs\":[{\"internalType\":\"bytes32\",\"name\":\"\",\"type\":\"bytes32\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"}],\"name\":\"allowance\",\"outputs\":[{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"},{\"internalType\":\"uint48\",\"name\":\"nonce\",\"type\":\"uint48\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"}],\"name\":\"approve\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint48\",\"name\":\"newNonce\",\"type\":\"uint48\"}],\"name\":\"invalidateNonces\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"uint256\",\"name\":\"wordPos\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"mask\",\"type\":\"uint256\"}],\"name\":\"invalidateUnorderedNonces\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"}],\"internalType\":\"struct IAllowanceTransfer.TokenSpenderPair[]\",\"name\":\"approvals\",\"type\":\"tuple[]\"}],\"name\":\"lockdown\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"\",\"type\":\"uint256\"}],\"name\":\"nonceBitmap\",\"outputs\":[{\"internalType\":\"uint256\",\"name\":\"\",\"type\":\"uint256\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"},{\"internalType\":\"uint48\",\"name\":\"nonce\",\"type\":\"uint48\"}],\"internalType\":\"struct IAllowanceTransfer.PermitDetails[]\",\"name\":\"details\",\"type\":\"tuple[]\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"sigDeadline\",\"type\":\"uint256\"}],\"internalType\":\"struct IAllowanceTransfer.PermitBatch\",\"name\":\"permitBatch\",\"type\":\"tuple\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permit\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"uint48\",\"name\":\"expiration\",\"type\":\"uint48\"},{\"internalType\":\"uint48\",\"name\":\"nonce\",\"type\":\"uint48\"}],\"internalType\":\"struct IAllowanceTransfer.PermitDetails\",\"name\":\"details\",\"type\":\"tuple\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"sigDeadline\",\"type\":\"uint256\"}],\"internalType\":\"struct IAllowanceTransfer.PermitSingle\",\"name\":\"permitSingle\",\"type\":\"tuple\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permit\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.TokenPermissions\",\"name\":\"permitted\",\"type\":\"tuple\"},{\"internalType\":\"uint256\",\"name\":\"nonce\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.PermitTransferFrom\",\"name\":\"permit\",\"type\":\"tuple\"},{\"components\":[{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"requestedAmount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.SignatureTransferDetails\",\"name\":\"transferDetails\",\"type\":\"tuple\"},{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permitTransferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.TokenPermissions[]\",\"name\":\"permitted\",\"type\":\"tuple[]\"},{\"internalType\":\"uint256\",\"name\":\"nonce\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.PermitBatchTransferFrom\",\"name\":\"permit\",\"type\":\"tuple\"},{\"components\":[{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"requestedAmount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.SignatureTransferDetails[]\",\"name\":\"transferDetails\",\"type\":\"tuple[]\"},{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permitTransferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.TokenPermissions\",\"name\":\"permitted\",\"type\":\"tuple\"},{\"internalType\":\"uint256\",\"name\":\"nonce\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.PermitTransferFrom\",\"name\":\"permit\",\"type\":\"tuple\"},{\"components\":[{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"requestedAmount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.SignatureTransferDetails\",\"name\":\"transferDetails\",\"type\":\"tuple\"},{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"internalType\":\"bytes32\",\"name\":\"witness\",\"type\":\"bytes32\"},{\"internalType\":\"string\",\"name\":\"witnessTypeString\",\"type\":\"string\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permitWitnessTransferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.TokenPermissions[]\",\"name\":\"permitted\",\"type\":\"tuple[]\"},{\"internalType\":\"uint256\",\"name\":\"nonce\",\"type\":\"uint256\"},{\"internalType\":\"uint256\",\"name\":\"deadline\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.PermitBatchTransferFrom\",\"name\":\"permit\",\"type\":\"tuple\"},{\"components\":[{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"requestedAmount\",\"type\":\"uint256\"}],\"internalType\":\"struct ISignatureTransfer.SignatureTransferDetails[]\",\"name\":\"transferDetails\",\"type\":\"tuple[]\"},{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"internalType\":\"bytes32\",\"name\":\"witness\",\"type\":\"bytes32\"},{\"internalType\":\"string\",\"name\":\"witnessTypeString\",\"type\":\"string\"},{\"internalType\":\"bytes\",\"name\":\"signature\",\"type\":\"bytes\"}],\"name\":\"permitWitnessTransferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"components\":[{\"internalType\":\"address\",\"name\":\"from\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"}],\"internalType\":\"struct IAllowanceTransfer.AllowanceTransferDetails[]\",\"name\":\"transferDetails\",\"type\":\"tuple[]\"}],\"name\":\"transferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"from\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"internalType\":\"uint160\",\"name\":\"amount\",\"type\":\"uint160\"},{\"internalType\":\"address\",\"name\":\"token\",\"type\":\"address\"}],\"name\":\"transferFrom\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"}]"

    # ✅ generic ERC20 Token ABI (Stored as JSON String)
    ERC20_ABI_JSON: ClassVar[str] = "[{\"inputs\":[{\"internalType\":\"address\",\"name\":\"_l2Bridge\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"_l1Token\",\"type\":\"address\"},{\"internalType\":\"string\",\"name\":\"_name\",\"type\":\"string\"},{\"internalType\":\"string\",\"name\":\"_symbol\",\"type\":\"string\"}],\"stateMutability\":\"nonpayable\",\"type\":\"constructor\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"value\",\"type\":\"uint256\"}],\"name\":\"Approval\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"_account\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"_amount\",\"type\":\"uint256\"}],\"name\":\"Burn\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"_account\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"_amount\",\"type\":\"uint256\"}],\"name\":\"Mint\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"internalType\":\"address\",\"name\":\"from\",\"type\":\"address\"},{\"indexed\":true,\"internalType\":\"address\",\"name\":\"to\",\"type\":\"address\"},{\"indexed\":false,\"internalType\":\"uint256\",\"name\":\"value\",\"type\":\"uint256\"}],\"name\":\"Transfer\",\"type\":\"event\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"owner\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"}],\"name\":\"allowance\",\"outputs\":[{\"internalType\":\"uint256\",\"name\":\"\",\"type\":\"uint256\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"name\":\"approve\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"account\",\"type\":\"address\"}],\"name\":\"balanceOf\",\"outputs\":[{\"internalType\":\"uint256\",\"name\":\"\",\"type\":\"uint256\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"_from\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"_amount\",\"type\":\"uint256\"}],\"name\":\"burn\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"decimals\",\"outputs\":[{\"internalType\":\"uint8\",\"name\":\"\",\"type\":\"uint8\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"subtractedValue\",\"type\":\"uint256\"}],\"name\":\"decreaseAllowance\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"spender\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"addedValue\",\"type\":\"uint256\"}],\"name\":\"increaseAllowance\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"l1Token\",\"outputs\":[{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"l2Bridge\",\"outputs\":[{\"internalType\":\"address\",\"name\":\"\",\"type\":\"address\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"_to\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"_amount\",\"type\":\"uint256\"}],\"name\":\"mint\",\"outputs\":[],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"name\",\"outputs\":[{\"internalType\":\"string\",\"name\":\"\",\"type\":\"string\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"bytes4\",\"name\":\"_interfaceId\",\"type\":\"bytes4\"}],\"name\":\"supportsInterface\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"pure\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"symbol\",\"outputs\":[{\"internalType\":\"string\",\"name\":\"\",\"type\":\"string\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[],\"name\":\"totalSupply\",\"outputs\":[{\"internalType\":\"uint256\",\"name\":\"\",\"type\":\"uint256\"}],\"stateMutability\":\"view\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"recipient\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"name\":\"transfer\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[{\"internalType\":\"address\",\"name\":\"sender\",\"type\":\"address\"},{\"internalType\":\"address\",\"name\":\"recipient\",\"type\":\"address\"},{\"internalType\":\"uint256\",\"name\":\"amount\",\"type\":\"uint256\"}],\"name\":\"transferFrom\",\"outputs\":[{\"internalType\":\"bool\",\"name\":\"\",\"type\":\"bool\"}],\"stateMutability\":\"nonpayable\",\"type\":\"function\"}]"

    # ✅ Convert JSON ABIs into Python Objects
    UNIVERSAL_ROUTER_ABI: ClassVar[list[dict[str, Any]]] = json.loads(UNIVERSAL_ROUTER_ABI_JSON)
    PERMIT2_ABI: ClassVar[list[dict[str, Any]]] = json.loads(PERMIT2_ABI_JSON)
    ERC20_ABI: ClassVar[list[dict[str, Any]]] = json.loads(ERC20_ABI_JSON)
    
    # External APIs
    # Default is external URL for local development, overridden by Docker env to internal service
    mcp_api_url: str = Field(default="https://forecasting.guidry-cloud.com/mcp", validation_alias="MCP_API_URL")
    mcp_api_key: Optional[str] = Field(default="sk_jDHFvVDCU8bF4caeenG96jnKbYIET4wcDm3qBzNWXVc", validation_alias="MCP_API_KEY")
    dex_simulator_url: str = Field(default="http://localhost:8001", validation_alias="DEX_SIMULATOR_URL")
    cmc_api_key: Optional[str] = Field(default=None, validation_alias="CMC_API_KEY")
    asknews_api_key: Optional[str] = Field(default=None, validation_alias="ASKNEWS_API_KEY")
    news_api_key: Optional[str] = Field(default=None, validation_alias="NEWS_API")
    sentiment_api_key: Optional[str] = Field(default=None, validation_alias="SENTIMENT_API")
    
    # Blockscout MCP Configuration
    blockscout_mcp_url: Optional[str] = Field(
        default="https://mcp.blockscout.com/mcp",
        validation_alias="BLOCKSCOUT_MCP_URL"
    )
    
    # Yahoo Finance MCP Configuration
    yahoo_finance_mcp_command: str = Field(
        default="uvx",
        validation_alias="YAHOO_FINANCE_MCP_COMMAND"
    )
    yahoo_finance_mcp_args: str = Field(
        default='["mcp-yahoo-finance"]',
        validation_alias="YAHOO_FINANCE_MCP_ARGS"
    )
    
    # YouTube Transcript MCP Configuration
    youtube_transcript_mcp_command: str = Field(
        default="npx",
        validation_alias="YOUTUBE_TRANSCRIPT_MCP_COMMAND"
    )
    youtube_transcript_mcp_args: str = Field(
        default='["-y", "@sinco-lab/mcp-youtube-transcript"]',
        validation_alias="YOUTUBE_TRANSCRIPT_MCP_ARGS"
    )
    
    # Mock services
    use_mock_services: bool = Field(default=False, validation_alias="USE_MOCK_SERVICES")

    # Forecasting mode: "mcp" | "api" | "mock" | "disabled"
    # - mcp/api: use forecasting API (MCP or REST)
    # - mock: use mock forecasting service
    # - disabled: skip forecasting entirely (standalone Polymarket mode)
    forecasting_mode: Literal["mcp", "api", "mock", "disabled"] = Field(
        default="api",
        validation_alias="FORECASTING_MODE",
    )
    
    # Exchange API Keys
    mexc_api_key: Optional[str] = Field(default=None, validation_alias="MEXC_API_KEY")
    mexc_secret_key: Optional[str] = Field(default=None, validation_alias="MEXC_SECRET_KEY")
    
    # DEX Configuration
    private_key: Optional[str] = Field(default=None, validation_alias="PRIVATE_KEY")
    wallet_address: Optional[str] = Field(default=None, validation_alias="WALLET_ADDRESS")

    # Polymarket Configuration
    polygon_private_key: Optional[str] = Field(default=None, validation_alias="POLYGON_PRIVATE_KEY")
    polygon_address: Optional[str] = Field(default=None, validation_alias="POLYGON_ADDRESS")
    polymarket_chain_id: int = Field(default=80002, validation_alias="POLYMARKET_CHAIN_ID")
    
    # LLM Configuration
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, validation_alias="OPENAI_BASE_URL")
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    vllm_endpoint: Optional[str] = Field(default="http://localhost:8002/v1", validation_alias="VLLM_ENDPOINT")
    
    # CAMEL Configuration (default to gpt-5-mini for lower cost)
    camel_default_model: str = Field(default="auto", validation_alias="CAMEL_DEFAULT_MODEL")
    camel_coordinator_model: str = Field(default="auto", validation_alias="CAMEL_COORDINATOR_MODEL")
    camel_task_model: str = Field(default="auto", validation_alias="CAMEL_TASK_MODEL")
    camel_worker_model: str = Field(default="auto", validation_alias="CAMEL_WORKER_MODEL")
    camel_primary_model: str = Field(default="openai/gpt-5-mini", validation_alias="CAMEL_PRIMARY_MODEL")  
    camel_fallback_model: str = Field(default="openai/gpt-5-mini", validation_alias="CAMEL_FALLBACK_MODEL")  
    camel_prefer_gemini: bool = Field(default=False, validation_alias="CAMEL_PREFER_GEMINI")
    
    # Qdrant Configuration
    qdrant_host: str = Field(default="localhost", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, validation_alias="QDRANT_PORT")
    qdrant_collection_name: str = Field(default="trading_memory", validation_alias="QDRANT_COLLECTION_NAME")

    # Neo4j Configuration
    # Note: NEO4J_AUTH (format: "user/password") can be used instead of NEO4J_USER/NEO4J_PASSWORD
    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")
    
    # Memory Configuration
    # Chat history limit: maximum number of messages stored per user (default: 100)
    memory_chat_history_limit: int = Field(default=100, validation_alias="MEMORY_CHAT_HISTORY_LIMIT")
    # Chat daily limit: maximum number of messages per user per day (default: 10)
    chat_daily_message_limit: int = Field(default=10, validation_alias="CHAT_DAILY_MESSAGE_LIMIT")
    memory_retrieve_limit: int = Field(default=3, validation_alias="MEMORY_RETRIEVE_LIMIT")
    memory_token_limit: int = Field(default=4096, validation_alias="MEMORY_TOKEN_LIMIT")
    memory_embedding_model: str = Field(default="nomic-embed-text", validation_alias="MEMORY_EMBEDDING_MODEL")
    memory_embedding_provider: str = Field(default="ollama", validation_alias="MEMORY_EMBEDDING_PROVIDER")  # "ollama" or "openai"
    memory_prune_limit: int = Field(default=100, validation_alias="MEMORY_PRUNE_LIMIT")
    memory_prune_similarity_threshold: float = Field(default=0.82, validation_alias="MEMORY_PRUNE_SIMILARITY_THRESHOLD")
    review_interval_hours: int = Field(default=24, validation_alias="REVIEW_INTERVAL_HOURS")
    review_prompt_default: str = Field(
        default="Review recent agent performance, adjust coordination weights to maximize risk-adjusted returns, and surface rationale for any changes. Keep weights normalized to 1.0.",
        validation_alias="REVIEW_PROMPT_DEFAULT",
    )
    news_llm_model: str = Field(default="openai/gpt-5-mini", validation_alias="NEWS_LLM_MODEL")
    
    # Ollama Configuration
    # Default: localhost for local development (Docker override with http://ollama:11434)
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_URL")
    ollama_model: str = Field(default="nomic-embed-text", validation_alias="OLLAMA_MODEL")
    
    # Blockchain RPC URLs
    bsc_rpc_url: str = Field(default="https://bsc-dataseed.binance.org/", validation_alias="BSC_RPC_URL")
    eth_rpc_url: str = Field(default="https://eth.llamarpc.com", validation_alias="ETH_RPC_URL")
    sol_rpc_url: str = Field(default="https://api.mainnet-beta.solana.com", validation_alias="SOL_RPC_URL")
    uniswap_subgraph_url: Optional[str] = Field(default=None, validation_alias="UNISWAP_SUBGRAPH_URL")
    polywhaler_market_data_url: str = Field(
        default="https://www.polywhaler.com/api/market-data",
        validation_alias="POLYWHALER_MARKET_DATA_URL",
    )
    watchlist_enabled: bool = Field(default=True, validation_alias="WATCHLIST_ENABLED")
    watchlist_scan_seconds: int = Field(default=60, validation_alias="WATCHLIST_SCAN_SECONDS")
    watchlist_trigger_pct: float = Field(default=0.05, validation_alias="WATCHLIST_TRIGGER_PCT")
    watchlist_fast_trigger_pct: float = Field(default=0.10, validation_alias="WATCHLIST_FAST_TRIGGER_PCT")
    watchlist_global_roi_trigger_enabled: bool = Field(default=True, validation_alias="WATCHLIST_GLOBAL_ROI_TRIGGER_ENABLED")
    watchlist_global_roi_trigger_pct: float = Field(default=0.04, validation_alias="WATCHLIST_GLOBAL_ROI_TRIGGER_PCT")
    watchlist_global_roi_fast_trigger_pct: float = Field(default=0.08, validation_alias="WATCHLIST_GLOBAL_ROI_FAST_TRIGGER_PCT")
    dex_trader_cycle_hours: int = Field(default=4, validation_alias="DEX_TRADER_CYCLE_HOURS")
    dex_trader_token_exploration_limit: int = Field(default=20, validation_alias="DEX_TRADER_TOKEN_EXPLORATION_LIMIT")
    dex_simulator_fallback_enabled: bool = Field(default=True, validation_alias="DEX_SIMULATOR_FALLBACK_ENABLED")
    dex_wallet_review_cache_seconds: int = Field(default=3600, validation_alias="DEX_WALLET_REVIEW_CACHE_SECONDS")
    dex_strategy_hint_interval_hours: int = Field(default=6, validation_alias="DEX_STRATEGY_HINT_INTERVAL_HOURS")
    auto_enhancement_enabled: bool = Field(default=True, validation_alias="AUTO_ENHANCEMENT_ENABLED")
    
    # Trading Configuration
    initial_capital: float = Field(default=1000.0, validation_alias="INITIAL_CAPITAL")
    max_position_size: float = Field(default=0.20, validation_alias="MAX_POSITION_SIZE")  # 20% max per asset
    max_daily_loss: float = Field(default=0.05, validation_alias="MAX_DAILY_LOSS")  # 5% max daily loss
    max_drawdown: float = Field(default=0.15, validation_alias="MAX_DRAWDOWN")  # 15% max drawdown
    trading_fee: float = Field(default=0.001, validation_alias="TRADING_FEE")  # 0.1% trading fee
    min_confidence: float = Field(default=0.0, validation_alias="MIN_CONFIDENCE")  # Minimum confidence for DQN trades
    trade_reward_window_seconds: int = Field(default=3600, validation_alias="TRADE_REWARD_WINDOW_SECONDS")
    trade_reward_min_confidence: float = Field(default=0.0, validation_alias="TRADE_REWARD_MIN_CONFIDENCE")
    trade_reward_max_pending: int = Field(default=500, validation_alias="TRADE_REWARD_MAX_PENDING")
    trade_reward_price_source: str = Field(default="chart", validation_alias="TRADE_REWARD_PRICE_SOURCE")
    deep_search_api_url: Optional[str] = Field(default=None, validation_alias="DEEP_SEARCH_API_URL")
    deep_search_api_key: Optional[str] = Field(default=None, validation_alias="DEEP_SEARCH_API_KEY")
    deep_search_sources: List[str] = Field(
        default_factory=lambda: ["coindesk", "cointelegraph", "decrypt"]
    )
    news_source_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "yahoo_finance": 0.35,
            "coin_bureau": 0.25,
            "arxiv": 0.20,
            "google_scholar": 0.20,
        },
        validation_alias="NEWS_SOURCE_WEIGHTS",
    )
    arxiv_enabled: bool = Field(default=True, validation_alias="ARXIV_ENABLED")
    deep_research_mcp_url: Optional[str] = Field(default=None, validation_alias="DEEP_RESEARCH_MCP_URL")
    deep_research_depth: int = Field(default=2, validation_alias="DEEP_RESEARCH_DEPTH")
    deep_research_breadth: int = Field(default=2, validation_alias="DEEP_RESEARCH_BREADTH")
    deep_research_model: Optional[str] = Field(default=None, validation_alias="DEEP_RESEARCH_MODEL")
    deep_research_source_preferences: Optional[str] = Field(default=None, validation_alias="DEEP_RESEARCH_SOURCE_PREFERENCES")
    deep_research_timeout_seconds: int = Field(default=120, validation_alias="DEEP_RESEARCH_TIMEOUT_SECONDS")
    agent_instance_id: str = Field(
        default_factory=lambda: os.getenv("AGENT_INSTANCE_ID")
        or os.getenv("HOSTNAME")
        or "agent-instance-1",
        validation_alias="AGENT_INSTANCE_ID",
    )
    cluster_name: str = Field(default="local-cluster", validation_alias="CLUSTER_NAME")
    
    # Supported Assets
    supported_assets: List[str] = [
        "AAVE", "ADA", "AXS", "BTC", "CRO", "DOGE", "ETH", 
        "GALA", "IMX", "MANA", "PEPE", "POPCAT", "SAND", "SOL", "SUI"
    ]
    manual_disabled_assets: List[str] = Field(default_factory=list)
    
    # Asset Risk Tiers (for position sizing)
    tier_1_assets: List[str] = ["BTC", "ETH", "SOL"]  # Major cryptos - higher allocation allowed
    tier_2_assets: List[str] = ["ADA", "AAVE", "CRO"]  # Mid-cap - moderate allocation
    tier_3_assets: List[str] = ["DOGE", "MANA", "SAND", "GALA", "AXS", "IMX", "SUI"]  # Higher risk
    tier_4_assets: List[str] = ["PEPE", "POPCAT"]  # Meme coins - lowest allocation
    
    # Trading Intervals
    observation_interval: str = "minutes"  # Observe market behavior
    decision_interval: str = "hours"  # Make trading decisions
    forecast_interval: str = "days"  # Long-term forecasting
    
    # Agent Configuration
    agent_heartbeat_interval: int = 30  # seconds
    agent_timeout: int = 300  # seconds
    agent_schedule_profile: str = Field(default="minutes", validation_alias="AGENT_SCHEDULE_PROFILE")
    agent_schedule_profiles: Dict[str, Dict[str, int]] = Field(
        default_factory=lambda: {
            "minutes": {
                "memory": 600,
                "dqn": 300,
                "chart": 300,
                "risk": 120,
                "news": 900,
                "copytrade": 180,
                "orchestrator": 300,
                "workforce": 300,
            },
            "hours": {
                "memory": 3600,
                "dqn": 1800,
                "chart": 1800,
                "risk": 1200,
                "news": 3600,
                "copytrade": 900,
                "orchestrator": 1800,
                "workforce": 1800,
            },
            "days": {
                "memory": 21600,
                "dqn": 14400,
                "chart": 10800,
                "risk": 7200,
                "news": 43200,
                "copytrade": 3600,
                "orchestrator": 14400,
                "workforce": 14400,
            },
        }
    )
    pipeline_live_defaults: Dict[str, Dict[str, Union[bool, str]]] = Field(
        default_factory=lambda: {
            "trend": {"enabled": True, "interval": "hours"},
            "fact": {"enabled": True, "interval": "hours"},
            "fusion": {"enabled": True, "interval": "hours"},
            "prune": {"enabled": True, "interval": "days"},
        }
    )
    pipeline_live_interval_seconds: Dict[str, Dict[str, int]] = Field(
        default_factory=lambda: {
            "trend": {"hours": 1800, "days": 10800},
            "fact": {"hours": 3600, "days": 14400},
            "fusion": {"hours": 1800, "days": 7200},
            "prune": {"hours": 7200, "days": 86400},
        }
    )
    agent_cycle_overrides: Dict[str, int] = Field(default_factory=dict, validation_alias="AGENT_CYCLE_OVERRIDES")
    default_agent_cycle_seconds: int = Field(default=300, validation_alias="DEFAULT_AGENT_CYCLE_SECONDS")
    
    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: str = Field(default="/app/logs/trading_system.log", validation_alias="LOG_FILE")
    logfire_token: Optional[str] = Field(default=None, validation_alias="LOGFIRE_TOKEN")
    log_redis_enabled: bool = Field(default=True, validation_alias="LOG_REDIS_ENABLED")
    log_redis_list_key: str = Field(default="logs:recent", validation_alias="LOG_REDIS_LIST_KEY")
    log_redis_max_entries: int = Field(default=1000, validation_alias="LOG_REDIS_MAX_ENTRIES")

    @model_validator(mode="after")
    def _apply_api_key_aliases(self) -> "Settings":
        """Populate API keys from alternate environment variable names when provided."""
        if not self.gemini_api_key:
            alias = (
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GOOGLE_STUDIO_API_KEY")
                or os.getenv("GOOGLE_GENAI_API_KEY")
                or os.getenv("GEMINI_APIKEY")
                or os.getenv("GEMINI_API_KEY")
            )
            if alias:
                self.gemini_api_key = alias.strip()

        # If no Gemini key available, ensure CAMEL defaults fall back to GPT
        if not self.gemini_api_key:
            self.camel_prefer_gemini = False

        def _ensure_openai_model(model_name: Optional[str]) -> str:
            value = (model_name or "").strip()
            if not value:
                return "openai/gpt-5-mini"
            lower = value.lower()
            if lower.startswith("openai/"):
                return value
            if lower.startswith("gpt"):
                return f"openai/{value}"
            if lower.startswith("gemini") and not self.gemini_api_key:
                return "openai/gpt-5-mini"
            # ✅ Support gpt-4.1-mini as rate limit fallback
            if "gpt-4.1-mini" in lower:
                return "openai/gpt-5-mini"
            return value

        self.camel_primary_model = _ensure_openai_model(self.camel_primary_model)
        self.camel_fallback_model = _ensure_openai_model(self.camel_fallback_model)
        self.news_llm_model = _ensure_openai_model(self.news_llm_model)

        # ✅ Ensure gpt-5-mini is used (user preference) - don't downgrade to gpt-5-mini
        if self.camel_primary_model.lower().startswith("openrouter"):
            self.camel_primary_model = "openai/gpt-5-mini"  # Use gpt-5-mini instead of mini
        # Only downgrade if explicitly set to mini or if no model specified
        if self.camel_primary_model == "openai/gpt-5-mini" and not os.getenv("CAMEL_PRIMARY_MODEL"):
            # If default was used and it's mini, upgrade to gpt-5-mini
            self.camel_primary_model = "openai/gpt-5-mini"
        if self.camel_fallback_model.lower().startswith("openrouter"):
            self.camel_fallback_model = "openai/gpt-5-mini"  # Use gpt-5-mini instead of mini
        if self.news_llm_model.lower().startswith("openrouter"):
            self.news_llm_model = "openai/gpt-5-mini"

        disabled_env = os.getenv("DISABLED_ASSETS")
        if disabled_env:
            self.manual_disabled_assets = [
                entry.strip().upper()
                for entry in disabled_env.split(",")
                if entry.strip()
            ]

        return self

    @model_validator(mode="after")
    def _validate_mcp_endpoints(self) -> "Settings":
        """Ensure MCP endpoints/keys are usable in the running container."""
        try:
            from core.logging import log
        except Exception:
            log = None

        def warn(msg: str):
            if log:
                log.warning(msg)
            else:
                print(msg)

        # Force external MCP URL if a docker-internal hostname is detected
        if self.mcp_api_url and ("http://ats-trading-api" in self.mcp_api_url or "http://forecasting-api" in self.mcp_api_url):
            default_url = "https://forecasting.guidry-cloud.com"
            os.environ["MCP_API_URL"] = default_url
            self.mcp_api_url = default_url
            warn(f"MCP_API_URL pointed to internal host; forcing external {default_url}")

        if not self.mcp_api_key:
            warn("MCP_API_KEY is missing; MCP tools will fail. Set MCP_API_KEY in the .env for the running container.")

        return self

    @model_validator(mode="before")
    @classmethod
    def _coerce_blank_env_entries(cls, data: Dict[str, object]):
        """Ensure empty-string env overrides do not clobber numeric/string defaults.
        
        Also parses NEO4J_AUTH (format: "user/password") if set.
        """
        if not isinstance(data, dict):
            return data
        
        # Parse NEO4J_AUTH if set (format: "user/password")
        # NEO4J_AUTH takes precedence over NEO4J_USER/NEO4J_PASSWORD if set
        neo4j_auth = data.get("NEO4J_AUTH") or os.getenv("NEO4J_AUTH")
        if neo4j_auth and isinstance(neo4j_auth, str) and "/" in neo4j_auth:
            parts = neo4j_auth.split("/", 1)
            if len(parts) == 2:
                # NEO4J_AUTH takes precedence - override NEO4J_USER and NEO4J_PASSWORD
                data["NEO4J_USER"] = parts[0]
                data["NEO4J_PASSWORD"] = parts[1]

        numeric_fields = {
            "qdrant_port",
            "memory_retrieve_limit",
            "memory_token_limit",
            "redis_port",
            "postgres_port",
            "redis_db",
            "agent_heartbeat_interval",
            "agent_timeout",
            "default_agent_cycle_seconds",
            "deep_research_depth",
            "deep_research_breadth",
            "deep_research_timeout_seconds",
        }

        string_fields = {
            "qdrant_host",
            "ollama_url",
            "mcp_api_url",
            "dex_simulator_url",
            "deep_search_api_url",
            "deep_research_mcp_url",
            "deep_research_model",
            "deep_research_source_preferences",
        }

        for field_name in numeric_fields:
            value = data.get(field_name)
            if isinstance(value, str) and not value.strip():
                data.pop(field_name, None)

        for field_name in string_fields:
            value = data.get(field_name)
            if isinstance(value, str) and not value.strip():
                data.pop(field_name, None)

        # ✅ Parse JSON string for news_source_weights if it's a string
        if "news_source_weights" in data:
            value = data.get("news_source_weights")
            if isinstance(value, str):
                try:
                    import json
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        data["news_source_weights"] = parsed
                except (json.JSONDecodeError, ValueError):
                    # If parsing fails, remove it to use default
                    data.pop("news_source_weights", None)

        return data
    
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL database URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def qdrant_url(self) -> str:
        """Construct Qdrant URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def openai_client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if self.openai_base_url:
            kwargs["base_url"] = self.openai_base_url
        return kwargs

    @property
    def neo4j_enabled(self) -> bool:
        """Determine whether Neo4j integration is configured."""
        return all([self.neo4j_uri, self.neo4j_user, self.neo4j_password])
    
    def get_asset_tier(self, asset: str) -> int:
        """Get the risk tier for an asset."""
        if asset in self.tier_1_assets:
            return 1
        elif asset in self.tier_2_assets:
            return 2
        elif asset in self.tier_3_assets:
            return 3
        elif asset in self.tier_4_assets:
            return 4
        return 3  # Default to tier 3
    
    def get_max_position_for_asset(self, asset: str) -> float:
        """Get maximum position size for an asset based on its tier."""
        tier = self.get_asset_tier(asset)
        if tier == 1:
            return self.max_position_size  # 20% for tier 1
        elif tier == 2:
            return self.max_position_size * 0.75  # 15% for tier 2
        elif tier == 3:
            return self.max_position_size * 0.5  # 10% for tier 3
        else:  # tier 4
            return self.max_position_size * 0.25  # 5% for tier 4 (meme coins)


# Rebuild model to resolve any forward references
Settings.model_rebuild()


# Global settings instance
settings = Settings()

# ✅ Ensure OpenAI key is exported for CAMEL and any SDKs that read from env
if settings.openai_api_key:
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
if settings.openai_base_url:
    os.environ.setdefault("OPENAI_BASE_URL", settings.openai_base_url)
