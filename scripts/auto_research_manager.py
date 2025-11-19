"""
auto_research_manager.py
【低負荷版】 楽天ランキング -> 徹底待機(10秒) -> Amazon不在＆利益品を抽出
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

# === 判定基準 ===
MIN_PROFIT = 500
MIN_ROI = 0.10
MAX_RANK = 80000

OUTPUT_FILE = f"data/order_list_{datetime.now().strftime('%Y%m%d')}.csv"

def clean_product_name(name: str) -> str:
    """検索精度を上げ、負荷を下げるために商品名をきれいにする"""
    # 【】や()の中身を削除
    name = re.sub(r'【.*?】', ' ', name)
    name = re.sub(r'\(.*?\)', ' ', name)
    name = re.sub(r'\[.*?\]', ' ', name)
    # 特定のキーワード削除
    name = name.replace("送料無料", "").replace("公式", "").replace("正規品", "").replace("楽天", "")
    # 先頭35文字だけ使う
    return name.strip()[:35]

def run_research():
    print("=== Starting Auto Research (Low Load Mode) ===")
    print(f"[Settings] Wait: 10s per item to avoid API limit.")
    
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

        # ジャンルごとに上位5件だけにする（さらに負荷を下げるため。慣れたら増やしてください）
        # ※最初は確実に成功させるため数を絞ります
        items = items[:5]

        for i, r_item in enumerate(items, 1):
            print(f"[{i}/{len(items)}] {r_item.name[:10]}...", end=" ")
            
            # 【重要】絶対に止まらないように10秒待つ
            time.sleep(10)

            # 商品名を整形して検索
            search_query = clean_product_name(r_item.name)
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
                print(f"-> Low Profit")

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
        print("\n[RESULT] No items matched.")

if __name__ == "__main__":
    run_research()
