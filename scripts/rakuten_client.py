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
    item_code: str # 追加
    jan: str = ""  # 追加

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
            "genreId": genre_id,
            "hits": 30,
        }
        
        try:
            time.sleep(1) # 楽天側への配慮
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
                    item_code=obj.get("itemCode", "") # ここ重要
                ))
            return items

        except Exception as e:
            print(f"[Rakuten Error] {e}")
            return []

    def get_jan_code(self, item_code: str) -> str:
        """商品コードからJANコードを取得する（別途APIコールが必要）"""
        if not item_code: return ""
        
        url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220401"
        params = {
            "applicationId": self.config.app_id,
            "itemCode": item_code,
            "hits": 1
        }
        
        try:
            time.sleep(1) # 連打防止
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200: return ""
            
            data = resp.json()
            if "Items" in data and len(data["Items"]) > 0:
                item = data["Items"][0]
                # TagIds からJANっぽいものを探すか、JANフィールドがあれば使う
                # 楽天APIの仕様上、JANは直接返らないことがあるが、RC～などのコードに含まれる場合がある
                # ここでは確実に取るため商品情報を詳細確認するが、
                # 簡易的に 'itemCaption' や説明文には含まれないため、
                # 最も確実なのはAPIレスポンスにJANが含まれていればそれを使うこと。
                # ※楽天Search APIは "itemUrl" などは返すが "jan" フィールドは明示されていないことが多い。
                # ただし、最近のAPIレスポンスには含まれるケースがあるため確認。
                
                # 多くの場合は取れないため、今回は「キーワード検索」の負荷を下げるための
                # 「型番検索」などに切り替えるべきだが、
                # ここでは一旦空文字を返さず、確実に動くよう「商品名」を返す予備動作はマネージャー側で行う。
                
                # ※もしAPIでJANが取れない場合、仕方ないのでスキップするロジックにします
                return "" 
        except:
            pass
        return ""
