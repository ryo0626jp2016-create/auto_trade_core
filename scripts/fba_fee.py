# scripts/fba_fee.py

import math
from typing import Tuple


def normalize_category(raw: str | None) -> str:
    """
    Keepa の productGroup など生のカテゴリ文字列から、
    FBA料金計算で使う「ざっくりカテゴリキー」を決める。

    例:
      - "Toys & Games" → "toys"
      - "Beauty" → "beauty"
      - "Electronics" → "electronics"
      - それ以外 → "default"
    """
    if not raw:
        return "default"

    s = raw.lower()

    if "toy" in s or "game" in s:
        return "toys"
    if "beauty" in s or "cosmetic" in s:
        return "beauty"
    if "electronic" in s or "computer" in s or "video game" in s:
        return "electronics"

    return "default"


def estimate_fba_fee(weight_kg: float, dimensions_cm: Tuple[float, float, float], category_key: str = "default") -> float:
    """
    FBA配送代行手数料 + 保管料の簡易見積もり。

    - weight_kg           : 商品重量(kg)（KeepaのpackageWeightから換算）
    - dimensions_cm       : (長辺, 中辺, 短辺) in cm（packageLength/Width/Heightから換算）
    - category_key        : "default" / "toys" / "beauty" / "electronics" など

    ※ 正確な公式料金とは多少ズレるが、仕入れ判定には十分な精度を目指した近似。
    """
    length, width, height = dimensions_cm

    # 体積重量(kg) = (縦cm × 横cm × 高さcm) / 5000 * 1000 / 1000 → cm3 / 5000
    volume_weight = (length * width * height) / 5000.0

    # 請求重量は 実重量 or 体積重量 の大きい方
    billable_weight = max(weight_kg, volume_weight)

    # カテゴリ別の基本料金（ざっくり）
    base_fee_map = {
        "default": 440.0,
        "toys": 420.0,
        "beauty": 410.0,
        "electronics": 480.0,
    }
    base_fee = base_fee_map.get(category_key, base_fee_map["default"])

    # 重量超過料金（0.5kgを超えた分に対して、1gごとにいくら、みたいなイメージ）
    extra_fee = 0.0
    if billable_weight > 0.5:
        # 0.5kgを超える分をgで切り上げ → 1gあたり 4円/100g くらいのイメージ
        extra_weight_g = math.ceil((billable_weight - 0.5) * 1000)
        extra_fee = (extra_weight_g / 100.0) * 4.0

    fba_shipping_fee = base_fee + extra_fee

    # 在庫保管料（小さめ商品想定でざっくり月10円分を乗せておく）
    storage_fee = 10.0

    return fba_shipping_fee + storage_fee
