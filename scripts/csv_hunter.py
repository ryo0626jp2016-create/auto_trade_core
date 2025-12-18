"""
scripts/csv_hunter.py
KeepaからエクスポートしたCSVを読み込み、楽天と価格比較を行う超高速リサーチツール
"""
import os
import glob
import pandas as pd
import time
from datetime import datetime
from scripts.rakuten_client import RakutenClient
from scripts.fba_calculator import calculate_fba_fees

# === 設定 ===
INPUT_DIR = "data/raw_keepa"   # CSVを置く場所
OUTPUT_FILE = f"data/hunter_result_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

# 利益基準
MIN_PROFIT = 300      # 最低利益額
MIN_ROI = 5.0         # 最低利益率(%)

def clean_price(value):
    """価格のクリーニング (¥マークやカンマを除去)"""
    if pd.isna(value) or value == '':
        return 0
    s = str(value).replace('¥', '').replace(',', '').replace(' ', '').strip()
    try:
        return int(float(s))
    except ValueError:
        return 0

def get_fba_fee_estimate(row):
    """CSVのサイズ情報からFBA手数料を概算"""
    # カラム名の揺れに対応
    weight_g = row.get('パッケージ: 重さ (g)', 0)
    size_cm3 = row.get('パッケージ: サイズ (cm³)', 0)
    
    # データがない場合は標準的な値を仮定
    if pd.isna(weight_g): weight_g = 200
    if pd.isna(size_cm3): size_cm3 = 1000
    
    # 簡易計算 (寸法が不明なため体積と重量で推測)
    # 小型軽量: 重さ1kg以下 かつ 体積小さめ -> 434円 (配送代行+諸経費)
    # 標準: -> 514円〜
    fee = 450 # ベース
    if weight_g > 1000 or size_cm3 > 15000:
        fee = 700 # 大型扱い
    elif weight_g > 500:
        fee = 550
        
    return fee

def main():
    print("=== 📂 CSV Hunter Started ===")
    
    # CSVファイルを探す
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    if not csv_files:
        print(f"ERROR: {INPUT_DIR} フォルダにCSVファイルが見つかりません。")
        return

    rakuten = RakutenClient()
    results = []
    
    for csv_file in csv_files:
        print(f"Loading: {csv_file}")
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            print(f"Error reading {csv_file}: {e}")
            continue

        print(f"Found {len(df)} items. Starting research...")

        for index, row in df.iterrows():
            # JANコード (EAN) の取得
            jan = row.get('商品コード: EAN')
            if pd.isna(jan):
                continue
            jan = str(int(float(jan))) # "4988..." の形式にする

            # Amazon価格の取得 (Buy Box 優先 -> Amazon -> 新品)
            amazon_price = clean_price(row.get('Buy Box 🚚: 現在価格'))
            if amazon_price == 0:
                amazon_price = clean_price(row.get('Amazon: 現在価格'))
            if amazon_price == 0:
                amazon_price = clean_price(row.get('新品: 現在価格'))
            
            if amazon_price == 0:
                continue

            # タイトル
            title = str(row.get('商品名', 'Unknown'))[:30]
            asin = str(row.get('ASIN', ''))

            # 楽天リサーチ
            print(f"[{index+1}/{len(df)}] Check: {jan} (Amz: {amazon_price}円)", end=" ... ")
            
            rakuten_item = rakuten.search_item(jan_code=jan)
            
            if not rakuten_item:
                print("Rakuten: Not Found")
                continue

            # 利益計算
            buy_price = rakuten_item.price
            shipping = rakuten_item.shipping
            
            # 手数料計算
            referral_fee = int(amazon_price * 0.10) # 販売手数料10%
            fba_fee = get_fba_fee_estimate(row)
            
            total_cost = buy_price + shipping + referral_fee + fba_fee
            profit = amazon_price - total_cost
            roi = (profit / (buy_price + shipping)) * 100 if buy_price > 0 else 0

            if profit >= MIN_PROFIT or roi >= MIN_ROI:
                print(f"💰 HIT! Profit: {profit}円 ({roi:.1f}%)")
                results.append({
                    "判定": "利益あり",
                    "商品名": title,
                    "ASIN": asin,
                    "JAN": jan,
                    "Amazon価格": amazon_price,
                    "楽天仕入": buy_price,
                    "楽天送料": shipping,
                    "粗利益": profit,
                    "利益率(ROI)": round(roi, 1),
                    "FBA手数料(概算)": fba_fee,
                    "楽天URL": rakuten_item.url,
                    "AmazonURL": f"https://www.amazon.co.jp/dp/{asin}"
                })
            else:
                print(f"Low Profit ({profit}円)")
            
            # API制限考慮
            time.sleep(1)

    # 結果保存
    if results:
        os.makedirs("data", exist_ok=True)
        # pandasで保存
        res_df = pd.DataFrame(results)
        res_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"\nSUCCESS: {len(results)}件の利益商品を {OUTPUT_FILE} に保存しました。")
    else:
        print("\nRESULT: 利益商品は見つかりませんでした。")

if __name__ == "__main__":
    main()
