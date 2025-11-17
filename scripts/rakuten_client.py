from __future__ import annotations

import os
from typing import Optional, Tuple, List, Dict, Any

import requests

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID")
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID")

RAKUTEN_ITEM_SEARCH_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"


def _ensure_app_id() -> bool:
    """
    楽天アプリIDが設定されているかチェック。
    未設定なら警告を出して False を返す。
    """
    if not RAKUTEN_APP_ID:
        print("[WARN] RAKUTEN_APP_ID が未設定のため、楽天API検索をスキップします。")
        return False
    return True


def search_rakuten_items_by_jan(jan: str, hits: int = 10) -> List[Dict[str, Any]]:
    """
    JANコードで楽天市場APIを検索し、商品リストを返す。
    見つからない・エラーの場合は空リスト。
    """
    if not jan:
        return []
    if not _ensure_app_id():
        return []

    params = {
        "applicationId": RAKUTEN_APP_ID,
        "format": "json",
        "isbnjan": jan,
        "hits": hits,
        "sort": "+itemPrice",  # 価格昇順
    }

    try:
        resp = requests.get(RAKUTEN_ITEM_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] Rakuten API error for JAN {jan}: {e}")
        return []

    items = data.get("Items") or []
    results: List[Dict[str, Any]] = []

    for entry in items:
        item = entry.get("Item") or {}
        results.append(item)

    return results


def get_lowest_price_and_url_by_jan(jan: str) -> Tuple[Optional[float], Optional[str]]:
    """
    JANコードで検索し、最安値(itemPrice)とその商品のURL(アフィリ付き)を返す。
    見つからなければ (None, None)。
    """
    items = search_rakuten_items_by_jan(jan, hits=10)
    if not items:
        return None, None

    # すでに価格昇順で返っているので最初の要素が最安
    item = items[0]
    price = item.get("itemPrice")
    if price is None:
        return None, None

    try:
        price_float = float(price)
    except Exception:
        price_float = None

    url = build_rakuten_affiliate_url(item)

    return price_float, url


def build_rakuten_affiliate_url(item: Dict[str, Any]) -> Optional[str]:
    """
    楽天API item dict からアフィリエイトURLを生成。
    RAKUTEN_AFFILIATE_ID が未設定なら通常URLを返す。
    """
    base_url = item.get("itemUrl")
    if not base_url:
        return None

    if not RAKUTEN_AFFILIATE_ID:
        return base_url

    # 一番シンプルな scid 付与
    return f"{base_url}?scid={RAKUTEN_AFFILIATE_ID}"
