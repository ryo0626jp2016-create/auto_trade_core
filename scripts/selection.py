from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from typing import Optional, List

from .keepa_api import get_product_info


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")
INPUT_CSV_PATH = os.path.join("data", "input_candidates.csv")
OUTPUT_CSV_PATH = os.path.join("data", "output_selected.csv")


@dataclass
class SelectionConfig:
    min_profit: float
    min_roi: float
    max_avg_rank_90d: int
    block_amazon_current_buybox: bool
    debug_no_fees: bool


def load_selection_config() -> SelectionConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    s = raw["selection"]
    return SelectionConfig(
        min_profit=s.get("min_profit", 0),
        min_roi=s.get("min_roi", 0),
        max_avg_rank_90d=s.get("max_avg_rank_90d", 100000),
        block_amazon_current_buybox=s.get("block_amazon_current_buybox", True),
        debug_no_fees=s.get("debug_no_fees", False),
    )


def calculate_profit(sell_price: float, buy_price: float, debug_no_fees: bool) -> tuple[float, float, float]:
    """
    利益計算（デバッグ時はFBA/手数料を強制0に）
    """
    if debug_no_fees:
        return sell_price - buy_price, 0, 0

    # 実運用用（今はデバッグなので使われない）
    amazon_fee = int(sell_price * 0.10)
    fba_fee = 459
    profit = sell_price - amazon_fee - fba_fee - buy_price
    return profit, amazon_fee, fba_fee


def evaluate_candidate(asin: str, buy_price: float, note: str, cfg: SelectionConfig):
    p = get_product_info(asin)
    if p is None:
        print(f" - Skip: Could not fetch Keepa data.")
        return None

    sell_price = p.expected_sell_price
    if sell_price is None:
        print(f" - Decision: NG (sell_price_missing)")
        return None

    profit, amazon_fee, fba_fee = calculate_profit(sell_price, buy_price, cfg.debug_no_fees)
    roi = profit / buy_price if buy_price > 0 else 0

    print(f" - Profit (after fees): {profit}")
    print(f" - ROI: {roi}")

    # デバッグ中は利益条件を無効化
    if not cfg.debug_no_fees:
        if profit < cfg.min_profit:
            print(f" - Decision: NG (profit_too_low)")
            return None
        if roi < cfg.min_roi:
            print(f" - Decision: NG (roi_too_low)")
            return None

    # ランク条件も無視
    print(" - Decision: OK (debug mode)")
    return {
        "asin": asin,
        "title": p.title,
        "sell_price": sell_price,
        "buy_price": buy_price,
        "profit": profit,
        "roi": roi,
        "note": note,
    }


def run_selection():
    cfg = load_selection_config()

    results = []
    with open(INPUT_CSV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header = True
    for line in lines:
        if header:
            header = False
            continue

        asin, price_str, note = line.strip().split("\t")
        buy_price = float(price_str)

        print(f"=== Evaluating ASIN {asin} ===")

        r = evaluate_candidate(asin, buy_price, note, cfg)
        if r is not None:
            results.append(r)

    # CSV 出力
    if results:
        os.makedirs("data", exist_ok=True)
        with open(OUTPUT_CSV_PATH, "w", encoding="utf-8") as w:
            w.write("asin\ttitle\tsell_price\tbuy_price\tprofit\troi\tnote\n")
            for r in results:
                w.write(
                    f"{r['asin']}\t{r['title']}\t{r['sell_price']}"
                    f"\t{r['buy_price']}\t{r['profit']}\t{r['roi']}\t{r['note']}\n"
                )
        print(f"\n[OK] Wrote result CSV → {OUTPUT_CSV_PATH}")
    else:
        print("\n[INFO] No items selected.")


if __name__ == "__main__":
    run_selection()
