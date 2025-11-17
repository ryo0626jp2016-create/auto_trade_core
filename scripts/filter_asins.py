# filter_asins.py

import os
import argparse
from typing import List, Dict, Any

import pandas as pd

from keepa_client import fetch_keepa_products, extract_keepa_metrics
from filter_asins import get_rakuten_lowest_price_by_jan, calc_profit_and_roi  # 自ファイル内に書くなら適宜修正


TURNOVER_THRESHOLD = 20      # 30日で20回以上
MIN_PROFIT = 300             # 利益300円以上
MIN_ROI = 30                 # ROI 30%以上


def detect_asin_column(df: pd.DataFrame) -> str:
    for cand in ["ASIN", "asin", "Asin"]:
        if cand in df.columns:
            return cand
    raise ValueError("ASIN列が見つかりません（ASIN / asin / Asin を想定）")


def detect_category_column(df: pd.DataFrame) -> str | None:
    for cand in ["カテゴリ", "カテゴリー", "category", "Category"]:
        if cand in df.columns:
            return cand
    return None


def filter_asins(
    input_path: str,
    output_dir: str,
) -> None:
    df = pd.read_excel(input_path)
    asin_col = detect_asin_column(df)
    cat_col = detect_category_column(df)

    # ASIN一覧
    asins: List[str] = (
        df[asin_col]
        .astype(str)
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )

    # Keepaでまとめて取得
    products = fetch_keepa_products(asins)
    product_by_asin: Dict[str, Dict[str, Any]] = {
        p.get("asin"): p for p in products
    }

    filtered_rows: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        product = product_by_asin.get(asin)
        if not product:
            continue

        m = extract_keepa_metrics(product)

        # 1) 回転率フィルタ
        drops = m.get("sales_rank_drops_30")
        if drops is None or drops < TURNOVER_THRESHOLD:
            continue

        # 2) Amazon本体不在
        if m.get("has_amazon_offer"):
            continue

        # 3) 楽天最安値取得（JANベース）
        jan = m.get("jan")
        rakuten_price = get_rakuten_lowest_price_by_jan(jan)
        if rakuten_price is None:
            continue

        # 4) 利益・ROI計算
        selling_price = m.get("selling_price")
        profit, roi = calc_profit_and_roi(selling_price, rakuten_price)

        if profit is None or roi is None:
            continue
        if profit < MIN_PROFIT or roi < MIN_ROI:
            continue

        out_row: Dict[str, Any] = {
            "ASIN": asin,
            "タイトル": m.get("title"),
            "回転数30日": drops,
            "Amazon販売価格(概算)": selling_price,
            "楽天最安価格": rakuten_price,
            "概算利益": round(profit),
            "ROI(%)": round(roi, 1),
        }

        if cat_col:
            out_row["カテゴリ"] = row[cat_col]

        filtered_rows.append(out_row)

    if not filtered_rows:
        print("条件を満たすASINがありませんでした。")
        return

    out_df = pd.DataFrame(filtered_rows)

    os.makedirs(output_dir, exist_ok=True)

    # 全体まとめ
    all_path = os.path.join(output_dir, "filtered_asins_all.xlsx")
    out_df.to_excel(all_path, index=False)
    print(f"全体ファイルを出力しました: {all_path}")

    # カテゴリ別出力
    if "カテゴリ" in out_df.columns:
        for cat, g in out_df.groupby("カテゴリ"):
            safe_cat = str(cat) if cat else "unknown"
            fname = f"filtered_asins_{safe_cat}.xlsx"
            path = os.path.join(output_dir, fname)
            g.to_excel(path, index=False)
            print(f"カテゴリ別ファイルを出力しました: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        required=True,
        help="ASIN候補リストExcelパス（例: data/ASIN候補リスト_美容_日用品.xlsx）",
    )
    parser.add_argument(
        "--output-dir",
        default="output/filtered_asins",
        help="出力先ディレクトリ",
    )
    args = parser.parse_args()

    filter_asins(args.input, args.output_dir)


if __name__ == "__main__":
    main()