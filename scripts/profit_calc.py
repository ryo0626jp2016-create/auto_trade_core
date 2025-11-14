# scripts/profit_calc.py

from scripts.fba_fee import estimate_fba_fee

def calc_profit(sell_price: float, buy_price: float, weight_kg: float, size_cm: tuple, category="default"):
    """
    完全版の利益計算
    """
    fba_fee = estimate_fba_fee(weight_kg, size_cm, category)

    amazon_fee = sell_price * 0.08  # 成約料（8%想定）
    total_cost = buy_price + fba_fee + amazon_fee

    profit = sell_price - total_cost
    roi = profit / buy_price if buy_price > 0 else 0

    return {
        "profit": round(profit),
        "roi": round(roi, 2),
        "fba_fee": round(fba_fee),
        "amazon_fee": round(amazon_fee),
    }
