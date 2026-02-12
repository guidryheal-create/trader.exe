"""Manual Polymarket trade CLI (explicit execution only).

Usage examples:
  python scripts/polymarket_trade_cli.py --search "bitcoin"
  python scripts/polymarket_trade_cli.py --market-id <id> --details
  python scripts/polymarket_trade_cli.py --market-id <id> --outcome YES --quantity 5 --price 0.45 --confirm
  python scripts/polymarket_trade_cli.py --market-id <id> --outcome NO --quantity 5 --price 0.55 --dry-run
  python scripts/polymarket_trade_cli.py --market-id <id> --outcome YES --quantity 5 --use-mid --confirm
  python scripts/polymarket_trade_cli.py --market-id <id> --outcome YES --quantity 5 --side SELL --price 0.60 --confirm
"""

import argparse
import asyncio
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from core.clients.polymarket_client import PolymarketClient


def _load_env() -> None:
    if load_dotenv:
        project_root = Path(__file__).resolve().parents[1]
        load_dotenv(project_root / ".env", override=False)


async def _resolve_market_and_token(
    client: PolymarketClient,
    market_id: Optional[str],
    outcome: str,
    condition_id: Optional[str] = None,
    slug: Optional[str] = None,
    market_maker_address: Optional[str] = None,
):
    outcome = outcome.upper()
    try:
        details = await client.get_market_details(
            market_id=market_id,
            condition_id=condition_id,
            slug=slug,
            market_maker_address=market_maker_address,
        )
    except Exception:
        details = None
        print("Failed to fetch market details; proceeding with token ID resolution if possible.")

    tokens = await client.get_outcome_token_ids(market_id, condition_id, slug, market_maker_address)
    if not tokens:
        return details, None

    token_id = tokens.get(outcome)
    if not token_id:
        return details, None
    return details, token_id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Manual Polymarket trade CLI")
    parser.add_argument("--get-trend", action="store_true", help="Search markets by trend")
    parser.add_argument("--get-details", action="store_true", help="market details for market-id")
    parser.add_argument("--search", help="Search markets by query")
    parser.add_argument("--market-id", help="Market ID to trade (numeric id or market maker address)")
    parser.add_argument("--condition-id", help="Condition ID to trade")
    parser.add_argument("--slug", help="Market slug to trade")
    parser.add_argument("--details", action="store_true", help="Fetch market details for market-id")
    parser.add_argument("--outcome", choices=["YES", "NO"], help="Outcome to buy")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY", help="Order side (BUY or SELL)")
    parser.add_argument("--quantity", type=float, help="Order size (shares)")
    parser.add_argument("--price", type=float, help="Limit price")
    parser.add_argument("--use-mid", action="store_true", help="Use mid price from orderbook when --price is omitted")
    parser.add_argument("--check-approvals", action="store_true", help="Check required USDC/CTF approvals")
    parser.add_argument("--approve", action="store_true", help="Submit approval transactions if missing")
    parser.add_argument("--dry-run", action="store_true", help="Print intended order without executing")
    parser.add_argument("--confirm", action="store_true", help="Execute trade (must be set to place order)")

    args = parser.parse_args()

    _load_env()
    client = PolymarketClient(chain_id=137)

    if args.get_trend:
        results = await client.get_trending_markets(limit=5)
        print(results)
        return

    if args.get_details and args.market_id:
        details = await client.get_market_details(market_id=args.market_id)
        id = await client.get_outcome_token_ids(market_id=args.market_id)
        print(id)
        print(details)

    if args.search:
        results = await client.search_markets(query=args.search, limit=1)
        print(results)
        return

    if args.market_id and args.details:
        details = await client.get_market_details(market_id=args.market_id)
        print(details)
        return

    if not (args.market_id or args.condition_id or args.slug) or not args.outcome or not args.quantity:
        raise SystemExit("Provide --market-id or --condition-id or --slug, plus --outcome and --quantity for trading.")

    if not args.confirm and not args.dry_run:
        raise SystemExit("Refusing to place order without --confirm or --dry-run")

    if not client.is_authenticated:
        raise SystemExit("Client not authenticated. Set POLYGON_PRIVATE_KEY and CLOB_* creds in .env")

    if args.check_approvals or args.approve:
        approvals = client.ensure_approvals(auto_approve=bool(args.approve))
        print("\nApprovals:")
        print(approvals)
        if args.approve and not approvals.get("success"):
            raise SystemExit("Approval failed; aborting.")
        if args.check_approvals and not args.confirm and not args.dry_run:
            return

    details, token_id = await _resolve_market_and_token(
        client,
        args.market_id,
        args.outcome,
        condition_id=args.condition_id,
        slug=args.slug,
        market_maker_address=args.market_id if isinstance(args.market_id, str) and args.market_id.startswith("0x") and len(args.market_id) == 42 else None,
    )
    if not token_id:
        raise SystemExit("Unable to resolve token_id for market/outcome")
    if isinstance(details, dict):
        if details.get("closed") is True or details.get("active") is False:
            raise SystemExit("Market is closed or inactive; cannot trade on CLOB.")

    price_value = args.price
    price_source = "explicit"
    if price_value is None:
        if not args.use_mid:
            raise SystemExit("Provide --price or use --use-mid to derive a price from the orderbook.")
        try:
            orderbook = await client.get_orderbook(token_id=token_id)
            bids = orderbook.get("bids", []) if isinstance(orderbook, dict) else []
            asks = orderbook.get("asks", []) if isinstance(orderbook, dict) else []
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            if best_bid is not None and best_ask is not None:
                price_value = (best_bid + best_ask) / 2.0
                price_source = "mid"
            elif best_bid is not None:
                price_value = best_bid
                price_source = "best_bid"
            elif best_ask is not None:
                price_value = best_ask
                price_source = "best_ask"
            else:
                price_value = 0.5
                price_source = "fallback"
        except Exception:
            price_value = 0.5
            price_source = "fallback"

    print("\nOrder Preview")
    print(f"  market_id: {args.market_id}")
    print(f"  outcome:   {args.outcome}")
    print(f"  side:      {args.side}")
    print(f"  token_id:  {token_id}")
    print(f"  quantity:  {args.quantity}")
    print(f"  price:     {price_value} ({price_source})")

    if args.dry_run and not args.confirm:
        print("\nDry run complete. No order placed.")
        return

    print("\nPlacing order...")

    print("USDC", client.get_usdc_balance())
    try:
        # Use client.place_order (async)

        resp = await client.place_order(
                token_id=token_id,
                side=args.side,
                quantity=float(args.quantity),
                price=float(price_value),
            )
        
        
    except Exception as exc:
        raise SystemExit(f"Order failed: {exc}")

    print("Order response:")
    print(resp)

    print("\nFetching open positions...")
    positions = client.get_open_positions()
    print(positions)



if __name__ == "__main__":
    asyncio.run(main())
