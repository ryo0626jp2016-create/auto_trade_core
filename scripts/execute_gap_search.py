import os
import csv
import pandas as pd
from scripts.rakuten_client import RakutenClient

# 設定：利益いくら以上ならOKとするか
MIN_PROFIT = 500
# 設定：FBA手数料の概算（サイズ情報がないため、一律この金額で仮計算します）
# ※本来はサイズごとに変えるべきですが、まずはこれでフィルタリングします
DEFAULT_FBA_FEE = 600 

def calculate_profit(amazon_price, rakuten_price, shipping):
    """
    利益計算式：
    Amazon価格 - (Amazon手数料10% + FBA手数料) - (楽天価格 + 送料)
    """
    # Amazon手数料（カテゴリによりますが平均10%と仮定）
    amz_fee = int(amazon_price * 0.10)
    
    # 手残り
    revenue = amazon_price - amz_fee - DEFAULT_FBA_FEE
    
    # 仕入れコスト
    cost = rakuten_price + shipping
    
    return revenue - cost

def main():
    input_csv = "data/order_list_keepa.csv"
    output_csv = "data/profitable_list.csv"
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} が見つかりません。")
        return

    print("Loading data...")
    df = pd.read_csv(input_csv)
    
    # JANコードがないデータはスキップ
    if 'jan' not in df.columns:
        print("Error: CSVに 'jan' 列がありません。")
        return
        
    df = df.dropna(subset=['jan', 'target_price'])
    
    client = RakutenClient()
    results = []
    
    print(f"Starting search for {len(df)} items...")
    
    for index, row in df.iterrows():
        jan = str(row['jan']).replace('.0', '') # JANのフォーマット整形
        amazon_price = int(row['target_price'])
        asin = row['asin']
        
        # 楽天で検索
        # 少なくともAmazon価格より安くないと意味がないので max_price を設定してAPIリクエストを節約
        rakuten_item = client.search_item(jan_code=jan, max_price=amazon_price)
        
        if rakuten_item:
            profit = calculate_profit(amazon_price, rakuten_item.price, rakuten_item.shipping)
            roi = round((profit / rakuten_item.price) * 100, 1) if rakuten_item.price > 0 else 0
            
            print(f"ASIN: {asin} | Amz: {amazon_price}円 vs Rak: {rakuten_item.price}円 | 利益: {profit}円")
            
            if profit >= MIN_PROFIT:
                results.append({
                    "asin": asin,
                    "jan": jan,
                    "amazon_price": amazon_price,
                    "rakuten_price": rakuten_item.price,
                    "shipping": rakuten_item.shipping,
                    "profit": profit,
                    "roi": roi,
                    "rakuten_url": rakuten_item.url,
                    "amazon_url": row['url']
                })
        else:
            # 見つからない、または高すぎる場合
            pass

    # 結果保存
    if results:
        result_df = pd.DataFrame(results)
        result_df.to_csv(output_csv, index=False)
        print(f"\nSearch Complete! Found {len(results)} profitable items.")
        print(f"Saved to: {output_csv}")
    else:
        print("\nNo profitable items found in this batch.")

if __name__ == "__main__":
    main()
