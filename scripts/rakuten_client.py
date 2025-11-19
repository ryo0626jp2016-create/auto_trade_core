from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass

# 設定ファイルのパス
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.toml")

@dataclass
class RakutenConfig:
    app_id: str
    secret: str
    endpoint: str
    shop_url: str

def load_rakuten_config() -> RakutenConfig:
    """
    楽天API設定を読み込む
    環境変数 -> config.toml の順
    """
    # 1. 環境変数
    env_app_id = os.getenv("RAKUTEN_APP_ID")
    env_secret = os.getenv("RAKUTEN_SECRET")

    if env_app_id and env_secret:
        return RakutenConfig(
            app_id=env_app_id,
            secret=env_secret,
            endpoint="https://api.rms.rakuten.co.jp/es/1.0/service",
            shop_url=""
        )

    # 2. config.toml
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            raw = tomllib.load(f)
        
        if "rakuten" in raw:
            conf = raw["rakuten"]
            return RakutenConfig(
                app_id=conf.get("app_id", ""),
                secret=conf.get("secret", ""),
                endpoint=conf.get("endpoint", "https://api.rms.rakuten.co.jp/es/1.0/service"),
                shop_url=conf.get("shop_url", "")
            )

    raise ValueError("Rakuten Config not found in environment or config.toml")
