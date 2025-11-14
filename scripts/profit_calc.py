# scripts/profit_calc.py
# FBA 推定ロジック（簡易版＋安全寄り）

from dataclasses import dataclass

@dataclass
class ProductInfo:
    weight_kg: float | None
    dimensions_cm: tuple[float, float, float] | None
    expected_sell_price: float

# -----------------------------------------
# Amazon 販売手数料（15% 固定でOK）
# -----------------------------------------
def estimate_amazon_fee(sell_price: float) -> float:
    return round(sell_price * 0.15, 3)

# -----------------------------------------
# FBA 配送代行手数料（Amazon公式に近い簡易版）
# -----------------------------------------
def estimate_fba_fee(weight_kg: float | None, dimensions_cm: tuple[float, float, float] | None) -> float:
    """
    商品の重量・サイズが不明の場合は安全側に倒した推定を返す。
    """
    # サイズが分かる場合、体積から簡易判定
    if dimensions_cm:
        l, w, h = dimensions_cm
        volume = l * w * h  # 立方cm
        
        # 小型・標準・大型のざっくりライン
        if volume < 1000:
            return 260  # 小型：260円付近
        elif volume < 12000:
            return 350  # 標準：350円付近
        else:
            return 550  # 大型：550円付近

    # 重量が分かる場合
    if weight_kg:
        if weight_kg < 0.2:
            return 260
        elif weight_kg < 1:
            return 350
        else:
            return 550

    # どちらも不明 → 安全寄りで高めに見積もる
    return 350
