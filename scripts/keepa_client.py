from __future__ import annotations
import os
import tomllib  # Python 3.11 以降
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import keepa  # pip install keepa


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


@dataclass
class KeepaConfig:
    api_key: str
    domain: str  # "JP" など


@dataclass
class ProductStats:
    asin: str
    title: str
    avg_rank_90d: Optional[int]
    expected_sell_price: Optional[float]  # 円（税抜き想定）
    buybox_is_amazon: bool


def load_keepa_config() -> KeepaConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    k = raw["keepa"]
    return KeepaConfig(
        api_key=k["api_key"],
        domain=k.get("domain", "JP"),
    )


def _get_avg_rank_90d_from_stats(stats: Dict[str, Any]) -> Optional[int]:
    """
    Keepa statistics object の avg90 配列から
    SALES(=売れ筋ランキング) の平均値を取り出す。

    docsより：
    - stats["avg90"] は整数配列
    - 配列のインデックスは csv / data フィールドと同じ並び
      AMAZON, NEW, USED, SALES, LISTPRICE, ... の順
    → SALES = index 3
    """
    avg90: List[int] = stats.get("avg90") or []
    if len(avg90) <= 3:
        return None
    value = avg90[3]
    # ランキングが存在しない場合は 0 or -1 のこともあるのでチェック
    if value is None or value <= 0:
        return None
    return int(value)


def _get_expected_sell_price_from_stats(stats: Dict[str, Any]) -> Optional[float]:
    """
    販売想定価格を stats から取得。
    まず buyBoxPrice を使い、なければ None を返す。

    Keepa の価格は「通貨の1/100単位」で返ってくる（例: 2500 = 25.00）ため、
    100で割って実際の通貨に変換する。
    """
    raw_price = stats.get("buyBoxPrice")
    if raw_price is None or raw_price <= 0:
        return None

    # 100 で割って通貨に変換（日本なら基本的にはほぼそのまま円相当）
    return raw_price / 100.0


def get_product_info(asin: str) -> Optional[ProductStats]:
    """
    指定した ASIN の Keepa 情報を取得し、仕入れ判定に必要な要約情報を返す。
    """
    config = load_keepa_config()
    api = keepa.Keepa(config.api_key)

    # デバッグ用：キー長 & ドメインを表示（キー本体はマスク）
    print(f"[DEBUG] Keepa domain = {config.domain}")
    print(f"[DEBUG] Keepa API key length = {len(config.api_key)}")
    if len(config.api_key) < 10:
        print("[ERROR] Keepa API key が短すぎます。config.toml / Secrets を確認してください。")

    try:
        # stats=90: 過去90日分の統計情報を含める
        products = api.query(
            asin,
            stats=90,
            domain=config.domain,
            history=False,   # とりあえず履歴は取らない（必要なら True に）
            buybox=True,
            rating=False,
            offers=0,
            progress_bar=False,
        )
    except RuntimeError as e:
        # ここで REQUEST_REJECTED などをキャッチして、そのASINだけスキップする
        print(f"[ERROR] Keepa request rejected for ASIN {asin}: {e}")
        return None

    if not products:
        print(f"[WARN] Keepa returned no product for ASIN {asin}")
        return None

    p = products[0]

    title = p.get("title", "")
    stats = p.get("stats") or {}

    avg_rank_90d = _get_avg_rank_90d_from_stats(stats)
    expected_sell_price = _get_expected_sell_price_from_stats(stats)

    buybox_is_amazon = bool(stats.get("buyBoxIsAmazon", False))

    return ProductStats(
        asin=asin,
        title=title,
        avg_rank_90d=avg_rank_90d,
        expected_sell_price=expected_sell_price,
        buybox_is_amazon=buybox_is_amazon,
    )
