# scripts/filter_asins.py

from __future__ import annotations

import argparse
import os
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from scripts.keepa_client import get_product_info, ProductStats


# 閾値（澤口さん指定）
TURNOVER_THRESHOLD_30D = 20      # 30日で20ドロップ以上（※ここは後でKeepa項目に合わせて調整）
MIN_PROFIT = 300                 # 利益300円以上
MIN_ROI = 30                     # ROI30%以上


def estimate_amazon_fee(price: Optional[float]) -> float:
    """
    簡易Amazon手数料モデル（ざっくり）
    ※あとでちゃんとカテゴリ別にしていけばOK
    """
    if price is None:
        return 0.0
    return price * 0.15 + 100  # 15% + 100円 仮置き


def calc_profit_and_roi(
    selling_price: Optional[float],
    cost_price: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if selling_price is None or cost_price is None or cost_price <= 0:
        return None, None

    fee = estimate_amazon_fee(selling_price)
    profit = selling_price - cost_price - fee
    roi = (profit / cost_price) * 100 if profit is not None else None
    return profit, roi


def detect_asin_column(df: pd.DataFrame) -> str:
    for cand in ["asin", "ASIN", "Asin"]:
        if cand in df.columns:
            return cand
    raise ValueError("ASIN列が見つかりません（asin / ASIN / Asin を想定）")


def detect_cost_column(df: pd.DataFrame) -> Optional[str]:
    """
    仕入れ価格の列候補
    （input_candidates.csv の列名に合わせて調整してもOK）
    """
    for cand in ["cost_price", "仕入れ価格", "cost", "仕入原価"]:
        if cand in df.columns:
            return cand
    return None


def filter_asins(
    input_path: str,
    output_dir: str,
) -> None:
    print(f"[INFO] filtering input: {input_path}")

    # CSV 固定（run_selection の出力に合わせる）
    df = pd.read_csv(input_path)

    asin_col = detect_asin_column(df)
    cost_col = detect_cost_column(df)

    if cost_col is None:
        print("[WARN] 仕入れ価格の列が見つからなかったため、コストは仮に 0 として扱います。")
        # コスト列が無い場合は 0 にして ROI 判定は実質スキップ気味になる
        df["__tmp_cost"] = 0.0
        cost_col = "__tmp_cost"

    os.makedirs(output_dir, exist_ok=True)

    selected_rows: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        cost_price = float(row[cost_col])

        print(f"[DEBUG] checking ASIN={asin}, cost_price={cost_price}")

        info: Optional[ProductStats] = get_product_info(asin)
        if info is None:
            print(f"[WARN] Keepa情報が取得できなかったためスキップ: {asin}")
            continue

        # TODO: 回転率条件（30日で20以上）については
        # 今の ProductStats にはドロップ回数を持っていないので、
        # ひとまず avg_rank_90d が小さいもの（=売れ行き良い）だけ残す簡易判定にしておく
        if info.avg_rank_90d is not None and info.avg_rank_90d > 100000:
            print(f"[DEBUG] ランクが重すぎるため除外: {asin} (avg_rank_90d={info.avg_rank_90d})")
            continue

        # Amazon本体不在条件
        if info.buybox_is_amazon or info.amazon_current:
            print(f"[DEBUG] BuyBoxがAmazon本体のため除外: {asin}")
            continue
        if info.amazon_presence_ratio is not None and info.amazon_presence_ratio > 0.3:
            print(f"[DEBUG] 過去にAmazon本体が居すぎるため除外: {asin} "
                  f"(presence_ratio={info.amazon_presence_ratio:.2f})")
            continue

        selling_price = info.expected_sell_price
        profit, roi = calc_profit_and_roi(selling_price, cost_price)

        if profit is None or roi is None:
            print(f"[DEBUG] 利益/ROIが計算できないため除外: {asin}")
            continue

        if profit < MIN_PROFIT or roi < MIN_ROI:
            print(f"[DEBUG] 利益条件を満たさないため除外: {asin} (profit={profit}, roi={roi})")
            continue

        selected_rows.append(
            {
                "asin": asin,
                "title": info.title,
                "avg_rank_90d": info.avg_rank_90d,
                "expected_sell_price": selling_price,
                "cost_price": cost_price,
                "profit": round(profit),
                "roi": round(roi, 1),
                "amazon_presence_ratio": info.amazon_presence_ratio,
                "amazon_buybox_count": info.amazon_buybox_count,
                "amazon_current": info.amazon_current,
                "buybox_is_amazon": info.buybox_is_amazon,
                "weight_kg": info.weight_kg,
                "dimensions_cm": info.dimensions_cm,
                "category": info.category,
            }
        )

    if not selected_rows:
        print("[INFO] 条件を満たすASINがありませんでした。空ファイルを出力します。")
        out_df = pd.DataFrame(columns=[
            "asin", "title", "avg_rank_90d", "expected_sell_price",
            "cost_price", "profit", "roi",
            "amazon_presence_ratio", "amazon_buybox_count",
            "amazon_current", "buybox_is_amazon",
            "weight_kg", "dimensions_cm", "category",
        ])
    else:
        out_df = pd.DataFrame(selected_rows)

    out_path = os.path.join(output_dir, "filtered_asins.csv")
    out_df.to_csv(out_path, index=False)
    print(f"[INFO] filtered ASIN list written to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        required=True,
        help="入力CSV (例: data/output_selected.csv)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/filtered_asins",
        help="出力ディレクトリ",
    )
    args = parser.parse_args()

    filter_asins(args.input, args.output_dir)


if __name__ == "__main__":
    main()