"""
auto_research_manager.py
楽天ランキング(仕入れ) -> Keepa(Amazon価格) -> 利益計算 -> 発注CSV
"""
from __future__ import annotations
import csv
import os
import time
from datetime import datetime

from scripts.rakuten_client import RakutenClient
from scripts.keepa_client import find_product_by_keyword
from scripts.fba_calculator import calculate_fba_fees

# === 設定エリア ===
# 狙うジャンルID (例: 100939=コスメ, 100371=レディースファッション, 562637=家電)
# 空欄 "" なら総合ランキング
TARGET_GENRE_ID = "100939" 
MIN_PROFIT = 500   # 最低利益
MIN_ROI = 0.1      # 最低利益率(10%)

OUTPUT_FILE = f"data/order_list_{datetime.now().strftime('%Y%m%d')}.csv"

def run_research():
    print("=== Starting Auto Research (Reverse Sourcing) ===")
    
    # 1. 楽天から候補取得
    try:
        r_client = RakutenClient()
        items = r_client.get_ranking(genre_id=TARGET_GENRE_ID)
        print(f"[Rakuten] Fetched {len(items)} items from ranking.")
    except Exception as e:
        print(f"[Error] Failed to fetch Rakuten: {e}")
        return

    results = []

    for i, r_item in enumerate(items, 1):
        print(f"[{i}/{len(items)}] Checking: {r_item.name[:30]}...", end=" ")
        
        # 2. Amazonで検索 (JANがないのでタイトル検索)
        # 検索精度を高めるため、商品名の先頭部分だけを使う
        search_query = r_item.name[:40].replace("【", " ").replace("】", " ")
        
        k_item = find_product_by_keyword(search_query)
        
        if not k_item:
            print("-> Amazon Not Found.")
            continue

        # 3. 利益計算
        sell_price = k_item.expected_sell_price
        if not sell_price:
            print("-> No Amazon Price.")
            continue

        # FBA手数料計算
        fees = calculate_fba_fees(sell_price, k_item.weight_kg, k_item.dimensions_cm)
        buy_price = r_item.price
        
        profit = sell_price - buy_price - fees
        roi = profit / buy_price if buy_price > 0 else 0

        # 結果表示
        if profit >= MIN_PROFIT and roi >= MIN_ROI:
            print(f"-> OK! Profit: ¥{profit} (ROI: {roi:.1%})")
            status = "未発注"
        else:
            print(f"-> Low Profit: ¥{profit}")
            status = "利益不足"

        # 4. リスト追加
        results.append({
            "status": status, # 管理用
            "profit": int(profit),
            "roi": f"{roi:.1%}",
            "item_name": k_item.title,
            "asin": k_item.asin,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "fees": fees,
            "rakuten_url": r_item.url,
            "amazon_url": f"https://www.amazon.co.jp/dp/{k_item.asin}",
            "rank": k_item.avg_rank_90d
        })
        
        # API制限考慮
        time.sleep(1)

    # 5. CSV保存
    if results:
        os.makedirs("data", exist_ok=True)
        # 利益が出る順に並べ替え
        results.sort(key=lambda x: x["profit"], reverse=True)
        
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"\nSaved result to {OUTPUT_FILE}")
        print("Check the CSV and start ordering!")
    else:
        print("\nNo products matched the criteria.")

if __name__ == "__main__":
    run_research()
