from __future__ import annotations

import os
import tomllib  # Python 3.11 以降で標準
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple

import keepa  # pip install keepa で入れてある前提


# config.toml のパス
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


# -------------------------------------------------
# 設定 & データ構造
# -------------------------------------------------
@dataclass
class KeepaConfig:
    api_key: str
    domain: str  # "JP" など


@dataclass
class ProductStats:
    """
    Keepa product から、せどり判定で使いたい情報だけをまとめた構造体。
    """
    asin: str
    title: str
    avg_rank_90d: Optional[int]
    expected_sell_price: Optional[float]  # 円（BuyBox 基準）

    # Amazon 本体関連
    buybox_is_amazon: bool
    amazon_presence_ratio: Optional[float]   # 過去履歴で Amazon 在庫あり割合（0.0〜1.0）
    amazon_buybox_count: Optional[int]       # Amazon が BuyBox を取っていた回数
    amazon_current: bool                     # 今の BuyBox が Amazon かどうか

    # FBA 手数料などの計算に使えそうな情報
    weight_kg: Optional[float]               # packageWeight → kg 換算
    dimensions_cm: Optional[Tuple[float, float, float]]  # package(L, W, H) → cm 換算
    category: Optional[str]                  # productGroup 等


# -------------------------------------------------
# 設定読み込み
# -------------------------------------------------
def load_keepa_config() -> KeepaConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    k = raw["keepa"]
    return KeepaConfig(
        api_key=k["api_key"],
        domain=k.get("domain", "JP"),
    )


def _get_domain_id(domain_str: str) -> int:
    """
    keepa のドメイン ID を返す（JP = 5）。
    ※ api.query に domain を渡すときに使う。
    """
    domain_str = (domain_str or "").upper()
    mapping = {
        "US": 1,
        "UK": 2,
        "DE": 3,
        "FR": 4,
        "JP": 5,
        "CA": 6,
        "CN": 7,
        "IT": 8,
        "ES": 9,
        "IN": 10,
        "MX": 11,
        "BR": 12,
    }
    return mapping.get(domain_str, 5)  # デフォルト JP


# -------------------------------------------------
# stats から欲しい値を抜き出すユーティリティ
# -------------------------------------------------
def _get_avg_rank_90d_from_stats(stats: Dict[str, Any]) -> Optional[int]:
    """
    statistics.avg90 配列の SALES(=売れ筋ランキング) を取得。
    docs 上では avg90[3] が SALES。
    """
    if not stats:
        return None
    avg90: List[int] = stats.get("avg90") or []
    if len(avg90) <= 3:
        return None

    value = avg90[3]
    if value is None or value <= 0:
        return None
    return int(value)


def _get_expected_sell_price_from_stats(stats: Dict[str, Any]) -> Optional[float]:
    """
    販売想定価格を stats から取得。
    まず buyBoxPrice を使う。
    keepa の価格は「通貨の 1/100 単位」で返るので /100 する。
    """
    if not stats:
        return None
    raw_price = stats.get("buyBoxPrice")
    if raw_price is None or raw_price <= 0:
        return None
    return raw_price / 100.0


def analyze_amazon_presence(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Amazon 本体参入状況をざっくり解析する。
    戻り値のキー:
      - amazon_presence_ratio
      - amazon_buybox_count
      - amazon_current
    """
    stats: Dict[str, Any] = product.get("stats") or {}
    data: Dict[str, Any] = product.get("data") or {}

    amazon_presence_ratio: Optional[float] = None
    amazon_buybox_count: Optional[int] = None

    # 現在の BuyBox が Amazon かどうか
    amazon_current = bool(stats.get("buyBoxIsAmazon", False))

    # AMAZON 在庫履歴（AMAZON フィールド）
    amazon_stock_history: List[int] = data.get("AMAZON") or []
    if amazon_stock_history:
        total = len(amazon_stock_history)
        count = sum(1 for v in amazon_stock_history if v is not None and v > 0)
        if total > 0:
            amazon_presence_ratio = count / total

    # Amazon が BuyBox を取っていた履歴
    buybox_is_amazon_history: List[int] = data.get("BUY_BOX_IS_AMAZON_SHIPPING") or []
    if buybox_is_amazon_history:
        amazon_buybox_count = sum(1 for v in buybox_is_amazon_history if v == 1)

    return {
        "amazon_presence_ratio": amazon_presence_ratio,
        "amazon_buybox_count": amazon_buybox_count,
        "amazon_current": amazon_current,
    }


def _extract_weight_and_dimensions(
    product: Dict[str, Any],
) -> Tuple[Optional[float], Optional[Tuple[float, float, float]]]:
    """
    packageWeight (g), packageLength/Width/Height (mm) を
    kg / cm に変換する。
    """
    package_weight = product.get("packageWeight")
    if isinstance(package_weight, (int, float)) and package_weight > 0:
        weight_kg: Optional[float] = package_weight / 1000.0
    else:
        weight_kg = None

    length_mm = product.get("packageLength")
    width_mm = product.get("packageWidth")
    height_mm = product.get("packageHeight")

    if all(isinstance(v, (int, float)) and v > 0 for v in (length_mm, width_mm, height_mm)):
        dimensions_cm: Optional[Tuple[float, float, float]] = (
            length_mm / 10.0,
            width_mm / 10.0,
            height_mm / 10.0,
        )
    else:
        dimensions_cm = None

    return weight_kg, dimensions_cm


def _extract_category(product: Dict[str, Any]) -> Optional[str]:
    """
    productGroup などからざっくりカテゴリを取り出す。
    """
    pg = product.get("productGroup")
    if isinstance(pg, str) and pg:
        return pg
    return None


# -------------------------------------------------
# keepa API インスタンスのシングルトン
# -------------------------------------------------
_keepa_api: Optional[keepa.Keepa] = None


def _get_keepa_api(api_key: str) -> keepa.Keepa:
    global _keepa_api
    if _keepa_api is None:
        _keepa_api = keepa.Keepa(api_key)
    return _keepa_api


# -------------------------------------------------
# 公開関数: ASIN 1件分の情報を取得
# -------------------------------------------------
def get_product_info(asin: str) -> Optional[ProductStats]:
    """
    指定 ASIN の情報を keepa ライブラリ経由で取得して
    ProductStats にまとめて返す。
    エラーやデータなしの場合は None。
    """
    config = load_keepa_config()

    print(f"[DEBUG] Keepa domain (string) = {config.domain}")
    print(f"[DEBUG] Keepa API key length = {len(config.api_key)}")
    if len(config.api_key) < 10:
        print("[ERROR] Keepa API key が短すぎます。config.toml / GitHub Secrets を確認してください。")

    domain_id = _get_domain_id(config.domain)
    print(f"[DEBUG] Keepa domain (id) = {domain_id}")

    api = _get_keepa_api(config.api_key)

    try:
        products = api.query(
            asin,
            stats=True,
            history=True,
            buybox=True,
            domain=domain_id,
        )
    except Exception as e:
        print(f"[ERROR] keepa.Keepa.query error for ASIN {asin}: {e}")
        return None

    if not products:
        print(f"[WARN] Keepa returned no product for ASIN {asin}")
        return None

    p: Dict[str, Any] = products[0]

    title = p.get("title", "") or ""
    stats = p.get("stats") or {}

    avg_rank_90d = _get_avg_rank_90d_from_stats(stats)
    expected_sell_price = _get_expected_sell_price_from_stats(stats)

    amazon_info = analyze_amazon_presence(p)
    weight_kg, dimensions_cm = _extract_weight_and_dimensions(p)
    category = _extract_category(p)

    return ProductStats(
        asin=asin,
        title=title,
        avg_rank_90d=avg_rank_90d,
        expected_sell_price=expected_sell_price,
        buybox_is_amazon=bool(stats.get("buyBoxIsAmazon", False)),
        amazon_presence_ratio=amazon_info["amazon_presence_ratio"],
        amazon_buybox_count=amazon_info["amazon_buybox_count"],
        amazon_current=amazon_info["amazon_current"],
        weight_kg=weight_kg,
        dimensions_cm=dimensions_cm,
        category=category,
    )
