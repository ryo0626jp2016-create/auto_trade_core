"""
scripts/smart_hunter.py
PC周辺機器と純正インクに特化した、高効率利益ハンター
"""
import os
import time
import csv
import random
from datetime import datetime

# 既存モジュールの再利用
from scripts.keepa_client import find_product_by_keyword, get_product_info
from scripts.rakuten_client import RakutenClient
from scripts.evaluator import evaluate_item
from scripts.fba_calculator import calculate_fba_fees

# === ターゲット設定 ===
# ここに「Amazon在庫切れになりやすい」黄金キーワードを定義
TARGET_KEYWORDS = [
    # --- 攻め：ゲーミングデバイス (利益額重視) ---
    "Logicool G PRO X Superlight",
    "Logicool G502 X",
    "Logicool G913 TKL",
    "Logicool G703h",
    "Razer Viper V2 Pro",
    "Razer DeathAdder V3",
    "Elgato Stream Deck MK.2",
    
    # --- 守り：純正インク (回転重視・セット品) ---
    "エプソン 純正 インク カメ 6色",
    "エプソン 純正 インク サツマイモ 6色",
    "キヤノン 純正 インク BCI-381+380/6MP",
    "キヤノン 純正 インク BCI-331+330/6MP"
]

OUTPUT_FILE = f"data/hunter_result_{datetime.now().strftime('%Y%m%d')}.csv"

def main():
    print("=== 🦅 Smart Hunter Started (Target: PC/Ink) ===")
    
    rakuten = RakutenClient()
    results = []
    
    for i, keyword in enumerate(TARGET_KEYWORDS):
        print(f"\n[{i+1}/{len(TARGET_KEYWORDS)}] Searching: {keyword} ...")
        
        # 1. Keepaで商品を検索 (Amazon在庫切れかどうかは後で判定)
        # find_product_by_keyword は既存の関数を利用
        product_stats = find_product_by_keyword(keyword)
        
        if not product_stats:
            print("   -> Keepa: Not Found or API Limit.")
            time.sleep(2)
            continue
            
        # 2. 評価ロジック (evaluator.py) を利用
        # 仕入れ値0円で仮評価し、Amazon在庫切れかチェックする
        # config.tomlの block_amazon_current_buybox = true が効く
        evaluation = evaluate_item(product_stats.asin, 0, product_stats)
        
        if evaluation["is_ok"] is False:
            # Amazon本体がいる、またはランキングが悪すぎる場合はスキップ
            if "Amazon currently has the buy box" in evaluation["reason"]:
                print(f"   -> NG: Amazon在庫あり (現在値: {product_stats.amazon_current}円)")
            else:
                print(f"   -> NG: {evaluation['reason']}")
            
            # Access 20プラン対策: 短時間に連打しすぎない
            time.sleep(2)
            continue

        print(f"   -> ✨ Amazon在庫切れの可能性大！ (想定売価: {product_stats.expected_sell_price}円)")
        
        # 3. 楽天で仕入れ値をチェック
        # JANコードがあればJANで、なければキーワードで検索
        search_key = keyword # JAN取得ロジックがあればそちらを優先したいが、今回はキーワードで簡易化
        rakuten_item = rakuten.search_item(keyword=search_key)
        
        if not rakuten_item:
            print("   -> Rakuten: Stock Not Found.")
            continue
            
        # 4. 最終利益計算
        sell_price = product_stats.expected_sell_price
        buy_price = rakuten_item.price
        shipping = rakuten_item.shipping
        
        # FBA手数料計算 (既存モジュール利用)
        fba_fee = calculate_fba_fees(sell_price, product_stats.weight_kg, product_stats.dimensions_cm)
        
        # 利益 = 売値 - (仕入れ + 送料) - (Amazon販売手数料10% + FBA手数料)
        # ※PC周辺機器の手数料は8~10%だが安全を見て10%計算
        amazon_referral_fee = int(sell_price * 0.10)
        total_cost = buy_price + shipping + amazon_referral_fee + fba_fee
        profit = sell_price - total_cost
        roi = (profit / (buy_price + shipping)) * 100 if buy_price > 0 else 0
        
        print(f"   💰 試算: 利益 {profit}円 (ROI {roi:.1f}%)")
        print(f"      仕入: {buy_price}円 (送{shipping}) -> 売: {sell_price}円")

        # 5. 利益が出るならリストに追加 (利益500円以上 または ROI 5%以上)
        # ※インクは薄利でも回転するので条件を甘くしても良い
        if profit > 500 or roi > 5.0:
            print("   -> 🎯 HIT! リストに追加します。")
            results.append({
                "ASIN": product_stats.asin,
                "商品名": product_stats.title,
                "Amazon想定売価": sell_price,
                "楽天仕入価格": buy_price,
                "楽天送料": shipping,
                "粗利益": profit,
                "利益率(ROI)": round(roi, 1),
                "FBA手数料": fba_fee,
                "楽天URL": rakuten_item.url,
                "KeepaURL": f"https://keepa.com/#!product/5-{product_stats.asin}"
            })
        
        # 連続アクセス防止の待機
        time.sleep(5)

    # 結果保存
    if results:
        os.makedirs("data", exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"\nSUCCESS: {len(results)}件の利益商品を {OUTPUT_FILE} に保存しました。")
    else:
        print("\nRESULT: 今回は利益商品が見つかりませんでした。")

if __name__ == "__main__":
    main()
