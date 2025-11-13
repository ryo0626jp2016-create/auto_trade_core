from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import os
import tomllib

from .keepa_client import ProductStats


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


@dataclass
class SelectionConfig:
    min_profit: int
    min_roi: float
    max_avg_rank_90d: int
    block_amazon_current_buybox: bool


def load_selection_config() -> SelectionConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    s = raw["selection"]
    return SelectionConfig(
        min_profit=int(s.get("min_profit", 500)),
        min_roi=float(s.get("min_roi", 0.3)),
        max_avg_rank_90d=int(s.get("max_avg_rank_90d", 100000)),
        block_amazon_current_buybox=bool(
            s.get("block_amazon_current_buybox", True)
        ),
    )


def evaluate_item(
    asin: str,
    buy_price: float,
    product_stats: ProductStats | None,
) -> Dict[str, Any]:
    """
    1商品の仕入れ判定を行い、結果を dict で返す。
    """
    cfg = load_selection_config()

    if product_stats is None:
        return {
            "asin": asin,
            "is_ok": False,
            "reason": "Keepa product not found",
        }

    # 1) Amazon本体が現在カートをとっているかチェック
    if cfg.block_amazon_current_buybox and product_stats.buybox_is_amazon:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": "Amazon currently has the buy box",
        }

    # 2) ランキングチェック
    avg_rank = product_stats.avg_rank_90d
    if avg_rank is None:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": "No avg_rank_90d",
        }

    if avg_rank > cfg.max_avg_rank_90d:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": f"Rank too low: {avg_rank}",
        }

    # 3) 売価が取れない場合はスキップ
    sell_price = product_stats.expected_sell_price
    if sell_price is None:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": "No expected sell price (buy box data missing)",
        }

    # 4) 粗利益計算（ざっくりモデル）
    #   - Amazon手数料: 15%
    #   - FBA発送手数料: 300円 として仮置き
    amazon_fee = sell_price * 0.15 + 300
    profit = sell_price - amazon_fee - buy_price
    roi = profit / buy_price if buy_price > 0 else -1

    if profit < cfg.min_profit:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": f"Profit too small: {profit:.0f}",
            "profit": round(profit),
            "roi": round(roi, 2),
            "avg_rank_90d": avg_rank,
            "sell_price": round(sell_price),
            "buy_price": buy_price,
        }

    if roi < cfg.min_roi:
        return {
            "asin": asin,
            "title": product_stats.title,
            "is_ok": False,
            "reason": f"ROI too low: {roi:.2f}",
            "profit": round(profit),
            "roi": round(roi, 2),
            "avg_rank_90d": avg_rank,
            "sell_price": round(sell_price),
            "buy_price": buy_price,
        }

    # ここまで来たら仕入れOK
    return {
        "asin": asin,
        "title": product_stats.title,
        "is_ok": True,
        "reason": "OK",
        "profit": round(profit),
        "roi": round(roi, 2),
        "avg_rank_90d": avg_rank,
        "sell_price": round(sell_price),
        "buy_price": buy_price,
    }
