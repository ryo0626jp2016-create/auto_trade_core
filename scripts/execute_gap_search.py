import os
import csv
import pandas as pd
from scripts.rakuten_client import RakutenClient

# === 設定 ===
MIN_PROFIT = 500        # 最低利益額（円）
MIN_ROI = 10.0          # 最低利益率（%）
AMAZON_FEE_RATE = 0.10  # Amazon販売手数料（10%仮定）
FBA_FEE_FIXED = 550     # FBA配送代行手数料（標準サイズ仮定）

def calculate_metrics(amazon_price, rakuten_price, shipping):
    # 仕入れ値（商品 + 送料）
    cost = rakuten_price + shipping
    
    # Amazon入金額（売値 - 手数料）
    amz_fee = int(amazon_price * AMAZON_FEE_RATE)
    net_revenue = amazon_price - amz_fee - FBA_FEE_FIXED
    
    # 利益
    profit = net_revenue - cost
    
    # 利益率 (ROI)
    roi = (profit / cost * 100) if cost > 0 else 0
    
    return profit, roi

def main():
    input_csv = "data/order_list_keepa.csv"
    output_csv = "data/profitable_list.csv"
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    print(f"Loading {input_csv}...")
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        print(f"CSV Load Error: {e}")
        return

    if 'jan' not in df.columns:
        print("Error: CSV must contain 'jan' column.")
        return

    # JANがあるデータのみ抽出
    df = df.dropna(subset=['jan', 'target_price'])
    
    client = RakutenClient()
    results = []
    
    print(f"Starting Research for {len(df)} items...")
    
    for index, row in df.iterrows():
        # JANコードの整形（.0がついている場合などに対応）
        try:
            jan = str(int(float(row['jan'])))
        except:
            jan = str(row['jan'])
            
        amazon_price = int(row['target_price'])
        asin = row['asin']
        
        # 進捗表示
        if index % 10 == 0:
            print(f"Processing {index}/{len(df)}...")

        # 楽天リサーチ実行
        # Amazon価格より高いものはそもそも利益が出ないので検索上限にする
        rakuten_item = client.search_item(jan_code=jan, max_price=amazon_price)
        
        if rakuten_item:
            profit, roi = calculate_metrics(amazon_price, rakuten_item.price, rakuten_item.shipping)
            
            # 判定
            if profit >= MIN_PROFIT and roi >= MIN_ROI:
                print(f"💰 WINNER! ASIN:{asin} | Amz:{amazon_price} vs Rak:{rakuten_item.price} | Profit:{int(profit)} ({roi:.1f}%)")
                
                results.append({
                    "asin": asin,
                    "jan": jan,
                    "item_name": row['keyword'][:30], # 長すぎるのでカット
                    "amazon_price": amazon_price,
                    "rakuten_price": rakuten_item.price,
                    "rakuten_shipping": rakuten_item.shipping,
                    "profit": int(profit),
                    "roi": round(roi, 1),
                    "rakuten_url": rakuten_item.url,
                    "amazon_url": row['url']
                })
            else:
                # 利益が出ない場合のログ（デバッグ用、うるさければコメントアウト）
                # print(f"Skip: {asin} (Profit: {int(profit)})")
                pass

    # 結果の保存
    if results:
        result_df = pd.DataFrame(results)
        result_df.to_csv(output_csv, index=False)
        print(f"\nSuccessfully saved {len(results)} profitable items to {output_csv}")
    else:
        print("\nNo profitable items found in this batch.")

if __name__ == "__main__":
    main()
