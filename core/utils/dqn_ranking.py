"""
DQN signal normalisation and ranking helpers.

These helpers work on top of ForecastingClient.get_action_recommendation
results, taking a list of pre-fetched action payloads and producing
compact rankings for BUY/SELL strength.
"""

from __future__ import annotations

from typing import Dict, List, Literal, TypedDict, Any


Side = Literal["buy", "sell", "both"]


class DQNSignal(TypedDict, total=False):
    ticker: str
    symbol: str
    interval: str
    action: int
    action_name: str
    confidence: float
    buy_score: float
    sell_score: float
    current_price: float
    q_values: List[float]


def _normalise_scores(record: Dict[str, Any]) -> DQNSignal:
    """
    Attach buy_score / sell_score to a raw action record.

    Expected input keys (from ForecastingClient.get_action_recommendation):
      - action: int (0=SELL, 1=HOLD, 2=BUY)
      - action_confidence: float
      - q_values: optional list[float] of length 3 [SELL, HOLD, BUY]
    """
    q_values = record.get("q_values") or []
    if isinstance(q_values, str):
        try:
            import json

            q_values = json.loads(q_values)
        except Exception:
            q_values = []

    q_values = q_values if isinstance(q_values, list) else []
    if len(q_values) != 3:
        # Fallback to a neutral distribution if q_values are missing
        q_values = [0.33, 0.34, 0.33]

    action = int(record.get("action", 1))
    action_conf = float(record.get("action_confidence", 0.0) or 0.0)

    # Primary scores from q_values
    buy_score = float(q_values[2])
    sell_score = float(q_values[0])

    # If we have a strong explicit action_confidence for the side that was chosen,
    # bias the corresponding score upwards slightly.
    if action == 2 and action_conf > buy_score:
        buy_score = action_conf
    elif action == 0 and action_conf > sell_score:
        sell_score = action_conf

    action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
    action_name = action_map.get(action, "HOLD")

    return DQNSignal(
        ticker=str(record.get("base_ticker") or record.get("ticker") or ""),
        symbol=str(record.get("symbol") or record.get("ticker") or ""),
        interval=str(record.get("interval") or ""),
        action=action,
        action_name=action_name,
        confidence=action_conf or max(buy_score, sell_score),
        buy_score=buy_score,
        sell_score=sell_score,
        current_price=float(record.get("current_price") or 0.0),
        q_values=list(q_values),
    )


def _filter_by_side(records: List[DQNSignal], side: Side) -> List[DQNSignal]:
    """Filter records that have a meaningful signal for the requested side."""
    if side == "buy":
        return [r for r in records if r["buy_score"] > 0]
    if side == "sell":
        return [r for r in records if r["sell_score"] > 0]
    return records


def rank_best_signals(
    raw_records: List[Dict[str, Any]],
    side: Side,
    limit: int,
) -> Dict[str, Any]:
    """
    Rank best BUY/SELL signals.

    Returns a compact JSON structure suitable for tool outputs:
      - if side in {\"buy\",\"sell\"}: { side: [...], side_limit: int }
      - if side == \"both\": { best_buy: [...], best_sell: [...], limit: int }
    """
    limit = max(1, min(int(limit), 50))
    enriched = [_normalise_scores(r) for r in raw_records]

    def sort_buy(rs: List[DQNSignal]) -> List[DQNSignal]:
        return sorted(rs, key=lambda r: r["buy_score"], reverse=True)[:limit]

    def sort_sell(rs: List[DQNSignal]) -> List[DQNSignal]:
        return sorted(rs, key=lambda r: r["sell_score"], reverse=True)[:limit]

    if side == "buy":
        buy_records = sort_buy(_filter_by_side(enriched, "buy"))
        return {"side": "buy", "limit": limit, "signals": buy_records}

    if side == "sell":
        sell_records = sort_sell(_filter_by_side(enriched, "sell"))
        return {"side": "sell", "limit": limit, "signals": sell_records}

    # both
    best_buy = sort_buy(_filter_by_side(enriched, "buy"))
    best_sell = sort_sell(_filter_by_side(enriched, "sell"))
    return {
        "side": "both",
        "limit": limit,
        "best_buy": best_buy,
        "best_sell": best_sell,
    }


def rank_best_vs_worst_signals(
    raw_records: List[Dict[str, Any]],
    side: Side,
    limit: int,
) -> Dict[str, Any]:
    """
    Rank best and worst signals for a given side.

    \"Best\" = highest score for that side.
    \"Worst\" = lowest non-zero score for that side, among assets that emit that signal.
    """
    limit = max(1, min(int(limit), 50))
    enriched = [_normalise_scores(r) for r in raw_records]

    def best_worst(
        rs: List[DQNSignal],
        use_buy: bool,
    ) -> Dict[str, List[DQNSignal]]:
        key = "buy_score" if use_buy else "sell_score"
        valid = [r for r in rs if r[key] > 0]
        if not valid:
            return {"best": [], "worst": []}
        ordered = sorted(valid, key=lambda r: r[key], reverse=True)
        best = ordered[:limit]
        worst = list(reversed(ordered))[:limit]
        return {"best": best, "worst": worst}

    if side == "buy":
        subset = _filter_by_side(enriched, "buy")
        bw = best_worst(subset, use_buy=True)
        return {"side": "buy", "limit": limit, **bw}

    if side == "sell":
        subset = _filter_by_side(enriched, "sell")
        bw = best_worst(subset, use_buy=False)
        return {"side": "sell", "limit": limit, **bw}

    # both
    buy_bw = best_worst(_filter_by_side(enriched, "buy"), use_buy=True)
    sell_bw = best_worst(_filter_by_side(enriched, "sell"), use_buy=False)
    return {
        "side": "both",
        "limit": limit,
        "buy": buy_bw,
        "sell": sell_bw,
    }



