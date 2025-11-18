from __future__ import annotations

import os
import sys
import argparse
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import pandas as pd

from keepa_client import get_product_info, ProductStats
from rakuten_client import RakutenClient, RakutenItem


# -----------------------------
# 設定データクラス
# -----------------------------
@dataclass
class FilterConfig:
    """
    ASINフィルタリングの基準値。
    """
    min_profit: int = 300        # 最低粗利（円）
    min_roi: float = 0.3         # 最低ROI
    max_avg_rank_90d: int = 250000  # 90日平均ランキングの上限
    block_amazon_current_buybox: bool = True  # Amazon本体が現在カート取得中ならブロックするかどうか


# -----------------------------
# 利益計算系のユーティリティ
# -----------------------------
def calc_profit_and_roi(
    sell_price: Optional[float],
    cost_price: Optional[float],
    fba_fee: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """
    粗利とROIを計算する。
    FBA手数料(fba_fee)がNoneの場合は0として扱う。
    """
    if sell_price is None or cost_price is None:
        return None, None

    fee = fba_fee or 0.0
    profit = sell_price - cost_price - fee
    if profit <= 0:
        return profit, None

    roi = profit / cost_price if cost_price > 0 else None
    return profit, roi


# -----------------------------
# メインのフィルタロジック
# -----------------------------
def filter_asins(
    input_path: str,
    output_dir: str,
    config: Optional[FilterConfig] = None,
) -> None:
    """
    入力CSV/ExcelからASINの候補リストを読み込み、
    Keepa + 楽天 で絞り込み、カテゴリ別にExcelとして出力する。
    """
    if config is None:
        config = FilterConfig()

    print(f"[INFO] Loading candidate ASIN list from: {input_path}")

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    # 拡張子で読み分け
    _, ext = os.path.splitext(input_path)
    ext = ext.lower()

    if ext in [".csv", ".txt"]:
        df = pd.read_csv(input_path)
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path)
    else:
        print(f"[ERROR] Unsupported input format: {ext}")
        sys.exit(1)

    # ASIN 列の名称を推測
    asin_col_candidates = ["ASIN", "asin", "商品ASIN", "asin_code"]
    asin_col = None
    for c in asin_col_candidates:
        if c in df.columns:
            asin_col = c
            break

    if asin_col is None:
        print(f"[ERROR] ASIN column not found. columns={list(df.columns)}")
        sys.exit(1)

    # カテゴリ列の名称を推測
    category_col_candidates = ["カテゴリ", "category", "ジャンル"]
    category_col = None
    for c in category_col_candidates:
        if c in df.columns:
            category_col = c
            break

    if category_col is None:
        # なければ一括で "uncategorized"
        df["category_for_filter"] = "uncategorized"
        category_col = "category_for_filter"
    else:
        df["category_for_filter"] = df[category_col].fillna("uncategorized")
        category_col = "category_for_filter"

    # 仕入れ想定価格の列を推測（楽天 or 仕入れ値）
    cost_col_candidates = ["仕入れ想定価格", "楽天最安値", "仕入れ価格", "仕入値", "CostPrice"]
    cost_col = None
    for c in cost_col_candidates:
        if c in df.columns:
            cost_col = c
            break

    if cost_col is None:
        # 仕入れ価格の列がない場合は、後段で None のまま計算される（→粗利・ROI は計算不可）
        print("[WARN] Cost price column not found. Profit/ROI may not be calculated.")
    else:
        df["cost_price_for_filter"] = pd.to_numeric(df[cost_col], errors="coerce")
        cost_col = "cost_price_for_filter"

    # Amazon販売価格の列を推測（Fallback用）
    amazon_price_col_candidates = [
        "Amazon商品価格",
        "Amazon価格",
        "販売価格",
        "sell_price",
        "予想販売価格",
    ]
    amazon_price_col = None
    for c in amazon_price_col_candidates:
        if c in df.columns:
            amazon_price_col = c
            break

    if amazon_price_col is not None:
        df["amazon_price_for_filter"] = pd.to_numeric(df[amazon_price_col], errors="coerce")
        amazon_price_col = "amazon_price_for_filter"

    # 楽天APIクライアント
    rakuten_app_id = os.getenv("RAKUTEN_APPLICATION_ID")
    rakuten_client = None
    if rakuten_app_id:
        rakuten_client = RakutenClient(rakuten_app_id)
    else:
        print("[WARN] 楽天APIキー (RAKUTEN_APPLICATION_ID) が設定されていません。楽天検索はスキップされます。")

    os.makedirs(output_dir, exist_ok=True)

    result_rows: List[Dict[str, Any]] = []

    # 1行ずつ評価
    for _, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        category = str(row[category_col]).strip() or "uncategorized"
        print(f"\n=== Evaluating ASIN {asin} (category={category}) ===")

        # Keepa 情報取得
        product_info: Optional[ProductStats] = get_product_info(asin)
        if product_info is None:
            print(f"[WARN] Keepa から情報が取れなかったためスキップ: {asin}")
            continue

        # 販売価格は基本 Keepa の BuyBox を使用
        sell_price = product_info.expected_sell_price

        # 販売価格が取れない場合、入力CSV側の Amazon 価格をFallbackで使用
        if sell_price is None and amazon_price_col is not None:
            sell_price = row.get(amazon_price_col)
            if pd.notna(sell_price):
                sell_price = float(sell_price)
                print(f"[INFO] Keepaの販売価格が取れなかったため、入力CSVのAmazon価格を利用: {sell_price}")
            else:
                sell_price = None

        # 仕入れ価格
        cost_price = None
        if cost_col is not None:
            val = row.get(cost_col)
            if pd.notna(val):
                cost_price = float(val)

        # ここでは FBA 手数料は仮に 0 としておく（必要なら後で別計算ロジックを追加）
        fba_fee = 0.0

        profit, roi = calc_profit_and_roi(
            sell_price=sell_price,
            cost_price=cost_price,
            fba_fee=fba_fee,
        )

        # フィルタ条件チェック
        if product_info.avg_rank_90d is not None and product_info.avg_rank_90d > config.max_avg_rank_90d:
            print(f"[INFO] ランク {product_info.avg_rank_90d} が上限 {config.max_avg_rank_90d} より悪いため除外")
            continue

        if config.block_amazon_current_buybox and product_info.amazon_current:
            print("[INFO] Amazon本体が現在BuyBox取得中のため除外")
            continue

        if profit is not None and profit < config.min_profit:
            print(f"[INFO] 利益 {profit} 円 が閾値 {config.min_profit} 円未満のため除外")
            continue

        if roi is not None and roi < config.min_roi:
            print(f"[INFO] ROI {roi:.2f} が閾値 {config.min_roi:.2f} 未満のため除外")
            continue

        # 楽天側の最安値などを取得して情報付加（任意）
        rakuten_items: List[RakutenItem] = []
        if rakuten_client is not None:
            try:
                rakuten_items = rakuten_client.search_by_keyword(product_info.title, hits=3)
            except Exception as e:
                print(f"[WARN] 楽天API検索中にエラー発生: {e}")

        if rakuten_items:
            rakuten_min_price = min(it.price for it in rakuten_items if it.price is not None)
        else:
            rakuten_min_price = None

        # 結果行を構築
        result_row: Dict[str, Any] = {
            "ASIN": asin,
            "Category": category,
            "Title": product_info.title,
            "AvgRank90d": product_info.avg_rank_90d,
            "ExpectedSellPrice": sell_price,
            "CostPrice": cost_price,
            "Profit": profit,
            "ROI": roi,
            "AmazonPresenceRatio": product_info.amazon_presence_ratio,
            "AmazonBuyBoxCount": product_info.amazon_buybox_count,
            "AmazonCurrent": product_info.amazon_current,
            "WeightKg": product_info.weight_kg,
            "DimensionsCm": product_info.dimensions_cm,
            "KeepaCategory": product_info.category,
            "RakutenMinPrice": rakuten_min_price,
        }

        result_rows.append(result_row)

    # ---- 結果の出力 ----
    if not result_rows:
        print("[INFO] 条件を満たした ASIN がありませんでした。")
        empty_path = os.path.join(output_dir, "no_result.xlsx")
        print(f"[INFO] 空の結果ファイルを出力します: {empty_path}")
        pd.DataFrame([]).to_excel(empty_path, index=False)
        return

    result_df = pd.DataFrame(result_rows)

    # カテゴリごとにExcel出力
    for category, group in result_df.groupby("Category"):
        safe_category = category.replace("/", "_").replace("\\", "_")
        out_path = os.path.join(output_dir, f"filtered_{safe_category}.xlsx")
        print(f"[INFO] Writing filtered result for category '{category}' to: {out_path}")
        group.to_excel(out_path, index=False)


# -----------------------------
# エントリポイント
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter ASIN candidates using Keepa + Rakuten info."
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input CSV/Excel file path (e.g. data/output_selected.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save filtered ASIN Excel files.",
    )

    args = parser.parse_args()

    filter_asins(args.input, args.output_dir)


if __name__ == "__main__":
    main()
