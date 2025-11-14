# scripts/fba_fee.py

import math

# Amazon JP の FBA料金推定ツールを元にした簡易計算
# ※ 完全な公式値と若干ズレるが、仕入れ判断には十分精度がある

def estimate_fba_fee(weight_kg: float, dimension_cm: tuple, category: str = "default"):
    """
    weight_kg: 重量(kg)
    dimension_cm: (縦, 横, 高さ) in cm
    category: 省略時は default
    
    return: 推定FBA手数料(円)
    """

    length, width, height = dimension_cm
    volume = (length * width * height) / 5000  # 体積重量(kg)

    billable_weight = max(weight_kg, volume)

    # カテゴリー別の基本料金（ざっくり）
    base_fee_map = {
        "default": 440,
        "toys": 420,
        "beauty": 410,
        "electronics": 480,
    }
    base_fee = base_fee_map.get(category, base_fee_map["default"])

    # 重量超過料金（目安）
    extra_fee = 0
    if billable_weight > 0.5:
        extra_fee = math.ceil((billable_weight - 0.5) * 1000) * 4

    # 配送代行手数料
    fba_fee = base_fee + extra_fee

    # 保管料（小物の仮値）
    storage_fee = 10

    return fba_fee + storage_fee
