from __future__ import annotations
import csv
import os
from typing import List
from scripts.keepa_api import get_product_info
from scripts.fees import estimate_fba_fee, estimate_amazon_fee
from dataclasses import dataclass
import tomllib


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")
INPUT_CSV = os.path.join("data", "input_candidates.csv")
OUTPUT_CSV = os.path.join("data", "output_selected.csv")


@dataclass
class SelectionConfig:
    min_profit: float
    min_roi: float
    max_avg_rank_90d: int
    block_amazon_current_buybox: bool
    debug_no_fba_fee: bool = False   # ←追加：デバッグモード


def load_selection_config() -> SelectionConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    s = raw["selection"]
    return SelectionConfig(
        min_profit=s.get("min_profit", 1),
        min_roi=s.get("min_roi", 0.0),
        max_avg_rank_90d=s.get("max_avg_rank_90d", 200000),
        block_amazon_current_buybox=s.get("block_amazon_current_buybox", True),
        debug_no_fba_fee=s.get("debug_no_fba_fee", False)
    )


def read_candidates() -> List[tuple[str, float, str]]:
    items = []
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] input not found: {INPUT_CSV}")
        return items

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = row["asin"].strip()
            buy_price = float(row["buy_price"])
            notes = row["notes"]
            items.append((asin, buy_price, notes))
    return items


def main():
    config = load_selection_config()
    print(f"Loaded config: {config}")

    candidates = read_candidates()
    print(f"Loaded {len(candidates)} candidate items.")

    results = []

    for asin, buy_price, notes in candidates:
        print(f"\n=== Evaluating ASIN {asin} ===")

        product = get_product_info(asin)
        if not product:
            print(" - Skip: Could not fetch Keepa data.")
            continue

        print(f" - Title: {product.title}")
        print(f" - Expected sell price: {product.expected_sell_price}")
        print(f" - Avg rank 90d: {product.avg_rank_90d}")
        print(f" - Amazon presence ratio: {product.amazon_presence_ratio}")
        print(f" - buybox_count: {product.amazon_buybox_count}")
        print(f" - current_is_amazon: {product.amazon_current}")

        # ランク判定
        if product.avg_rank_90d and product.avg_rank_90d > config.max_avg_rank_90d:
            print(f" - Decision: NG (rank_too_low_{product.avg_rank_90d})")
            continue

        # Amazon buybox 判定
        if config.block_amazon_current_buybox and product.amazon_current:
            print(" - Decision: NG (amazon_current_buybox)")
            continue

        # 販売価格の取得
        if not product.expected_sell_price:
            print(" - Decision: NG (sell_price_missing)")
            continue

        # FBA / Amazon fee 計算
        if config.debug_no_fba_fee:
            fba_fee = 0
            amazon_fee = 0
        else:
            fba_fee = estimate_fba_fee(product)
            amazon_fee = estimate_amazon_fee(product.expected_sell_price)

        profit = product.expected_sell_price - buy_price - fba_fee - amazon_fee
        roi = profit / buy_price if buy_price > 0 else 0

        print(f" - Profit (after FBA & Amazon fee): {profit}")
        print(f" - ROI: {roi}")
        print(f"   (FBA fee: {fba_fee}, Amazon fee: {amazon_fee})")

        # 利益判定
        if profit < config.min_profit:
            print(f" - Decision: NG (profit_too_low_{profit})")
            continue

        if roi < config.min_roi:
            print(f" - Decision: NG (roi_too_low_{roi})")
            continue

        # OK判定
        print(" - Decision: OK")
        results.append([
            asin,
            product.title,
            buy_price,
            product.expected_sell_price,
            profit,
            roi,
            notes
        ])

    # CSV出力
    if results:
        os.makedirs("data", exist_ok=True)
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["asin", "title", "buy_price", "sell_price", "profit", "roi", "notes"])
            writer.writerows(results)
        print(f"Saved: {OUTPUT_CSV}")
    else:
        print("No items passed selection criteria. No CSV will be written.")


if __name__ == "__main__":
    main()
