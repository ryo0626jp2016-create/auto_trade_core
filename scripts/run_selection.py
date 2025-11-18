# scripts/run_selection.py
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd


# リポジトリのルートを基準にパスを決める
# （python -m scripts.run_selection を auto_trade_core のルートで実行する想定）
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_PATH = os.path.join(DATA_DIR, "input_candidates.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "output_selected.csv")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


@dataclass
class SelectionConfig:
    """
    以前のログと互換性を保つためのダミー設定クラス。
    実際の選別ロジックは filter_asins.py 側でやる。
    """
    min_profit: int = 300
    min_roi: float = 0.3
    max_avg_rank_90d: int = 250000
    block_amazon_current_buybox: bool = True
    debug_no_fba_fee: bool = False


def load_selection_config() -> SelectionConfig:
    """
    config.toml に [selection] セクションがあれば読み込む。
    無ければデフォルト値で返す。
    """
    if not os.path.exists(CONFIG_PATH):
        return SelectionConfig()

    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    sel: Dict[str, Any] = raw.get("selection", {}) or {}

    return SelectionConfig(
        min_profit=int(sel.get("min_profit", 300)),
        min_roi=float(sel.get("min_roi", 0.3)),
        max_avg_rank_90d=int(sel.get("max_avg_rank_90d", 250000)),
        block_amazon_current_buybox=bool(sel.get("block_amazon_current_buybox", True)),
        debug_no_fba_fee=bool(sel.get("debug_no_fba_fee", False)),
    )


def run_selection() -> None:
    """
    役割：
      - data/input_candidates.csv を読み込む
      - ASIN 列があることを確認
      - そのまま data/output_selected.csv として書き出す

    実際の Keepa / 楽天 / 利益判定は filter_asins.py 側で実施。
    """
    config = load_selection_config()
    print(f"Loaded config: {config}")

    print(f"[INFO] Loading input candidates from: {INPUT_PATH}")
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(
            f"候補リストが見つかりませんでした: {INPUT_PATH}\n"
            "data/input_candidates.csv に ASIN リストを保存してください。"
        )

    # input_candidates.csv は CSV 想定
    df = pd.read_csv(INPUT_PATH)

    # ASIN 列は必須
    asin_col_candidates = ["ASIN", "asin", "asin_code", "asinコード"]
    asin_col = None
    for c in asin_col_candidates:
        if c in df.columns:
            asin_col = c
            break

    if asin_col is None:
        raise ValueError(
            f"ASIN 列が見つかりませんでした。"
            f" 想定ヘッダ: {asin_col_candidates}, 実際の列: {list(df.columns)}"
        )

    # 今回は特に条件を絞らず、そのまま出力にコピー
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"[INFO] Wrote selected candidates to: {OUTPUT_PATH}")
    print(f"[INFO] rows: {len(df)}")


def main() -> None:
    run_selection()


if __name__ == "__main__":
    main()