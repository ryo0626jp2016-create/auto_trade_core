"""
filter_asins.py
Amazonで見つけた候補リスト(CSV)を読み込み、
1. Keepaで最新情報を再確認
2. 楽天で商品を検索 (Rakuten API)
3. 利益計算を行い、最終的な仕入れリストを出力する
"""

from __future__ import annotations
import os
import csv
import argparse
import time
from typing import List, Dict, Any

# 【修正】 scripts. をつけてインポート
from scripts.keepa_client import get_product_info, ProductStats
from scripts.rakuten_client import RakutenClient, RakutenItem

def load_candidates(file_path: str) -> List[Dict[str, str]]:
    """CSVから候補リストを読み込む"""
    candidates = []
    if not os.path.exists(file_path):
        return candidates

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append(row)
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

    # 楽天クライアントの初期化
    try:
        rakuten = RakutenClient()
        print("[INFO] Rakuten Client initialized.")
    except Exception as e:
        print(f"[WARN] Rakuten Client init failed: {e}")
        print("Skipping Rakuten search...")
        rakuten = None

    final_list = []
    total = len(candidates)

    for i, row in enumerate(candidates, 1):
        asin = row.get("asin")
        if not asin:
            continue

        print(f"[{i}/{total}] Checking {asin} ...", end=" ", flush=True)

        # 1. Keepaで最新情報取得
        p_info = get_product_info(asin)
        if not p_info:
            print("Keepa No Data -> Skip")
            continue

        # 2. 楽天で検索 (キーワードはタイトルを使用)
        # ※ JANコードがあればそれがベストですが、今回は簡易的にタイトル先頭で検索
        rakuten_price = 0
        shop_name = ""
        rakuten_url = ""
        
        if rakuten:
            # 検索精度を上げるため、タイトルの先頭30文字程度を使用するか、メーカー型番があればそれを使う
            # ここではシンプルにタイトル全体で検索してみる（ヒットしない場合は調整が必要）
            search_keyword = p_info.title[:40] # 長すぎるとヒットしにくいので切る
            
            # 上限価格はAmazon価格以下に設定して検索するなど工夫可能
            r_items = rakuten.search_items(search_keyword)
            
            if r_items:
                # 最安値を取得
                best_item = r_items[0] # ソート済み前提
                rakuten_price = best_item.price
                shop_name = best_item.shop_name
                rakuten_url = best_item.url
                print(f"Rakuten Found: ¥{rakuten_price} ", end="")
            else:
                print("Rakuten Not Found ", end="")
                # 見つからなくてもリストには残す場合
                pass

        # 3. 利益計算 (簡易)
        # Amazon価格
        amazon_price = p_info.expected_sell_price or 0
        if amazon_price == 0 and p_info.amazon_current:
             amazon_price = p_info.amazon_current

        profit = 0
        roi = 0.0

        if amazon_price > 0 and rakuten_price > 0:
            # 手数料15% + 配送300円と仮定
            fees = (amazon_price * 0.15) + 300
            profit = amazon_price - fees - rakuten_price
            roi = profit / rakuten_price

        print(f"Profit: ¥{int(profit)}")

        # 結果行を作成
        res_row = {
            "asin": asin,
            "title": p_info.title,
            "amazon_price": amazon_price,
            "rakuten_price": rakuten_price,
            "profit": int(profit),
            "roi": round(roi, 2),
            "shop_name": shop_name,
            "rank_90d": p_info.avg_rank_90d,
            "amazon_url": f"https://www.amazon.co.jp/dp/{asin}",
            "rakuten_url": rakuten_url
        }
        
        # 利益が出る、もしくは楽天で見つかったものだけ残すなどのフィルタが可能
        # ここでは楽天で見つかったものは全て残す設定にします
        if rakuten_price > 0:
            final_list.append(res_row)

    # 保存
    save_results(final_list, output_csv)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    filter_asins(args.input, args.output)

if __name__ == "__main__":
    main()
