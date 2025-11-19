"""
filter_asins.py
Amazon候補リストを読み込み、Keepaと楽天で価格比較を行う。
【修正点】条件に合わない商品も「判定NG」としてCSVに残すように変更。
"""

from __future__ import annotations
import os
import csv
import argparse
from typing import List, Dict, Any

from scripts.keepa_client import get_product_info
from scripts.rakuten_client import RakutenClient

def load_candidates(file_path: str) -> List[Dict[str, str]]:
    """CSVから候補リストを読み込む（ヘッダーの大文字小文字を吸収）"""
    candidates = []
    if not os.path.exists(file_path):
        return candidates

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # ヘッダーを正規化（すべて小文字にするなどの処理があればベストだが、今回は柔軟に取得する）
        for row in reader:
            # キーを小文字に変換して新しい辞書を作る
            normalized_row = {k.lower().strip(): v for k, v in row.items() if k}
            candidates.append(normalized_row)
    return candidates

def save_results(results: List[Dict[str, Any]], output_path: str):
    """結果をCSVに保存"""
    if not results:
        print("No results to save.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fieldnames = list(results[0].keys())
    
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {len(results)} items to {output_path}")

def filter_asins(input_csv: str, output_csv: str):
    print(f"[INFO] Loading candidate ASIN list from: {input_csv}")
    candidates = load_candidates(input_csv)
    
    if not candidates:
        print("[WARN] No candidates found in input file.")
        return

    # 楽天クライアント初期化
    try:
        rakuten = RakutenClient()
        print("[INFO] Rakuten Client initialized.")
    except Exception:
        print("[WARN] Rakuten Client init failed. Rakuten search will be skipped.")
        rakuten = None

    final_list = []
    total = len(candidates)

    for i, row in enumerate(candidates, 1):
        # 'asin' または 'id' などのカラムを探す
        asin = row.get("asin") or row.get("id")
        if not asin:
            # デバッグ用：どんなキーがあるか表示
            print(f"Skipping row {i}: ASIN key not found. Keys: {list(row.keys())}")
            continue

        print(f"[{i}/{total}] Check {asin} ...", end=" ", flush=True)

        # 1. Keepa情報取得
        p_info = get_product_info(asin)
        if not p_info:
            print("Keepa: No Data -> Skip")
            continue

        # 2. 楽天検索
        rakuten_price = 0
        rakuten_url = ""
        shop_name = ""
        search_status = "Not Found"

        if rakuten:
            # 検索ワード：タイトル先頭40文字（長すぎるとヒットしないため）
            keyword = p_info.title[:40]
            items = rakuten.search_items(keyword)
            if items:
                best = items[0]
                rakuten_price = best.price
                rakuten_url = best.url
                shop_name = best.shop_name
                search_status = "Found"

        # 3. 利益計算
        amazon_price = p_info.expected_sell_price or p_info.amazon_current or 0
        profit = 0
        roi = 0.0
        
        # Amazon手数料（仮：15% + 500円(FBA配送代など)）
        fees = (amazon_price * 0.15) + 500
        
        judgment = "NG" # 仕入れ判定

        if amazon_price > 0 and rakuten_price > 0:
            profit = amazon_price - fees - rakuten_price
            if rakuten_price > 0:
                roi = profit / rakuten_price
            
            # 判定ロジック (例: 利益300円以上 かつ ROI 10%以上)
            if profit >= 300 and roi >= 0.1:
                judgment = "OK"
                print(f"Profit: ¥{int(profit)} (OK!)")
            else:
                judgment = "Low Profit"
                print(f"Profit: ¥{int(profit)} (Low)")
        else:
            print(f"Price Missing (Amz:{amazon_price}, Rak:{rakuten_price})")

        # 結果に追加（判定NGでもリストには残す！）
        res_row = {
            "judgment": judgment, # 判定結果
            "asin": asin,
            "title": p_info.title[:30] + "...",
            "amazon_price": amazon_price,
            "rakuten_price": rakuten_price,
            "profit": int(profit),
            "roi": round(roi, 2),
            "rank_90d": p_info.avg_rank_90d,
            "shop_name": shop_name,
            "search_status": search_status,
            "amazon_url": f"https://www.amazon.co.jp/dp/{asin}",
            "rakuten_url": rakuten_url
        }
        final_list.append(res_row)

    # 全件保存する
    save_results(final_list, output_csv)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    filter_asins(args.input, args.output)

if __name__ == "__main__":
    main()
