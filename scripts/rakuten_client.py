from __future__ import annotations
import os
import tomllib
import requests
import time
from dataclasses import dataclass
from typing import List, Optional

# 設定ファイルのパス
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.toml")

@dataclass
class RakutenConfig:
    app_id: str
    secret: str
    endpoint: str
    shop_url: str

@dataclass
class RakutenItem:
    name: str
    price: int
    url: str
    shop_name: str
    image_url: str
    shop_code: str
    item_code: str
    availability: bool # 購入可能か

def load_rakuten_config() -> RakutenConfig:
    """
    楽天API設定を読み込む
    環境変数 -> config.toml の順
    """
    # 1. 環境変数 (GitHub Actions用)
    env_app_id = os.getenv("RAKUTEN_APP_ID")
    env_secret = os.getenv("RAKUTEN_SECRET")

    if env_app_id:
        # secret は必須でないAPIもありますが、一応読み込む
        return RakutenConfig(
            app_id=env_app_id,
            secret=env_secret or "",
            endpoint="https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220401",
            shop_url=""
        )

    # 2. config.toml (ローカル用)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            raw = tomllib.load(f)
        
        if "rakuten" in raw:
            conf = raw["rakuten"]
            return RakutenConfig(
                app_id=conf.get("app_id", ""),
                secret=conf.get("secret", ""),
                endpoint=conf.get("endpoint", "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220401"),
                shop_url=conf.get("shop_url", "")
            )

    # 見つからない場合でもエラーにせず、空のConfigを返す手もありますが、
    # ここではAPIキー必須としてエラーを出します。
    raise ValueError("Rakuten Config (RAKUTEN_APP_ID) not found in environment or config.toml")


class RakutenClient:
    def __init__(self):
        self.config = load_rakuten_config()
        self.session = requests.Session()

    def search_items(self, keyword: str, min_price: Optional[int] = None, max_price: Optional[int] = None) -> List[RakutenItem]:
        """
        キーワード（JANコードなど）で楽天商品を検索する
        """
        params = {
            "applicationId": self.config.app_id,
            "keyword": keyword,
            "formatVersion": 2,
            "hits": 3, # 上位3件取得（必要に応じて変更）
            "sort": "+itemPrice", # 安い順
        }
        
        if min_price:
            params["minPrice"] = min_price
        if max_price:
            params["maxPrice"] = max_price

        try:
            # リクエスト送信（API制限考慮で少し待機を入れるのがマナーですが、呼び出し元で制御推奨）
            time.sleep(0.5) 
            resp = self.session.get(self.config.endpoint, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            items = []
            
            # Items キーが存在するかチェック
            if "Items" not in data:
                return []

            for item_data in data["Items"]:
                # フォーマットバージョン2の場合の構造に合わせて抽出
                # 階層構造が変わる可能性があるため get を使用
                i = item_data
                
                # 売り切れフラグチェック (availabilityが1なら在庫あり)
                availability = i.get("availability", 0) == 1

                items.append(RakutenItem(
                    name=i.get("itemName", ""),
                    price=i.get("itemPrice", 0),
                    url=i.get("itemUrl", ""),
                    shop_name=i.get("shopName", ""),
                    image_url=i.get("mediumImageUrls", [""])[0] if i.get("mediumImageUrls") else "",
                    shop_code=i.get("shopCode", ""),
                    item_code=i.get("itemCode", ""),
                    availability=availability
                ))
            
            return items

        except requests.exceptions.RequestException as e:
            print(f"[Rakuten API Error] keyword={keyword}, error={e}")
            return []
