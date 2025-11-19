from __future__ import annotations
import os
import tomllib
import requests
import time
from dataclasses import dataclass
from typing import List, Optional

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.toml")

@dataclass
class RakutenConfig:
    app_id: str
    secret: str

@dataclass
class RakutenItem:
    name: str
    price: int
    url: str
    shop_name: str
    image_url: str
    jan: str  # JANコード追加

def load_rakuten_config() -> RakutenConfig:
    env_app_id = os.getenv("RAKUTEN_APP_ID")
    env_secret = os.getenv("RAKUTEN_SECRET")
    if env_app_id:
        return RakutenConfig(app_id=env_app_id, secret=env_secret or "")
    
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            raw = tomllib.load(f)
        if "rakuten" in raw:
            return RakutenConfig(
                app_id=raw["rakuten"].get("app_id", ""),
                secret=raw["rakuten"].get("secret", "")
            )
    raise ValueError("Rakuten API Key missing.")

class RakutenClient:
    def __init__(self):
        self.config = load_rakuten_config()
        self.session = requests.Session()

    def get_ranking(self, genre_id: str = "") -> List[RakutenItem]:
        """楽天ランキングAPIから上位商品を取得"""
        url = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20170628"
        params = {
            "applicationId": self.config.app_id,
            "genreId": genre_id, # 空なら総合ランキング
            "hits": 30,          # 上位30件
        }
        
        try:
            time.sleep(0.5)
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            items = []
            for i, item_data in enumerate(data.get("Items", []), 1):
                # ランキングAPIの構造に対応
                obj = item_data.get("Item", {}) if "Item" in item_data else item_data
                
                # JANコード取得を試みる
                # ※ランキングAPIには直接JANが含まれないことが多いため、詳細検索が必要な場合がありますが
                # 今回は簡易的に取得できる情報で構成します。
                # 実際の運用では、ここで取得したitemCodeを使って再検索するとJANが取れます。
                
                items.append(RakutenItem(
                    name=obj.get("itemName", ""),
                    price=obj.get("itemPrice", 0),
                    url=obj.get("itemUrl", ""),
                    shop_name=obj.get("shopName", ""),
                    image_url=obj.get("mediumImageUrls", [{"imageUrl": ""}])[0]["imageUrl"],
                    jan="" # ランキングAPI単体では取れないため、メイン処理で補完またはキーワード検索に使用
                ))
            return items

        except Exception as e:
            print(f"[Rakuten Error] {e}")
            return []
