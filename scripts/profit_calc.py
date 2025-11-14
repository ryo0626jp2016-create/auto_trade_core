# scripts/profit_calc.py

from typing import Optional, Tuple

from .fba_fee import estimate_fba_fee, normalize_category


def _fallback_weight_and_dimensions(
    weight_kg: Optional[float],
    dimensions_cm: Optional[Tuple[float, float, float]],
) -> Tuple[float, Tuple[float, float, float]]:
    """
    Keepa から重さ・サイズが取れなかった場合の安全なデフォルト値。

    - 小さめの一般的な小物（例: 20cm x 15cm x 5cm / 0.3kg）として扱う。
    - 実際のFBA料金より多少多めに見積もることで、利益過大評価を避ける。
    """
    if weight_kg is None or weight_kg <= 0:
        weight_kg = 0.3  # 300g想定

    if (
        dimensions_cm is None
        or any(d <= 0 for d in dimensions_cm)
    ):
        dimensions_cm = (20.0, 15.0, 5.0)  # 小型商品のざっくりサイズ

    return weight_kg, dimensions_cm


def calc_profit_with_fba(
    sell_price: float,
    buy_price: float,
    weight_kg: Optional[float],
    dimensions_cm: Optional[Tuple[float, float, float]],
    raw_category: Optional[str],
) -> dict:
    """
    FBA手数料・Amazon成約料込みの利益計算。

    戻り値:
    {
        "profit": int(円),
        "roi": float(0.00),
        "fba_fee": int(円),
        "amazon_fee": int(円)
    }
    """
    # 重量・サイズの穴埋め
    weight_kg, dimensions_cm = _fallback_weight_and_dimensions(weight_kg, dimensions_cm)

    # カテゴリ文字列を内部カテゴリキーに変換
    category_key = normalize_category(raw_category)

    # FBA料金の見積もり
    fba_fee = estimate_fba_fee(weight_kg, dimensions_cm, category_key)

    # Amazon 販売手数料（成約料など）
    # ※ カテゴリによって8〜15%くらいだが、とりあえず10%で保守的に見積もる
    amazon_fee = sell_price * 0.10

    total_cost = buy_price + fba_fee + amazon_fee

    profit = sell_price - total_cost
    roi = profit / buy_price if buy_price > 0 else 0.0

    return {
        "profit": int(round(profit)),
        "roi": float(round(roi, 2)),
        "fba_fee": int(round(fba_fee)),
        "amazon_fee": int(round(amazon_fee)),
    }
