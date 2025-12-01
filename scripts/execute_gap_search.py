import os
import csv
import pandas as pd
from scripts.rakuten_client import RakutenClient

# === 設定 ===
MIN_PROFIT = 200        # 最低利益額（円）※少し下げて広く拾う
MIN_ROI = 5.0           # 最低利益率（%） ※ポイント込みなら5%~10%目安
AMAZON_FEE_RATE = 0.10  # Amazon販売手数料（10%仮定）

# 【重要】ご自身のSPU倍率を設定（例: 10倍なら 10.0）
SPU_RATE = 10.0         
# ポイント計算用の係数 (0.10)
POINT_MULTIPLIER = SPU_RATE / 100

# FBA手数料（小型軽量を考慮して少し平均を下げるか、サイズ分岐を入れるのが理想）
# ここでは「標準」と「小型」の中間程度または、厳し目に見て450円程度に設定
FBA_FEE_FIXED = 450     

def clean_price(value):
    """価格のクリーニング"""
    if pd.isna(value) or value == '':
        return 0
    s = str(value)
    s = s.replace('¥', '').replace(',', '').replace(' ', '').strip()
    try:
        return int(float(s))
    except ValueError:
        return 0

def calculate_metrics(amazon_price, rakuten_price, shipping):
    # === 仕入れ値計算（ポイント考慮） ===
    # 獲得ポイント計算（税抜価格に対して付与されるが、簡易的に税込で計算）
    # ※より厳密にするなら rakuten_price / 1.1 * POINT_MULTIPLIER
    points = int(rakuten_price * POINT_MULTIPLIER)
    
    # 実質仕入れ値 = (商品価格 + 送料) - 獲得ポイント
    cost_cash = rakuten_price + shipping
    cost_net = cost_cash - points
    
    # === Amazon入金額計算 ===
    amz_fee = int(amazon_price * AMAZON_FEE_RATE)
    net_revenue = amazon_price - amz_fee - FBA_FEE_FIXED
    
    # === 利益計算 ===
    profit = net_revenue - cost_net
    
    # 利益率 (ROI)
    roi = (profit / cost_net * 100) if cost_net > 0 else 0
    
    return profit, roi, cost_net, points

def main():
    input_csv = "data/order_list_keepa.csv"
    output_csv = "data/profitable_list.csv"
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    print(f"Loading {input_csv}...")
    try:
        # csvの読み込み（エンコーディングエラーが出る場合は encoding='utf-8' や 'cp932' を指定）
        df = pd.read_csv(input_csv)
    except Exception as e:
        print(f"CSV Load Error: {e}")
        return

    if 'jan' not in df.columns:
        print("Error: CSV must contain 'jan' column.")
        return

    # JANがある行だけ抽出
    df = df.dropna(subset=['jan'])
    
    client = RakutenClient()
    results = []
    
    print(f"Starting Research for {len(df)} items... (SPU: {SPU_RATE}%)")
    
    for index, row in df.iterrows():
        try:
            # JANコードの整形
            jan_raw = row['jan']
            if pd.isna(jan_raw): continue
            jan = str(int(float(jan_raw)))
        except:
            continue
            
        # Amazon価格取得
        # ※ CSVの列名が 'target_price' だが、これが「現在のカート価格」であることを確認してください
        amazon_price = clean_price(row.get('target_price', 0))
        asin = row.get('asin', 'UNKNOWN')
        
        if amazon_price == 0:
            continue

        # 進捗表示
        if index % 10 == 0:
            print(f"Checking {index}/{len(df)}: ASIN {asin} (Amz: {amazon_price}円)")

        # === 楽天リサーチ実行 ===
        # 【修正】max_priceを指定しない（Amazonより高くてもポイント等で利益が出る可能性があるため）
        rakuten_item = client.search_item(jan_code=jan) # max_price引数を削除
        
        if rakuten_item:
            # 利益計算
            profit, roi, real_cost, points = calculate_metrics(
                amazon_price, 
                rakuten_item.price, 
                rakuten_item.shipping
            )
            
            # コンソールに見つかったアイテムの状況を表示（デバッグ用）
            # print(f"   -> Rakuten: {rakuten_item.price}円(送{rakuten_item.shipping}) | 実質: {real_cost}円 | 利益: {profit}円")

            if profit >= MIN_PROFIT and roi >= MIN_ROI:
                print(f"💰 WINNER! {str(row.get('keyword', ''))[:15]}...")
                print(f"   ASIN:{asin} | Amz:{amazon_price} -> Rak:{rakuten_item.price}(送{rakuten_item.shipping})")
                print(f"   Point:{points}pt | Profit:{int(profit)} ({roi:.1f}%)")
                
                results.append({
                    "asin": asin,
                    "jan": jan,
                    "item_name": str(row.get('keyword', ''))[:30], 
                    "amazon_price": amazon_price,
                    "rakuten_price": rakuten_item.price,
                    "rakuten_shipping": rakuten_item.shipping,
                    "rakuten_points": points, # ポイント列を追加
                    "profit": int(profit),
                    "roi": round(roi, 1),
                    "rakuten_url": rakuten_item.url,
                    "amazon_url": row.get('url', f"https://www.amazon.co.jp/dp/{asin}")
                })
        
        # APIレートリミットへの配慮は rakuten_client 側で行っているが、必要ならここにも sleep を入れる
        # time.sleep(0.5)

    # 結果保存
    if results:
        result_df = pd.DataFrame(results)
        result_df.to_csv(output_csv, index=False, encoding='utf-8-sig') # Excelで文字化けしないようsig付き
        print(f"\nSuccessfully saved {len(results)} profitable items to {output_csv}")
    else:
        print("\nNo profitable items found. (Try adjusting MIN_PROFIT or SPU_RATE)")

if __name__ == "__main__":
    main()
