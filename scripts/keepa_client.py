from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from typing import Optional
import keepa # 要: pip install keepa

# 設定ファイルのパス
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.toml")

@dataclass
class ProductStats:
    asin: str
    title: str
    avg_rank_90d: Optional[int]
    expected_sell_price: Optional[int]
    amazon_presence_ratio: Optional[float]
    amazon_buybox_count: Optional[int]
    amazon_current: Optional[int]
    buybox_is_amazon: bool
    weight_kg: Optional[float]
    dimensions_cm: Optional[str]
    category: str

def load_config() -> str:
    """
    APIキーを読み込む
    1. 環境変数 (GitHub Actions用)
    2. config.toml (ローカル開発用)
    の順で検索する
    """
    # 1. 環境変数をチェック
    env_key = os.getenv("KEEPA_API_KEY")
    if env_key:
        return env_key

    # 2. config.toml をチェック
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "rb") as f:
                config = tomllib.load(f)
            return config["keepa"]["api_key"]
        except (FileNotFoundError, KeyError):
            pass

    raise ValueError("KEEPA_API_KEY is not set in environment variables or config.toml")

def get_product_info(asin: str) -> Optional[ProductStats]:
    """
    Keepa APIから商品情報を取得して整理して返す
    """
    api_key = load_config()
    api = keepa.Keepa(api_key)

    try:
        # domain=5 は Amazon.co.jp
        products = api.query(items=[asin], domain=5)
        if not products:
            return None
        
        p = products[0]
        
        # データがない場合は None を返す
        if p.get('title') is None:
            return None

        # 各種データの抽出
        title = p.get('title', '')
        
        # カテゴリ
        category = ""
        if 'categories' in p and p['categories']:
            # メインカテゴリIDなどを取得（簡易実装）
            category = str(p['categories'][0])

        # ランキング (Sales Rank)
        # stats['current'][3] などを参照する方法もあるが、csvプロパティを使うのが一般的
        stats = p.get('stats', {})
        current_stats = stats.get('current', {})
        avg90 = stats.get('avg90', {})
        
        # 90日平均ランキング (index 3 = Sales Rank)
        avg_rank_90d = avg90[3] if 3 in avg90 and avg90[3] > 0 else None
        
        # 想定売価 (BuyBox = index 18, New = index 1)
        # 90日平均のBuyBox価格を参考にする
        expected_sell_price = avg90[18] if 18 in avg90 and avg90[18] > 0 else None
        if expected_sell_price is None:
             # BuyBoxがない場合は新品最安値
            expected_sell_price = avg90[1] if 1 in avg90 and avg90[1] > 0 else None

        # Amazon本体の価格 (index 0)
        amazon_current = current_stats[0] if 0 in current_stats and current_stats[0] > 0 else None

        # Amazonがカートを取っているか判定 (BuyBoxのSellerId等で判定できるが、簡易的に「Amazon価格が存在し、かつ最安」などで判定も可能)
        # ここでは厳密な判定より、stats buyBoxOwnerId などを使うのが正確ですが、
        # 簡易的に「Amazon在庫がある(=index 0がある)」かつ「Amazon価格がBuyBoxに近い」場合を警戒とします
        buybox_is_amazon = False
        if amazon_current and expected_sell_price:
            # Amazon価格がカート価格以下ならAmazonがカートとみなす（簡易ロジック）
            if amazon_current <= expected_sell_price:
                buybox_is_amazon = True

        # 90日間のAmazon在庫率 (index 0) の有無チェックなどは keepa ライブラリの仕様に合わせて調整が必要
        # ここでは仮置き
        amazon_presence_ratio = 0.0 

        return ProductStats(
            asin=asin,
            title=title,
            avg_rank_90d=avg_rank_90d,
            expected_sell_price=expected_sell_price,
            amazon_presence_ratio=amazon_presence_ratio,
            amazon_buybox_count=0, # 必要なら詳細実装
            amazon_current=amazon_current,
            buybox_is_amazon=buybox_is_amazon,
            weight_kg=p.get('packageWeight', 0) / 1000.0 if p.get('packageWeight') else 0.0,
            dimensions_cm="",
            category=category
        )

    except Exception as e:
        print(f"Error fetching {asin}: {e}")
        return None
