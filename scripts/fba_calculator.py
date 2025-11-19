# scripts/fba_calculator.py
from __future__ import annotations
from typing import Optional, Tuple
from .keepa_client import ProductStats # ProductStatsを使用するためにインポート

# Amazon FBA 手数料の定義 (2024年以降の日本FBA料金に基づいた簡略化モデル)

# 1. 販売手数料 (Referral Fee) はカテゴリー依存だが、今回は一般的な15%を基準とする
DEFAULT_REFERRAL_FEE_RATE = 0.15 # 15%

# 2. 配送代行手数料 (Fulfillment Fee) の基本料金（例: 2024年標準サイズ）
# 実際は時期や重量で細かく変動しますが、ロジックを示すために主要なサイズで定義
# (サイズ, 重量上限kg, 基本手数料) のタプルリスト
FBA_FEE_TIERS = [
    # 小型 (L+W+H <= 35cm, 最長辺 <= 25cm, 250g以下)
    (35, 0.25, 330),  # 250g
    # 標準サイズ (L+W+H <= 45cm, 最長辺 <= 35cm, 1kg以下)
    (45, 1.0, 480),   # 1kg
    # 標準サイズ (L+W+H <= 55cm, 最長辺 <= 45cm, 3kg以下)
    (55, 3.0, 580),   # 3kg
    # 標準サイズ (L+W+H <= 65cm, 最長辺 <= 55cm, 5kg以下)
    (65, 5.0, 680),   # 5kg
    # これを超えると大型サイズ（計算が複雑になるため、ここでは省略）
]


def calculate_fba_fees(
    sell_price: float,
    product_stats: ProductStats,
    referral_rate: float = DEFAULT_REFERRAL_FEE_RATE,
) -> float:
    """
    Amazon FBA の総手数料（販売手数料 + 配送代行手数料）を算出する。

    sell_price: Amazonでの販売価格（Buy Boxなど）
    product_stats: Keepaから取得した商品の統計情報（重量、サイズを含む）
    """
    
    # 1. 販売手数料 (Referral Fee)
    # カテゴリーによって変動しますが、ここでは簡易的に15%を適用
    referral_fee = sell_price * referral_rate

    # 2. 配送代行手数料 (Fulfillment Fee)
    
    # 重量と寸法を抽出
    weight_kg = product_stats.weight_kg or 0.5  # データがなければ仮の重さ
    dimensions_cm = product_stats.dimensions_cm
    
    if not dimensions_cm or weight_kg == 0:
        # サイズデータがない場合、計算不能なので標準的な手数料を仮定
        fulfillment_fee = 500  
        # print("[WARN] Size data missing, using default fulfillment fee.")
    else:
        # 寸法（L, W, H）の合計
        length_plus_girth = sum(dimensions_cm)
        # 最長辺
        max_dimension = max(dimensions_cm)
        
        fulfillment_fee = 0
        
        # FBA料金ティアを順にチェック
        for max_sum_dim, max_weight_kg, base_fee in FBA_FEE_TIERS:
            if length_plus_girth <= max_sum_dim and weight_kg <= max_weight_kg:
                fulfillment_fee = base_fee
                break
        
        # どのティアにも当てはまらない場合（大型など）は、高めの料金を仮定
        if fulfillment_fee == 0:
            fulfillment_fee = 1200 # 大型商品の最低ラインを仮定

    # 3. 合計手数料
    total_fees = referral_fee + fulfillment_fee
    
    # FBA料金は最低手数料が設定されている場合がある（ここでは省略）
    return total_fees
