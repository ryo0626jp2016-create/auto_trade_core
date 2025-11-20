from __future__ import annotations

# FBA手数料定義 (簡易版)
FBA_TIERS = [
    (35, 0.25, 330),
    (45, 1.00, 480),
    (55, 3.00, 580),
    (65, 5.00, 680),
]

def calculate_fba_fees(sell_price: int, weight_kg: float, dimensions_cm: list[int] | None) -> int:
    if sell_price <= 0: return 0
    referral_fee = int(sell_price * 0.15) # 15%
    fulfillment_fee = 550
    if dimensions_cm and weight_kg > 0:
        total_cm = sum(dimensions_cm)
        found_tier = False
        for max_cm, max_kg, fee in FBA_TIERS:
            if total_cm <= max_cm and weight_kg <= max_kg:
                fulfillment_fee = fee
                found_tier = True
                break
        if not found_tier:
            fulfillment_fee = 1000
    return referral_fee + fulfillment_fee
