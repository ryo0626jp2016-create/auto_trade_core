# scripts/filter_asins.py
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import pandas as pd

from keepa_client import get_product_info, ProductStats
from rakuten_client import RakutenClient, RakutenItem


# -----------------------------
# 設定値（ここを変えれば条件調整できる）
# -----------------------------
MIN_PROFIT = 300          # 利益 300 円以上
MIN_ROI = 0.30            # ROI 30%以上
MAX_AVG_RANK_90D = 250000 # 高回転の目安
BLOCK_AMAZON_CURRENT = True  # 現在 Amazon 本体がカートなら弾く


@dataclass
class FilterResult:
    asin: str
    title: str

    # Keepa 指標
    avg_rank_90d: Optional[int]
    expected_sell_price: Optional[float]
    amazon_current: bool
    amazon_presence_ratio: Optional[float]
    amazon_buybox_count: Optional[int]

    # FBA 料金・利益系
    fba_fee_estimate: Optional[float]
    profit: Optional[float]
    roi: Optional[float]

    # 楽天側
    rakuten_price: Optional[float]
    rakuten_item_name: Optional[str]
    rakuten_item_url: Optional[str]

    # 元ファイルの追加カラムがあればここに載せる
    extra: Dict[str, Any]


# -----------------------------
# FBA 手数料の超ざっくり推定
# -----------------------------
def estimate_fba_fee(price: float, product: ProductStats) -> float:
    """
    正確な FBA 手数料ではなく、「安全側にちょっと盛った概算」を返す。
    - 15% 販売手数料
    - 100 円 ベース手数料
    - 送料やサイズはだいたい +80〜300 円 くらいを想定して、ここでは +200 円 に固定
    """
    if price is None or price <= 0:
        return 0.0

    # 販売手数料（15% を仮定）
    commission = price * 0.15

    # ベース＋配送系の固定費を 300 円 と仮置き
    base_and_shipping = 300.0

    return commission + base_and_shipping


# -----------------------------
# 楽天側の最安値取得（単純に1件目）
# -----------------------------
def find_rakuten_candidate(client: RakutenClient, asin: str, title: str) -> Optional[RakutenItem]:
    """
    まず ASIN で検索して、ヒットしなければタイトルで検索、というシンプルなロジック。
    """
    # 1) ASIN で検索
    item = client.search_by_keyword(asin)
    if item is not None:
        return item

    # 2) タイトルで検索（長すぎると微妙なので先頭 30 文字くらいにカット）
    keyword = (title or "")[:30]
    if not keyword:
        return None
    return client.search_by_keyword(keyword)


# -----------------------------
# 1 ASIN 分の判定ロジック
# -----------------------------
def evaluate_asin(asin: str, base_row: Dict[str, Any], rakuten_client: RakutenClient) -> Optional[FilterResult]:
    # --- Keepa から情報取得 ---
    product = get_product_info(asin)
    if product is None:
        print(f"[WARN] Keepa から情報が取れなかったためスキップ: {asin}")
        return None

    # 条件1: ランキング（高回転か）
    if product.avg_rank_90d is None or product.avg_rank_90d <= 0:
        print(f"[INFO] ランク情報なしのためスキップ: {asin}")
        return None

    if product.avg_rank_90d > MAX_AVG_RANK_90D:
        print(f"[INFO] ランク {product.avg_rank_90d} > {MAX_AVG_RANK_90D} のためスキップ: {asin}")
        return None

    # 条件2: Amazon 本体が現在カートかどうか
    if BLOCK_AMAZON_CURRENT and product.amazon_current:
        print(f"[INFO] 現在のカートが Amazon 本体のためスキップ: {asin}")
        return None

    # 想定販売価格
    sell_price = product.expected_sell_price
    if sell_price is None or sell_price <= 0:
        print(f"[INFO] 想定販売価格が取れないためスキップ: {asin}")
        return None

    # --- 楽天で仕入れ候補を探す ---
    rakuten_item = find_rakuten_candidate(rakuten_client, asin, product.title)
    if rakuten_item is None or rakuten_item.item_price is None or rakuten_item.item_price <= 0:
        print(f"[INFO] 楽天側で有効な商品が見つからないためスキップ: {asin}")
        return None

    buy_price = rakuten_item.item_price

    # --- FBA 手数料の概算 ---
    fba_fee = estimate_fba_fee(sell_price, product)

    # 利益と ROI
    profit = sell_price - fba_fee - buy_price
    roi = profit / buy_price if buy_price > 0 else None

    if profit < MIN_PROFIT:
        print(f"[INFO] 利益 {profit:.0f} 円 < {MIN_PROFIT} 円 のためスキップ: {asin}")
        return None

    if roi is None or roi < MIN_ROI:
        print(f"[INFO] ROI {roi:.2f} < {MIN_ROI:.2f} のためスキップ: {asin}")
        return None

    # extra に元の列をそのまま載せておく（ASIN と Title 以外）
    extra = dict(base_row)
    extra.pop("ASIN", None)
    extra.pop("asin", None)
    extra.pop("タイトル", None)
    extra.pop("title", None)

    return FilterResult(
        asin=asin,
        title=product.title or base_row.get("タイトル") or base_row.get("title") or "",
        avg_rank_90d=product.avg_rank_90d,
        expected_sell_price=sell_price,
        amazon_current=product.amazon_current,
        amazon_presence_ratio=product.amazon_presence_ratio,
        amazon_buybox_count=product.amazon_buybox_count,
        fba_fee_estimate=fba_fee,
        profit=profit,
        roi=roi,
        rakuten_price=rakuten_item.item_price,
        rakuten_item_name=rakuten_item.item_name,
        rakuten_item_url=rakuten_item.item_url,
        extra=extra,
    )


# -----------------------------
# メイン処理
# -----------------------------
def filter_asins(input_path: str, output_dir: str) -> None:
    print(f"[INFO] Loading candidate ASIN list from: {input_path}")

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    os.makedirs(output_dir, exist_ok=True)

    # 拡張子で読み分け
    _, ext = os.path.splitext(input_path)
    ext = ext.lower()

    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path)
    else:
        df = pd.read_csv(input_path)

    # ASIN列の候補
    asin_col_candidates = ["ASIN", "asin", "asin_code", "asinコード"]
    asin_col = None
    for c in asin_col_candidates:
        if c in df.columns:
            asin_col = c
            break

    if asin_col is None:
        raise ValueError(f"ASIN 列が見つかりませんでした。候補: {asin_col_candidates} / 実際の列: {list(df.columns)}")

    # 楽天クライアント初期化
    rakuten_client = RakutenClient.from_env()

    # 結果をカテゴリごとに分類したい場合、元ファイルにカテゴリ列があれば利用
    category_col_candidates = ["category", "カテゴリ", "大カテゴリ", "category_name"]
    category_col = None
    for c in category_col_candidates:
        if c in df.columns:
            category_col = c
            break

    # カテゴリ列がない場合は "uncategorized" でまとめる
    if category_col is None:
        df["_category_tmp"] = "uncategorized"
        category_col = "_category_tmp"

    all_results: List[FilterResult] = []

    # 1行ずつチェック
    for idx, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        if not asin or asin.lower() == "nan":
            continue

        category = str(row[category_col])
        print(f"\n=== Evaluating ASIN {asin} (category={category}) ===")

        result = evaluate_asin(asin, row.to_dict(), rakuten_client)
        if result is None:
            continue

        all_results.append(result)

    if not all_results:
        print("[INFO] 条件を満たした ASIN がありませんでした。")
        # 一応、空の Excel を出しておく
        empty_path = os.path.join(output_dir, "no_result.xlsx")
        pd.DataFrame([]).to_excel(empty_path, index=False)
        print(f"[INFO] 空の結果を {empty_path} に書き出しました。")
        return

    # DataFrame 化（extra を展開）
    records: List[Dict[str, Any]] = []
    for r in all_results:
        base = asdict(r)
        extra = base.pop("extra", {}) or {}
        base.update(extra)
        records.append(base)

    result_df = pd.DataFrame(records)

    # カテゴリ列があればカテゴリごとにファイル分割
    if category_col in df.columns:
        # result_df 側のカテゴリ列名は、元 extra から来ている可能性があるので再チェック
        possible_category_cols = [category_col, "category", "カテゴリ", "大カテゴリ"]
        cat_col_in_result = None
        for c in possible_category_cols:
            if c in result_df.columns:
                cat_col_in_result = c
                break

        if cat_col_in_result is None:
            # 見つからなければ 1 ファイルだけ出す
            out_path = os.path.join(output_dir, "filtered_asins.xlsx")
            result_df.to_excel(out_path, index=False)
            print(f"[INFO] Wrote result: {out_path}")
        else:
            for category, sub_df in result_df.groupby(cat_col_in_result):
                safe_cat = str(category).replace("/", "_").replace("\\", "_")
                out_path = os.path.join(output_dir, f"filtered_asins_{safe_cat}.xlsx")
                sub_df.to_excel(out_path, index=False)
                print(f"[INFO] Wrote result for category {category}: {out_path}")
    else:
        out_path = os.path.join(output_dir, "filtered_asins.xlsx")
        result_df.to_excel(out_path, index=False)
        print(f"[INFO] Wrote result: {out_path}")


# -----------------------------
# CLI エントリポイント
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keepa + 楽天で ASIN 候補を再フィルタして、利益が出そうなものだけ Excel に書き出すスクリプト。"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="入力ファイルパス（CSV または Excel）。例: data/output_selected.csv や data/ASIN候補リスト_美容_日用品.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="結果の Excel を出力するディレクトリ。例: output/filtered_asins",
    )

    args = parser.parse_args()
    filter_asins(args.input, args.output_dir)


if __name__ == "__main__":
    main()
