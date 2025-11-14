# scripts/run_selection.py

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import tomllib

from .keepa_client import get_product_info, ProductStats
from .profit_calc import calc_profit_with_fba


BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.toml")
INPUT_CSV_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "input_candidates.csv")
OUTPUT_CSV_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "output_selected.csv")


@dataclass
class SelectionConfig:
    min_profit: int
    min_roi: float
    max_avg_rank_90d: int
    block_amazon_current_buybox: bool


def load_selection_config() -> SelectionConfig:
    """
    scripts/config.toml の [selection] から選別条件を読み込む。
    キーがなければそこそこ安全なデフォルト値を使う。
    """
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    sel = raw.get("selection", {})

    return SelectionConfig(
        min_profit=int(sel.get("min_profit", 0)),
        min_roi=float(sel.get("min_roi", 0.0)),
        max_avg_rank_90d=int(sel.get("max_avg_rank_90d", 999999)),
        block_amazon_current_buybox=bool(sel.get("block_amazon_current_buybox", False)),
    )


def load_candidates(path: str = INPUT_CSV_PATH) -> List[Dict[str, Any]]:
    """
    data/input_candidates.csv から仕入れ候補を読み込む。
    フォーマット:
      asin,buy_price,source
    """
    if not os.path.exists(path):
        print(f"[WARN] Candidate CSV not found: {path}")
        return []

    items: List[Dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = row.get("asin", "").strip()
            if not asin:
                continue
            try:
                buy_price = float(row.get("buy_price", "0") or 0)
            except ValueError:
                buy_price = 0.0
            source = row.get("source", "").strip() or "unknown"

            items.append(
                {
                    "asin": asin,
                    "buy_price": buy_price,
                    "source": source,
                }
            )
    print(f"Loaded {len(items)} candidate items.")
    return items


def evaluate_candidate(
    asin: str,
    buy_price: float,
    source: str,
    sel_cfg: SelectionConfig,
) -> Optional[Dict[str, Any]]:
    """
    1 商品(ASIN) について:
      - Keepa から情報取得
      - FBA 手数料込み利益計算
      - 選別条件に合格すれば dict を返す
      - NG の場合は None
    """
    print(f"\n=== Evaluating ASIN {asin} ===")

    product_stats: Optional[ProductStats] = get_product_info(asin)
    if product_stats is None:
        print(" - Skip: Could not fetch Keepa data.")
        return None

    print(f" - Title: {product_stats.title}")
    print(f" - Expected sell price: {product_stats.expected_sell_price}")
    print(f" - Avg rank 90d: {product_stats.avg_rank_90d}")
    print(
        f" - Amazon presence ratio: {product_stats.amazon_presence_ratio}, "
        f"buybox_count: {product_stats.amazon_buybox_count}, "
        f"current_is_amazon: {product_stats.amazon_current}"
    )

    # 販売価格が取得できなければ判定不能
    if product_stats.expected_sell_price is None:
        print(" - Decision: NG (sell_price_missing)")
        return None

    # ランキングチェック
    if (
        product_stats.avg_rank_90d is None
        or product_stats.avg_rank_90d <= 0
    ):
        print(" - Decision: NG (rank_missing)")
        return None

    if product_stats.avg_rank_90d > sel_cfg.max_avg_rank_90d:
        print(f" - Decision: NG (rank_too_low_{product_stats.avg_rank_90d})")
        return None

    # Amazon本体が現在 BuyBox を取っている場合にブロック
    if sel_cfg.block_amazon_current_buybox and product_stats.amazon_current:
        print(" - Decision: NG (amazon_current_buybox)")
        return None

    # FBA手数料込み利益計算
    profit_info = calc_profit_with_fba(
        sell_price=product_stats.expected_sell_price,
        buy_price=buy_price,
        weight_kg=product_stats.weight_kg,
        dimensions_cm=product_stats.dimensions_cm,
        raw_category=product_stats.category,
    )

    profit = profit_info["profit"]
    roi = profit_info["roi"]
    fba_fee = profit_info["fba_fee"]
    amazon_fee = profit_info["amazon_fee"]

    print(f" - Profit (after FBA & Amazon fee): {profit}")
    print(f" - ROI: {roi}")
    print(f"   (FBA fee: {fba_fee}, Amazon fee: {amazon_fee})")

    # 利益額・ROI でフィルタ
    if profit < sel_cfg.min_profit:
        print(f" - Decision: NG (profit_too_low_{profit})")
        return None

    if roi < sel_cfg.min_roi:
        print(f" - Decision: NG (roi_too_low_{roi})")
        return None

    print(" - Decision: OK")

    return {
        "asin": asin,
        "title": product_stats.title,
        "expected_sell_price": product_stats.expected_sell_price,
        "buy_price": buy_price,
        "profit": profit,
        "roi": roi,
        "avg_rank_90d": product_stats.avg_rank_90d,
        "amazon_presence_ratio": product_stats.amazon_presence_ratio,
        "amazon_buybox_count": product_stats.amazon_buybox_count,
        "amazon_current": product_stats.amazon_current,
        "fba_fee": fba_fee,
        "amazon_fee": amazon_fee,
        "source": source,
    }


def write_selected_items(items: List[Dict[str, Any]], path: str = OUTPUT_CSV_PATH) -> None:
    """
    合格した商品を CSV に書き出す。
    """
    if not items:
        print("No items passed the selection criteria. No CSV will be written.")
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    headers = [
        "asin",
        "title",
        "expected_sell_price",
        "buy_price",
        "profit",
        "roi",
        "avg_rank_90d",
        "amazon_presence_ratio",
        "amazon_buybox_count",
        "amazon_current",
        "fba_fee",
        "amazon_fee",
        "source",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for item in items:
            writer.writerow(item)

    print(f"Wrote {len(items)} selected items to {path}")


def main():
    sel_cfg = load_selection_config()
    candidates = load_candidates()

    selected: List[Dict[str, Any]] = []

    for c in candidates:
        asin = c["asin"]
        buy_price = c["buy_price"]
        source = c["source"]

        result = evaluate_candidate(
            asin=asin,
            buy_price=buy_price,
            source=source,
            sel_cfg=sel_cfg,
        )
        if result is not None:
            selected.append(result)

    write_selected_items(selected)


if __name__ == "__main__":
    main()
