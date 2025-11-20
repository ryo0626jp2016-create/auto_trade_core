import os
import time
import random
import requests
from dataclasses import dataclass
from typing import Optional

@dataclass
class RakutenItem:
    name: str
    price: int
    url: str
    shop_name: str
    shipping: int  # 送料

class RakutenClient:
    def __init__(self):
        # 環境変数 RAKUTEN_APP_ID がカンマ区切りであれば複数読み込む
        # 例: "ID1,ID2,ID3"
        ids_str = os.getenv("RAKUTEN_APP_ID", "")
        self.app_ids = [x.strip() for x in ids_str.split(",") if x.strip()]
        
        if not self.app_ids:
            # IDがない場合はエラーを出さず、空で初期化（実行時にチェック）
            print("Warning: RAKUTEN_APP_ID is not set.")
            self.app_ids = []

    def _get_random_app_id(self) -> str:
        if not self.app_ids:
            raise ValueError("No Rakuten App ID found.")
        return random.choice(self.app_ids)

    def search_item(self, jan_code: str = "", keyword: str = "", min_price: int = 0, max_price: int = 0) -> Optional[RakutenItem]:
        """
        JANコードまたはキーワードで最安値を検索する
        """
        url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
        
        # 検索パラメータ
        params = {
            "applicationId": self._get_random_app_id(),
            "format": "json",
            "sort": "+itemPrice",  # 価格が安い順
            "availability": 1,     # 販売可能なもののみ
            "hits": 1,             # 最安の1件だけでOK
        }

        if jan_code:
            params["keyword"] = jan_code
        elif keyword:
            params["keyword"] = keyword
        else:
            return None

        if min_price > 0:
            params["minPrice"] = min_price
        if max_price > 0:
            params["maxPrice"] = max_price

        try:
            # API制限考慮（少し待機）
            time.sleep(0.5)
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "Items" in data and len(data["Items"]) > 0:
                item = data["Items"][0]["Item"]
                
                # 送料フラグ (0:送料別, 1:送料込)
                postage_flag = item.get("postageFlag", 0)
                # 送料が不明な場合は一旦500円と仮定（安全策）
                shipping_cost = 0 if postage_flag == 1 else 500
                
                return RakutenItem(
                    name=item.get("itemName", ""),
                    price=item.get("itemPrice", 0),
                    url=item.get("itemUrl", ""),
                    shop_name=item.get("shopName", ""),
                    shipping=shipping_cost
                )
            else:
                return None

        except Exception as e:
            print(f"Rakuten API Error: {e}")
            return None
