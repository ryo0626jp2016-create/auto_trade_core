from __future__ import annotations
from typing import Optional, Tuple
# 循環参照を防ぐため、型ヒントのみ文字列で扱うか、データクラスを別にする手もありますが、
# ここではシンプルに計算ロジックのみを提供します。

# FBA手数料定義 (2024-2025想定 / 標準サイズ基準)
# (長辺+短辺+高さcm, 重量kg, 手数料円)
FBA_TIERS = [
    (35, 0.25, 330),  # 小型
    (45, 1.00, 480),  # 標準1
    (55, 3.00, 580),  # 標準2
    (65, 5.00, 680),  # 標準3
]

def calculate_fba_fees(sell_price: int, weight_kg: float, dimensions_cm: list[int] | None) -> int:
    """
    販売価格、重量、サイズからFBA手数料（販売手数料＋配送代行手数料）を計算
    """
    if sell_price <= 0:
        return 0

    # 1. 販売手数料 (一律10%〜15%ですが、安全を見て15%とします)
    # カテゴリ判定を入れるとさらに精密になります
    referral_fee = int(sell_price * 0.15)

    # 2. 配送代行手数料
    fulfillment_fee = 550 # データがない場合のデフォルト(標準サイズ相当)

    if dimensions_cm and weight_kg > 0:
        total_cm = sum(dimensions_cm)
        
        found_tier = False
        for max_cm, max_kg, fee in FBA_TIERS:
            if total_cm <= max_cm and weight_kg <= max_kg:
                fulfillment_fee = fee
                found_tier = True
                break
        
        if not found_tier:
            # 大型判定 (簡易)
            fulfillment_fee = 1000

    return referral_fee + fulfillment_fee
