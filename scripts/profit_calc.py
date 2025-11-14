from __future__ import annotations

"""
Amazon 販売手数料をざっくり計算するモジュール（デバッグ用）
"""

def estimate_amazon_fee(sell_price: float) -> float:
    """
    Amazon手数料の概算を返す関数。

    今回はデバッグ用として、カテゴリなどは考慮せず
    「売価の 10% を手数料」として計算する。
    - sell_price: 販売予定価格（円）

    戻り値:
        手数料（円）
    """
    if sell_price is None or sell_price <= 0:
        return 0.0

    fee_rate = 0.10  # 10%
    fee = sell_price * fee_rate
    return float(fee)

