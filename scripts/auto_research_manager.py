"""
auto_research_manager.py
AI厳選の複数ジャンルを巡回 -> 楽天ランキング -> Amazon不在＆利益品を抽出 -> 発注リスト化
"""
from __future__ import annotations
import csv
import os
import time
from datetime import datetime

from scripts.rakuten_client import RakutenClient
from scripts.keepa_client import find_product_by_keyword
from scripts.fba_calculator import calculate_fba_fees

# === AI厳選：稼げるジャンルリスト ===
TARGET_GENRES = [
    {"id": "100939", "name": "美容・コスメ"}, # 回転率最強・FBA手数料安い
    {"id": "562637", "name": "家電"},        # 単価が高い・利益額大きい
    {"id": "215783", "name": "日用品・雑貨"}, # 安定需要
    {"id": "101213", "name": "ペット用品"},   # ライバル少なめ
]

# === 判定基準 ===
MIN_PROFIT = 500       # 最低利益 (円)
MIN_ROI = 0.10         # 最低利益率 (10%) - 幅広く拾うため少し下げました
MAX_RANK = 80000       # ランキング上限 (8万位以内ならかなり売れている)

OUTPUT_FILE = f"data/order_list_{datetime.now().strftime('%Y%m%d')}.csv"

def run_research():
    print("=== Starting Auto Research (Multi-Genre Mode) ===")
    print(f"[Settings] Skip Amazon Sellers. Min Profit: ¥{MIN_PROFIT}")
    
    try:
        r_client = RakutenClient()
    except Exception as e:
        print(f"[CRITICAL ERROR] Rakuten Client Init Failed: {e}")
        return

    all_candidates = []

    # 1. 各ジャンルを巡回してリサーチ
    for genre in TARGET_GENRES:
        print(f"\n>>> Scanning Genre: {genre['name']} (ID: {genre['id']}) <<<")
        
        try:
            items = r_client.get_ranking(genre_id=genre['id'])
            print(f"[Rakuten] Fetched {len(items)} items.")
        except Exception as e:
            print(f"[Error] Failed to fetch genre {genre['name']}: {e}")
            continue

        for i, r_item in enumerate(items, 1):
            print(f"[{i}/{len(items)}] {r_item.name[:15]}...", end=" ")
            
            # 【修正】API制限回避のため、待機時間を3秒に延長
            # REQUEST_REJECTED エラー対策
            time.sleep(3)

            # Amazonで検索 (検索精度向上のため記号を除去)
            search_query = r_item.name[:40].replace("【", " ").replace("】", " ")
            k_item = find_product_by_keyword(search_query)
            
            if not k_item:
                print("-> Amazon Not Found.")
                continue

            # === 安全フィルター (Safety Filters) ===
            
            # ① Amazon本体がいるか (最重要)
            # keepa_client側で在庫なしはNoneになるよう調整済み
            if k_item.amazon_current is not None:
                print("-> NG (Amazon Exists)")
                continue

            # ② ランキングチェック
            if k_item.avg_rank_90d is None or k_item.avg_rank_90d > MAX_RANK:
                rank_display = k_item.avg_rank_90d if k_item.avg_rank_90d else "Unknown"
                print(f"-> NG (Rank: {rank_display})")
                continue
                
            # ③ 売価チェック
            sell_price = k_item.expected_sell_price
            if not sell_price:
                print("-> NG (No Price)")
                continue

            # 利益計算 (FBA手数料込)
            fees = calculate_fba_fees(sell_price, k_item.weight_kg, k_item.dimensions_cm)
            buy_price = r_item.price
            
            profit = sell_price - buy_price - fees
            roi = profit / buy_price if buy_price > 0 else 0

            # 判定
            if profit >= MIN_PROFIT and roi >= MIN_ROI:
                print(f"-> ★OK! Profit: ¥{profit} (ROI: {roi:.1%})")
                
                all_candidates.append({
                    "genre": genre['name'], # どのジャンルか
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

    # 2. 全ジャンルの結果をまとめて保存
    if all_candidates:
        os.makedirs("data", exist_ok=True)
        # 利益額が高い順に並べ替え（一番儲かる商品を一番上に）
        all_candidates.sort(key=lambda x: x["profit"], reverse=True)
        
        fieldnames = ["status", "genre", "item_name", "profit", "roi", "buy_price", "sell_price", "fees", "rank", "rakuten_url", "amazon_url", "asin"]
        
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_candidates)
            
        print(f"\n" + "="*50)
        print(f" [SUCCESS] Total {len(all_candidates)} profitable items found across {len(TARGET_GENRES)} genres!")
        print(f" Saved to: {OUTPUT_FILE}")
        if all_candidates:
            print(f" Top Item Profit: ¥{all_candidates[0]['profit']}")
        print("="*50)
    else:
        print("\n[RESULT] Unfortunately, no items matched the criteria this time.")

if __name__ == "__main__":
    run_research()
