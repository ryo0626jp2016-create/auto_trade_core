# scripts/run_selection.py

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import List

from .keepa_client import get_product_info
from .fba_fee import estimate_fba_fee
from .profit_calc import estimate_amazon_fee
import tomllib

# このファイルと同じディレクトリの config.toml を読む
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")

# 候補ASINリストと、結果CSVのパス
INPUT_CSV = os.path.join("data", "input_candidates.csv")
OUTPUT_CSV = os.path.join("data", "output_selected.csv")


@dataclass
class SelectionConfig:
    """仕入れ判定用のしきい値設定"""
    min_profit: float                     # 最低利益（円）
    min_roi: float                        # 最低ROI
    max_avg_rank_90d: int                 # 90日平均ランキングの上限
    block_amazon_current_buybox: bool     # 現在Amazon本体がカート取得中ならNGにするか
    debug_no_fba_fee: bool = False        # デバッグ時：FBA手数料を0として計算するか


def load_selection_config() -> SelectionConfig:
    """scripts/config.toml から selection 設定を読み込む"""
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    s = raw["selection"]
    return SelectionConfig(
        min_profit=s.get("min_profit", 1),
        min_roi=s.get("min_roi", 0.0),
        max_avg_rank_90d=s.get("max_avg_rank_90d", 200000),
        block_amazon_current_buybox=s.get("block_amazon_current_buybox", True),
        debug_no_fba_fee=s.get("debug_no_fba_fee", False),
    )


def read_candidates() -> List[tuple[str, float, str]]:
    """
    data/input_candidates.csv を読み込む。
    フォーマット:
        asin,buy_price,notes
    """
    items: List[tuple[str, float, str]] = []

    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] input not found: {INPUT_CSV}")
        return items

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = row["asin"].strip()
            buy_price = float(row["buy_price"])
            notes = row.get("notes", "")
            items.append((asin, buy_price, notes))

    return items


def main() -> None:
    config = load_selection_config()
    print(f"Loaded config: {config}")

    candidates = read_candidates()
    print(f"Loaded {len(candidates)} candidate items.")

    results: list[list] = []

    for asin, buy_price, notes in candidates:
        print(f"\n=== Evaluating ASIN {asin} ===")

        # Keepa から商品情報取得
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

        # ① ランク判定
        if product.avg_rank_90d and product.avg_rank_90d > config.max_avg_rank_90d:
            print(f" - Decision: NG (rank_too_low_{product.avg_rank_90d})")
            continue

        # ② Amazon本体の現在カート取得をブロックするか
        if config.block_amazon_current_buybox and product.amazon_current:
            print(" - Decision: NG (amazon_current_buybox)")
            continue

        # ③ 販売価格が取れなければNG
        if not product.expected_sell_price:
            print(" - Decision: NG (sell_price_missing)")
            continue

        # ④ FBA & 販売手数料の計算
        if config.debug_no_fba_fee:
            fba_fee = 0.0
        else:
            # fba_fee.py の estimate_fba_fee(product) を利用
            fba_fee = estimate_fba_fee(product)

        amazon_fee = estimate_amazon_fee(product.expected_sell_price)

        profit = product.expected_sell_price - buy_price - fba_fee - amazon_fee
        roi = profit / buy_price if buy_price > 0 else 0.0

        print(f" - Profit (after FBA & Amazon fee): {profit}")
        print(f" - ROI: {roi}")
        print(f"   (FBA fee: {fba_fee}, Amazon fee: {amazon_fee})")

        # ⑤ 利益条件判定
        if profit < config.min_profit:
            print(f" - Decision: NG (profit_too_low_{profit})")
            continue

        if roi < config.min_roi:
            print(f" - Decision: NG (roi_too_low_{roi})")
            continue

        # ⑥ ここまで来たら仕入れ候補として採用
        print(" - Decision: OK")
        results.append([
            asin,
            product.title,
            buy_price,
            product.expected_sell_price,
            profit,
            roi,
            notes,
        ])

    # ⑦ CSV出力
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

