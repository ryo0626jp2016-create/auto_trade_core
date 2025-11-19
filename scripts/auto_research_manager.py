"""
auto_research_manager.py
【高速・高精度版】 楽天ランキング -> あいまい検索(2秒) -> 利益品抽出
"""
from __future__ import annotations
import csv
import os
import time
import re
from datetime import datetime

from scripts.rakuten_client import RakutenClient
from scripts.keepa_client import find_product_by_keyword
from scripts.fba_calculator import calculate_fba_fees

TARGET_GENRES = [
    {"id": "100939", "name": "美容・コスメ"},
    {"id": "562637", "name": "家電"},
    {"id": "215783", "name": "日用品・雑貨"},
    {"id": "101213", "name": "ペット用品"},
]

MIN_PROFIT = 300       # 少し緩めて広く拾う
MIN_ROI = 0.10
MAX_RANK = 100000

OUTPUT_FILE = f"data/order_list_{datetime.now().strftime('%Y%m%d')}.csv"

def clean_product_name(name: str) -> str:
    """楽天特有のノイズを除去してAmazon検索にヒットしやすくする"""
    # 【】や[]の中身ごと削除
    name = re.sub(r'【.*?】', ' ', name)
    name = re.sub(r'\[.*?\]', ' ', name)
    name = re.sub(r'\(.*?\)', ' ', name)
    
    # ノイズワード削除
    noise = ["送料無料", "公式", "正規品", "楽天", "ポイント", "倍", "クーポン", "OFF", "SALE", "即納"]
    for n in noise:
        name = name.replace(n, " ")
        
    # 空白を整理して、先頭30文字を取得 (Amazon検索は短い方がヒットしやすい)
    return " ".join(name.split())[:30]

def run_research():
    print("=== Starting Auto Research (Fuzzy Search Mode) ===")
    print(f"[Settings] Wait: 2s per item. Min Profit: ¥{MIN_PROFIT}")
    
    try:
        r_client = RakutenClient()
    except Exception as e:
        print(f"[CRITICAL ERROR] Rakuten Client Init Failed: {e}")
        return

    all_candidates = []

    for genre in TARGET_GENRES:
        print(f"\n>>> Scanning Genre: {genre['name']} <<<")
        try:
            items = r_client.get_ranking(genre_id=genre['id'])
            print(f"[Rakuten] Fetched {len(items)} items.")
        except:
            continue

        # テスト用: 上位10件ずつチェック (慣れたら items[:10] を items に戻して全件へ)
        check_items = items[:10]

        for i, r_item in enumerate(check_items, 1):
            # クリーニング後の名称
            search_query = clean_product_name(r_item.name)
            
            print(f"[{i}/{len(check_items)}] search: '{search_query}' ...", end=" ")
            
            # コストが1トークンになったので2秒待てば余裕で回復する
            time.sleep(2)

            k_item = find_product_by_keyword(search_query)
            
            if not k_item:
                print("-> Not Found.")
                continue

            # === フィルター ===
            if k_item.amazon_current is not None:
                print("-> NG (Amazon Exists)")
                continue

            if k_item.avg_rank_90d is None or k_item.avg_rank_90d > MAX_RANK:
                print(f"-> NG (Rank: {k_item.avg_rank_90d})")
                continue
                
            sell_price = k_item.expected_sell_price
            if not sell_price:
                print("-> NG (No Price)")
                continue

            # 利益計算
            fees = calculate_fba_fees(sell_price, k_item.weight_kg, k_item.dimensions_cm)
            buy_price = r_item.price
            profit = sell_price - buy_price - fees
            roi = profit / buy_price if buy_price > 0 else 0

            if profit >= MIN_PROFIT and roi >= MIN_ROI:
                print(f"-> ★OK! ¥{profit}")
                all_candidates.append({
                    "genre": genre['name'],
                    "status": "未発注",
                    "item_name": k_item.title,
                    "profit": int(profit),
                    "roi": f"{roi:.1%}",
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "fees": fees,
                    "rank": k_item.avg_rank_90d,
                    "rakuten_url": r_item.url,
                    "amazon_url": f"https://www.amazon.co.jp/dp/{k_item.asin}",
                    "asin": k_item.asin
                })
            else:
                print(f"-> Low Profit (¥{profit})")

    # 保存
    if all_candidates:
        os.makedirs("data", exist_ok=True)
        all_candidates.sort(key=lambda x: x["profit"], reverse=True)
        
        fieldnames = ["status", "genre", "item_name", "profit", "roi", "buy_price", "sell_price", "fees", "rank", "rakuten_url", "amazon_url", "asin"]
        
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_candidates)
            
        print(f"\n[SUCCESS] Saved {len(all_candidates)} items to {OUTPUT_FILE}")
    else:
        print("\n[RESULT] No profitable items found in this batch.")

if __name__ == "__main__":
    run_research()
