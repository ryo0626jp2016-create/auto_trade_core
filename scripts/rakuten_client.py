# scripts/rakuten_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests

RAKUTEN_API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"


@dataclass
class RakutenItem:
    """
    楽天市場APIから取得した商品1件分の簡易情報
    """
    item_name: str
    item_price: float
    item_url: str
    shop_name: Optional[str] = None


class RakutenClient:
    """
    楽天市場 商品検索API 用の簡易クライアント。
    """
    def __init__(self, application_id: str):
        self.application_id = (application_id or "").strip()

    @classmethod
    def from_env(cls) -> "RakutenClient":
        """
        環境変数から applicationId を読む。
        未設定ならキーなしクライアント（常に検索スキップ）として返す。
        """
        app_id = (
            os.getenv("RAKUTEN_APPLICATION_ID")
            or os.getenv("RAKUTEN_APP_ID")
            or os.getenv("RAKUTEN_API_KEY")
        )

        if not app_id:
            print("[WARN] 楽天APIキー (RAKUTEN_APPLICATION_ID) が設定されていません。楽天検索はスキップされます。")

        return cls(app_id or "")

    def search_by_keyword(self, keyword: str) -> Optional[RakutenItem]:
        """
        キーワードで1件だけ商品を検索し、最安値っぽいものを返す。
        APIキーが無い場合は None を返してスキップ。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return None

        if not self.application_id:
            # APIキーなし → 何もせずスキップ
            return None

        params = {
            "applicationId": self.application_id,
            "keyword": keyword,
            "hits": 1,              # 1件だけ
            "sort": "+itemPrice",   # 価格の安い順
            "format": "json",
        }

        try:
            resp = requests.get(RAKUTEN_API_URL, params=params, timeout=10)
        except Exception as e:
            print(f"[WARN] Rakuten API HTTP error: {e}")
            return None

        if resp.status_code != 200:
            print(f"[WARN] Rakuten API status {resp.status_code}: {resp.text[:200]}")
            return None

        try:
            data = resp.json()
        except Exception as e:
            print(f"[WARN] Rakuten API JSON decode error: {e}")
            return None

        items = data.get("Items") or []
        if not items:
            return None

        first = items[0].get("Item") or {}
        price = first.get("itemPrice")
        name = first.get("itemName")
        url = first.get("itemUrl")

        if price is None or url is None:
            return None

        return RakutenItem(
            item_name=name or "",
            item_price=float(price),
            item_url=url,
            shop_name=first.get("shopName"),
        )
