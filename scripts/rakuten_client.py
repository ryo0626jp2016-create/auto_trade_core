import os
import time
import random
import requests
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class RakutenItem:
    name: str
    price: int
    url: str
    shop_name: str
    shipping: int  # 送料
    image_url: str

class RakutenClient:
    def __init__(self):
        # 環境変数 RAKUTEN_APP_ID からカンマ区切りでIDを取得
        # GitHub Secrets例: "106xxx,107xxx,108xxx"
        ids_str = os.getenv("RAKUTEN_APP_ID", "")
        self.app_ids = [x.strip() for x in ids_str.split(",") if x.strip()]
        
        if not self.app_ids:
            print("Warning: RAKUTEN_APP_ID is not set. API calls will fail.")

    def _get_random_app_id(self) -> str:
        if not self.app_ids:
            raise ValueError("Rakuten APP ID is missing in Secrets.")
        return random.choice(self.app_ids)

    def search_item(self, jan_code: str = "", keyword: str = "", max_price: int = 0) -> Optional[RakutenItem]:
        """
        JANコードまたはキーワードで最安値を検索する
        """
        url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
        
        params = {
            "applicationId": self._get_random_app_id(),
            "format": "json",
            "sort": "+itemPrice",  # 価格が安い順
            "availability": 1,     # 在庫ありのみ
            "hits": 1,             # 最安の1件だけ取得
            # "NGKeyword": "中古",  # 中古を除外したい場合はコメントアウトを外す
        }

        if jan_code:
            params["keyword"] = jan_code
        elif keyword:
            params["keyword"] = keyword
        else:
            return None

        if max_price > 0:
            # Amazon価格より高いものは検索結果から除外（API節約にはならないがレスポンスには効く）
            params["maxPrice"] = max_price

        try:
            # 連続アクセスによる制限回避のため少し待機
            time.sleep(0.7) 
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                print("Rakuten API Rate Limit Reached. Waiting...")
                time.sleep(2)
                return None
                
            data = response.json()

            if "Items" in data and len(data["Items"]) > 0:
                item = data["Items"][0]["Item"]
                
                # 送料フラグ (0:送料別, 1:送料込)
                postage_flag = item.get("postageFlag", 0)
                # 送料別の場合は一律600円と仮定（正確に取るのは難しいため）
                shipping_cost = 0 if postage_flag == 1 else 600
                
                return RakutenItem(
                    name=item.get("itemName", ""),
                    price=item.get("itemPrice", 0),
                    url=item.get("itemUrl", ""),
                    shop_name=item.get("shopName", ""),
                    shipping=shipping_cost,
                    image_url=item.get("mediumImageUrls", [{}])[0].get("imageUrl", "")
                )
            else:
                return None

        except Exception as e:
            print(f"Rakuten API Error: {e}")
            return None
