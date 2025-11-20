"""
auto_research_manager.py
【接続テスト用】 各ジャンルTOP1商品のみ、65秒間隔で確実にリサーチ
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

# === ジャンル ===
TARGET_GENRES = [
    {"id": "100939", "name": "美容・コスメ"},
    {"id": "562637", "name": "家電"},
    {"id": "215783", "name": "日用品・雑貨"},
    {"id": "101213", "name": "ペット用品"},
]

# === 判定基準 (テストなので緩く設定) ===
MIN_PROFIT = 1         # 1円以上ならリストに入れる
MIN_ROI = 0.01         # 1%以上なら入れる
MAX_RANK = 500000      # ほぼ何でもOK

OUTPUT_FILE = f"data/order_list_{datetime.now().strftime('%Y%m%d')}.csv"

def clean_product_name(name: str) -> str:
    """検索精度向上のための整形"""
    name = re.sub(r'【.*?】', ' ', name)
    name = re.sub(r'\(.*?\)', ' ', name)
    name = re.sub(r'\[.*?\]', ' ', name)
    name = name.replace("送料無料", "").replace("公式", "").replace("正規品", "").replace("楽天", "")
    # 長すぎるとヒットしないので35文字制限
    return name.strip()[:35]

def run_research():
    print("=== Starting Connection Test (1 Item/Genre, 65s Wait) ===")
    
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
            print(f"[Rakuten] Fetched items.")
        except:
            print("Rakuten Fetch Error")
            continue

        if not items:
            continue

        # 【テスト用】各ジャンル 1位の商品だけチェック
        top_item = items[0] 
        
        print(f"[Check] {top_item.name[:15]}...", end=" ")
        
        # 【重要】65秒待つ (これで回復しないプランはない)
        time.sleep(65)

        # 検索
        search_query = clean_product_name(top_item.name)
        k_item = find_product_by_keyword(search_query)
        
        if not k_item:
            print("-> Amazon Not Found.")
            continue

        # データ取得成功！
        print(f"-> Found! (ASIN: {k_item.asin})")

        # 利益計算
        sell_price = k_item.expected_sell_price
        if not sell_price:
            print("-> No Price")
            # テストなので売価がなくても、Amazonで見つかった事実を残すために保存しても良いが
            # 計算エラーになるので今回はスキップ
            continue

        fees = calculate_fba_fees(sell_price, k_item.weight_kg, k_item.dimensions_cm)
        buy_price = top_item.price
        profit = sell_price - buy_price - fees
        roi = profit / buy_price if buy_price > 0 else 0

        print(f"   Profit: {profit} yen")

        # テストなので条件に関わらずAmazonで見つかれば保存候補へ
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
            "rakuten_url": top_item.url,
            "amazon_url": f"https://www.amazon.co.jp/dp/{k_item.asin}",
            "asin": k_item.asin
        })

    # 保存
    if all_candidates:
        os.makedirs("data", exist_ok=True)
        
        fieldnames = ["status", "genre", "item_name", "profit", "roi", "buy_price", "sell_price", "fees", "rank", "rakuten_url", "amazon_url", "asin"]
        
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_candidates)
            
        print(f"\n[SUCCESS] Test Complete! Saved {len(all_candidates)} items to {OUTPUT_FILE}")
    else:
        print("\n[RESULT] No items found (Keepa search failed or no price).")

if __name__ == "__main__":
    run_research()
