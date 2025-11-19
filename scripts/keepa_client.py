from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from typing import Optional, List
import keepa

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.toml")

@dataclass
class ProductStats:
    asin: str
    title: str
    avg_rank_90d: int | None
    expected_sell_price: int | None
    weight_kg: float
    dimensions_cm: List[int] | None
    amazon_current: int | None

def load_config() -> str:
    env_key = os.getenv("KEEPA_API_KEY")
    if env_key: return env_key
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            try:
                return tomllib.load(f)["keepa"]["api_key"]
            except:
                pass
    raise ValueError("KEEPA_API_KEY missing.")

def _parse_product(p) -> Optional[ProductStats]:
    if not p.get("title"): return None
    stats = p.get("stats", {})
    avg90 = stats.get("avg90", {})
    current = stats.get("current", {})
    
    price = avg90.get(18, avg90.get(1, None))
    if price is None or price < 0:
        price = current.get(18, current.get(1, None))
    if price == -1: price = None
    
    amz_price = current.get(0, None)
    if amz_price is not None and amz_price <= 0:
        amz_price = None

    w = p.get("packageWeight", 0) / 1000.0
    dims = [p.get("packageLength", 0)/10.0, p.get("packageWidth", 0)/10.0, p.get("packageHeight", 0)/10.0]

    return ProductStats(
        asin=p.get("asin"),
        title=p.get("title"),
        avg_rank_90d=avg90.get(3, None),
        expected_sell_price=price,
        weight_kg=w,
        dimensions_cm=dims,
        amazon_current=amz_price
    )

def get_product_info(asin: str) -> Optional[ProductStats]:
    api = keepa.Keepa(load_config())
    try:
        products = api.query(items=[asin], domain=5)
        return _parse_product(products[0]) if products else None
    except:
        return None

def find_product_by_keyword(keyword: str) -> Optional[ProductStats]:
    # 高コスト: 20トークン消費
    api = keepa.Keepa(load_config())
    try:
        result = api.product_finder({'title': keyword, 'perPage': 1, 'page': 0}, domain='JP')
        if result: return get_product_info(result[0])
        return None
    except:
        return None

def find_product_by_jan(code: str) -> Optional[ProductStats]:
    """JANコードで検索 (低コスト: 1トークン)"""
    if not code: return None
    api = keepa.Keepa(load_config())
    try:
        # product_code_is_asin=False でJAN検索
        products = api.query(items=[code], domain=5, product_code_is_asin=False)
        if products and products[0].get("title"):
            return _parse_product(products[0])
        return None
    except:
        return None
