from __future__ import annotations
import os
import tomllib
import requests
import time
from dataclasses import dataclass
from typing import List

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
    item_code: str

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
        url = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20170628"
        params = {
            "applicationId": self.config.app_id,
            "genreId": genre_id,
            "hits": 10, # テスト用に少なめ
        }
        try:
            time.sleep(1)
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = []
            for item_data in data.get("Items", []):
                obj = item_data.get("Item", {}) if "Item" in item_data else item_data
                items.append(RakutenItem(
                    name=obj.get("itemName", ""),
                    price=obj.get("itemPrice", 0),
                    url=obj.get("itemUrl", ""),
                    shop_name=obj.get("shopName", ""),
                    image_url=obj.get("mediumImageUrls", [{"imageUrl": ""}])[0]["imageUrl"],
                    item_code=obj.get("itemCode", "")
                ))
            return items
        except Exception as e:
            print(f"[Rakuten Error] {e}")
            return []
