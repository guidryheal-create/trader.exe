from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, MarketOrderArgs
from py_clob_client.order_builder.constants import BUY, SELL


host: str = "https://clob.polymarket.com"
key: str = "6d01e41ee42fc6aa2fda393e8c58240c3879dec405edc16f6850205188448f4e" #"0x5111e75529f91fcd0dc66d6a23ce31004ff61d19e5f75f49eaec740a4a5abe3d" #This is your Private Key. Export from reveal.polymarket.com or from your Web3 Application
chain_id: int = 137 #No need to adjust this
POLYMARKET_PROXY_ADDRESS: str = "0x82d59ac77aa44feeb7173f73b356965508be2ea0" #"0xBE0eB07dca2207D8a73a8Fc52e3058416f32A6aC" #"0xBE0eB07dca2207D8a73a8Fc52e3058416f32A6aC"  #'0x7764DcAf2519BEEB08bF2f4f95F0fc6D6559334F' ## #This is the address you deposit/send USDC to to FUND your Polymarket account.
# 0xBE0eB07dca2207D8a73a8Fc52e3058416f32A6aC
# Canada
#Select from the following 3 initialization options to matches your login method, and remove any unused lines so only one client is initialized.

### Initialization of a client using a Polymarket Proxy associated with an Email/Magic account. If you login with your email use this example.
#client = ClobClient(host, key=key, chain_id=chain_id, signature_type=1, funder=POLYMARKET_PROXY_ADDRESS)

### Initialization of a client using a Polymarket Proxy associated with a Browser Wallet(Metamask, Coinbase Wallet, etc)
#client = ClobClient(host, key=key, chain_id=chain_id, signature_type=2, funder=POLYMARKET_PROXY_ADDRESS)

### Initialization of a client that trades directly from an EOA. 
client = ClobClient(host, key=key, chain_id=chain_id, signature_type=2, funder=POLYMARKET_PROXY_ADDRESS) # signatureType 2 when web ui

client.get_markets()
## Create and sign a limit order buying 100 YES tokens for 0.50c each
#Refer to the Markets API documentation to locate a tokenID: https://docs.polymarket.com/developers/gamma-markets-api/get-markets

client.set_api_creds(client.create_or_derive_api_creds()) 

# print(client.get_price("86747772836911775922057639239053413816155316577458452758134270001018486135733", BUY))
# test on next trade  --> market trade seems clearner but nothing proove working actualy
# market level trade maybe not token id ?
order_args = OrderArgs(
    price=0.99,
    size=2,
    side=BUY,
    token_id="93650255436006267988321932304979422947402635812913538865761249802385028747113",
)

from decimal import Decimal, ROUND_DOWN

amount = Decimal("5").quantize(Decimal("0.01"), rounding=ROUND_DOWN)


market_order = MarketOrderArgs(
    amount=amount,
    side=SELL,
    token_id="91476348043501290296002542371370873214324765964392677410406915117239290266273",
)

signed_order = client.create_order(order_args)
print(signed_order)
## GTC(Good-Till-Cancelled) Order
resp = client.post_order(signed_order, orderType=OrderType.FAK)
print(resp)

"""

    def build_order(
        self,
        market_token: str,
        amount: float,
        nonce: str = str(round(time.time())),  # for cancellations
        side: str = "BUY",
        expiration: str = "0",  # timestamp after which order expires
    ):
        signer = Signer(self.private_key)
        builder = OrderBuilder(self.exchange_address, self.chain_id, signer)

        buy = side == "BUY"
        side = 0 if buy else 1
        maker_amount = amount if buy else 0
        taker_amount = amount if not buy else 0
        order_data = OrderData(
            maker=self.get_address_for_private_key(),
            tokenId=market_token,
            makerAmount=maker_amount,
            takerAmount=taker_amount,
            feeRateBps="1",
            nonce=nonce,
            side=side,
            expiration=expiration,
        )
        order = builder.build_signed_order(order_data)
        return order
"""
