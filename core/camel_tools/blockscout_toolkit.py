"""
Blockscout MCP Toolkit for CAMEL Agents.

Provides tools for querying on-chain data across 3,000+ EVM-compatible chains.
Reference: https://www.blog.blockscout.com/how-to-set-up-mcp-ai-onchain-data-block-explorer/
"""
from typing import Dict, Any, Annotated
from pydantic import Field
from core.logging import log
from core.config import settings
from core.clients.blockscout_client import BlockscoutMCPClient, BlockscoutMCPError


# Global toolkit instance
_toolkit_instance: "BlockscoutMCPToolkit" = None


def get_blockscout_toolkit() -> "BlockscoutMCPToolkit":
    """Get or create the global Blockscout toolkit instance."""
    global _toolkit_instance
    if _toolkit_instance is None:
        _toolkit_instance = BlockscoutMCPToolkit()
    return _toolkit_instance


class BlockscoutMCPToolkit:
    """Toolkit for Blockscout MCP on-chain data queries."""
    
    def __init__(self):
        """Initialize the Blockscout MCP toolkit."""
        config = {
            "base_url": settings.blockscout_mcp_url,
            "timeout": 30.0,
            "retry_attempts": 3
        }
        self.blockscout_client = BlockscoutMCPClient(config)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the Blockscout client connection."""
        if not self._initialized:
            await self.blockscout_client.connect()
            self._initialized = True
            log.info("Blockscout MCP toolkit initialized")
    
    def get_list_chains_tool(self):
        """Get tool for listing supported EVM chains."""
        toolkit_instance = self
        
        async def list_chains() -> Dict[str, Any]:
            """
            List all EVM-compatible blockchain networks supported by Blockscout.
            
            Returns a dictionary with success status, chains list, and total count.
            Each chain entry includes metadata such as chain ID, name, and network information.
            
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - chains (list): List of supported chains with metadata
                    - total_chains (int): Total number of supported chains
            """
            try:
                await toolkit_instance.initialize()
                chains = await toolkit_instance.blockscout_client.list_chains()
                return {
                    "success": True,
                    "chains": chains,
                    "total_chains": len(chains)
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "chains": []
                }
            except Exception as e:
                log.error(f"Error listing chains: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "chains": []
                }
        
        list_chains.__name__ = "list_chains"
        list_chains.__doc__ = "List all EVM-compatible blockchain networks supported by Blockscout"
        return list_chains
    
    def get_wallet_balance_tool(self):
        """Get tool for querying wallet balances."""
        toolkit_instance = self
        
        async def get_wallet_balance(
            address: Annotated[str, Field(description="Wallet address (0x...)")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, polygon, arbitrum)", default="ethereum")] = "ethereum",
            token_address: Annotated[str, Field(description="Optional token contract address for token balance", default=None)] = None
        ) -> Dict[str, Any]:
            """
            Get wallet balance for an address on a specific EVM chain.
            
            Retrieves both native token (ETH, MATIC, etc.) and ERC-20 token balances.
            If token_address is provided, returns balance for that specific token.
            
            Args:
                address: Wallet address in 0x format (e.g., 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb)
                chain: Chain name (e.g., ethereum, polygon, arbitrum, bsc). Default: ethereum
                token_address: Optional ERC-20 token contract address. If None, returns all token balances
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - address (str): The queried wallet address
                    - chain (str): The chain name
                    - native_balance (str): Native token balance (e.g., ETH balance)
                    - token_balances (list): List of ERC-20 token balances if token_address is None
                    - token_balance (str): Specific token balance if token_address is provided
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                result = await toolkit_instance.blockscout_client.get_wallet_balance(
                    address=address,
                    chain=chain,
                    token_address=token_address
                )
                return {
                    "success": True,
                    "address": address,
                    "chain": chain,
                    **result
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "address": address,
                    "chain": chain
                }
            except Exception as e:
                log.error(f"Error getting wallet balance: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "address": address,
                    "chain": chain
                }
        
        get_wallet_balance.__name__ = "get_wallet_balance"
        get_wallet_balance.__doc__ = "Get wallet balance for an address on a specific EVM chain"
        return get_wallet_balance
    
    def get_transaction_history_tool(self):
        """Get tool for querying transaction history."""
        toolkit_instance = self
        
        async def get_transaction_history(
            address: Annotated[str, Field(description="Wallet address (0x...)")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, polygon)", default="ethereum")] = "ethereum",
            limit: Annotated[int, Field(description="Number of transactions to return", default=50)] = 50,
            offset: Annotated[int, Field(description="Pagination offset", default=0)] = 0
        ) -> Dict[str, Any]:
            """
            Get transaction history for a wallet address on a specific EVM chain.
            
            Retrieves a paginated list of transactions (both sent and received) for the given address.
            Transactions include details such as hash, timestamp, value, gas fees, and status.
            
            Args:
                address: Wallet address in 0x format
                chain: Chain name (e.g., ethereum, polygon, arbitrum). Default: ethereum
                limit: Maximum number of transactions to return (1-100). Default: 50
                offset: Pagination offset for retrieving older transactions. Default: 0
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - address (str): The queried wallet address
                    - chain (str): The chain name
                    - transactions (list): List of transaction objects with full details
                    - count (int): Number of transactions returned
                    - limit (int): The limit parameter used
                    - offset (int): The offset parameter used
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                transactions = await toolkit_instance.blockscout_client.get_transaction_history(
                    address=address,
                    chain=chain,
                    limit=limit,
                    offset=offset
                )
                return {
                    "success": True,
                    "address": address,
                    "chain": chain,
                    "transactions": transactions,
                    "count": len(transactions),
                    "limit": limit,
                    "offset": offset
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "address": address,
                    "chain": chain,
                    "transactions": []
                }
            except Exception as e:
                log.error(f"Error getting transaction history: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "address": address,
                    "chain": chain,
                    "transactions": []
                }
        
        get_transaction_history.__name__ = "get_transaction_history"
        get_transaction_history.__doc__ = "Get transaction history for a wallet address on a specific chain"
        return get_transaction_history
    
    def get_contract_info_tool(self):
        """Get tool for querying smart contract information."""
        toolkit_instance = self
        
        async def get_contract_info(
            contract_address: Annotated[str, Field(description="Smart contract address (0x...)")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, arbitrum)", default="ethereum")] = "ethereum"
        ) -> Dict[str, Any]:
            """
            Get smart contract information including source code, ABI, and verification status.
            
            Retrieves comprehensive contract details including verified source code, ABI (Application Binary Interface),
            compiler version, and optimization settings. Useful for contract analysis and interaction.
            
            Args:
                contract_address: Smart contract address in 0x format
                chain: Chain name (e.g., ethereum, arbitrum, polygon). Default: ethereum
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - contract_address (str): The queried contract address
                    - chain (str): The chain name
                    - source_code (str): Verified contract source code
                    - abi (list): Contract ABI (JSON interface)
                    - compiler_version (str): Solidity compiler version used
                    - optimization_enabled (bool): Whether optimization was enabled
                    - verification_status (str): Contract verification status
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                result = await toolkit_instance.blockscout_client.get_contract_info(
                    contract_address=contract_address,
                    chain=chain
                )
                return {
                    "success": True,
                    "contract_address": contract_address,
                    "chain": chain,
                    **result
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "contract_address": contract_address,
                    "chain": chain
                }
            except Exception as e:
                log.error(f"Error getting contract info: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "contract_address": contract_address,
                    "chain": chain
                }
        
        get_contract_info.__name__ = "get_contract_info"
        get_contract_info.__doc__ = "Get smart contract information including source code and ABI"
        return get_contract_info
    
    def get_token_info_tool(self):
        """Get tool for querying token information."""
        toolkit_instance = self
        
        async def get_token_info(
            token_address: Annotated[str, Field(description="Token contract address (0x...)")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, polygon)", default="ethereum")] = "ethereum"
        ) -> Dict[str, Any]:
            """
            Get token information for ERC-20 or ERC-721 tokens.
            
            Retrieves comprehensive token metadata including name, symbol, decimals, total supply,
            token type (ERC-20 fungible or ERC-721 NFT), and holder count.
            
            Args:
                token_address: Token contract address in 0x format
                chain: Chain name (e.g., ethereum, polygon, arbitrum). Default: ethereum
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - token_address (str): The queried token address
                    - chain (str): The chain name
                    - name (str): Token name (e.g., "Wrapped Ether")
                    - symbol (str): Token symbol (e.g., "WETH")
                    - decimals (int): Number of decimals (typically 18 for ERC-20)
                    - total_supply (str): Total token supply
                    - token_type (str): "ERC-20" or "ERC-721"
                    - holders_count (int): Number of token holders
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                result = await toolkit_instance.blockscout_client.get_token_info(
                    token_address=token_address,
                    chain=chain
                )
                return {
                    "success": True,
                    "token_address": token_address,
                    "chain": chain,
                    **result
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "token_address": token_address,
                    "chain": chain
                }
            except Exception as e:
                log.error(f"Error getting token info: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "token_address": token_address,
                    "chain": chain
                }
        
        get_token_info.__name__ = "get_token_info"
        get_token_info.__doc__ = "Get token information (ERC-20/ERC-721) including name, symbol, and supply"
        return get_token_info
    
    def get_transaction_details_tool(self):
        """Get tool for querying transaction details."""
        toolkit_instance = self
        
        async def get_transaction_details(
            tx_hash: Annotated[str, Field(description="Transaction hash")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, polygon)", default="ethereum")] = "ethereum"
        ) -> Dict[str, Any]:
            """
            Get detailed transaction information by transaction hash.
            
            Retrieves comprehensive transaction details including sender/receiver addresses, value transferred,
            gas used, gas price, transaction status (success/failed), block number, timestamp, and event logs.
            
            Args:
                tx_hash: Transaction hash (0x-prefixed hex string)
                chain: Chain name (e.g., ethereum, polygon, arbitrum). Default: ethereum
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - tx_hash (str): The queried transaction hash
                    - chain (str): The chain name
                    - from_address (str): Sender wallet address
                    - to_address (str): Receiver wallet address
                    - value (str): Amount transferred in native token (wei)
                    - gas_used (int): Gas units consumed
                    - gas_price (str): Gas price in wei
                    - status (str): Transaction status ("success" or "failed")
                    - block_number (int): Block number containing the transaction
                    - timestamp (str): Transaction timestamp
                    - logs (list): Event logs emitted by the transaction
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                result = await toolkit_instance.blockscout_client.get_transaction_details(
                    tx_hash=tx_hash,
                    chain=chain
                )
                return {
                    "success": True,
                    "tx_hash": tx_hash,
                    "chain": chain,
                    **result
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tx_hash": tx_hash,
                    "chain": chain
                }
            except Exception as e:
                log.error(f"Error getting transaction details: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "tx_hash": tx_hash,
                    "chain": chain
                }
        
        get_transaction_details.__name__ = "get_transaction_details"
        get_transaction_details.__doc__ = "Get detailed transaction information by transaction hash"
        return get_transaction_details
    
    def get_compare_wallets_tool(self):
        """Get tool for comparing multiple wallets."""
        toolkit_instance = self
        
        async def compare_wallets(
            addresses: Annotated[str, Field(description="Comma-separated list of wallet addresses (0x...)")],
            chain: Annotated[str, Field(description="Chain name (e.g., ethereum, polygon)", default="ethereum")] = "ethereum"
        ) -> Dict[str, Any]:
            """
            Compare multiple wallets across balances, activity, and statistics.
            
            Analyzes and compares multiple wallet addresses on the same chain, providing aggregated
            statistics such as total balances, transaction counts, activity levels, and balance distributions.
            
            Args:
                addresses: Comma-separated list of wallet addresses in 0x format (e.g., "0x123...,0x456...")
                chain: Chain name (e.g., ethereum, polygon, arbitrum). Default: ethereum
                
            Returns:
                Dict containing:
                    - success (bool): Whether the operation succeeded
                    - addresses (list): List of compared wallet addresses
                    - chain (str): The chain name
                    - total_balance (str): Sum of all wallet balances
                    - average_balance (str): Average balance across wallets
                    - wallet_stats (list): Per-wallet statistics including balance and transaction count
                    - comparison_metrics (dict): Aggregated comparison metrics
                    - error (str): Error message if success is False
            """
            try:
                await toolkit_instance.initialize()
                address_list = [addr.strip() for addr in addresses.split(",")]
                result = await toolkit_instance.blockscout_client.compare_wallets(
                    addresses=address_list,
                    chain=chain
                )
                return {
                    "success": True,
                    **result
                }
            except BlockscoutMCPError as e:
                log.error(f"Blockscout MCP error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "addresses": addresses,
                    "chain": chain
                }
            except Exception as e:
                log.error(f"Error comparing wallets: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "addresses": addresses,
                    "chain": chain
                }
        
        compare_wallets.__name__ = "compare_wallets"
        compare_wallets.__doc__ = "Compare multiple wallets across balances and activity"
        return compare_wallets

