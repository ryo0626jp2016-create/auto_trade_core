from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import List

import tomllib  # Python 3.11+
from .keepa_client import get_product_info, ProductStats

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INPUT_CSV = os.path.join(DATA_DIR, "input_candidates.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "output_selected.csv")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


# =========================
# 設定読み込み
# =========================
@dataclass
class SelectionConfig:
    min_profit: int
    min_roi: float
    max_avg_rank_90d: int
    block_amazon_current_buybox: bool
    max_amazon_presence_ratio: float  # 例: 0.3 = 30%
    max_amazon_buybox_count: int      # 例: 10 回まで


def load_selection_config() -> SelectionConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    s = raw.get("selection", {})

    return SelectionConfig(
        min_profit=int(s.get("min_profit", 500)),
        min_roi=float(s.get("min_roi", 0.3)),
        max_avg_rank_90d=int(s.get("max_avg_rank_90d", 100_000)),
        block_amazon_current_buybox=bool(
            s.get("block_amazon_current_buybox", True)
        ),
        max_amazon_presence_ratio=float(s.get("max_amazon_presence_ratio", 0.3)),
        max_amazon_buybox_count=int(s.get("max_amazon_buybox_count", 10)),
    )


# =========================
# 入力候補データ
# =========================
@dataclass
class CandidateItem:
    asin: str
    buy_price: int
    source: str


def load_candidates() -> List[CandidateItem]:
    items: List[CandidateItem] = []
    if not os.path.exists(INPUT_CSV):
        print(f"[WARN] input CSV not found: {INPUT_CSV}")
        return items

    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = row.get("asin", "").strip()
            if not asin:
                continue
            try:
                buy_price = int(float(row.get("buy_price", "0")))
            except ValueError:
                print(f"[WARN] invalid buy_price for ASIN {asin}: {row.get('buy_price')}")
                continue
            source = row.get("source", "").strip() or "unknown"
            items.append(CandidateItem(asin=asin, buy_price=buy_price, source=source))

    print(f"Loaded {len(items)} candidate items.")
    return items


# =========================
# 仕入れ判定ロジック
# =========================
def is_profitable(stats: ProductStats, buy_price: int, cfg: SelectionConfig) -> tuple[bool, str, float, float]:
    """
    仕入れ可否を判定する。
    戻り値: (OKかどうか, 理由, 利益額, ROI)
    """
    # 価格情報がなければ判定不可
    if stats.expected_sell_price is None:
        return False, "sell_price_missing", 0.0, 0.0

    sell_price = stats.expected_sell_price

    # 手数料などは簡略化してまずは単純差分で計算（あとで拡張可）
    profit = sell_price - buy_price
    roi = profit / buy_price if buy_price > 0 else 0.0

    # ランキング
    if stats.avg_rank_90d is None:
        return False, "rank_missing", profit, roi
    if stats.avg_rank_90d > cfg.max_avg_rank_90d:
        return False, f"rank_too_low_{stats.avg_rank_90d}", profit, roi

    # 利益・ROI
    if profit < cfg.min_profit:
        return False, f"profit_too_small_{profit}", profit, roi
    if roi < cfg.min_roi:
        return False, f"roi_too_small_{roi:.2f}", profit, roi

    # ========== Amazon 本体チェック ==========
    # 現在のBuyBoxがAmazonなら即NG
    if cfg.block_amazon_current_buybox and stats.amazon_current:
        return False, "amazon_current_buybox", profit, roi

    # Amazon presence ratio（在庫率）が高すぎる
    if (
        stats.amazon_presence_ratio is not None
        and stats.amazon_presence_ratio > cfg.max_amazon_presence_ratio
    ):
        return False, f"amazon_presence_high_{stats.amazon_presence_ratio:.2f}", profit, roi

    # AmazonがBuyBoxを取っていた回数が多すぎる
    if (
        stats.amazon_buybox_count is not None
        and stats.amazon_buybox_count > cfg.max_amazon_buybox_count
    ):
        return False, f"amazon_buybox_count_high_{stats.amazon_buybox_count}", profit, roi

    # ここまでクリアなら仕入れOK
    return True, "ok", profit, roi


# =========================
# メイン処理
# =========================
def main() -> None:
    cfg = load_selection_config()
    candidates = load_candidates()

    selected_rows: List[dict] = []

    for c in candidates:
        print(f"\n=== Evaluating ASIN {c.asin} ===")

        stats = get_product_info(c.asin)
        if stats is None:
            print(" - Skip: Could not fetch Keepa data.")
            continue

        ok, reason, profit, roi = is_profitable(stats, c.buy_price, cfg)

        print(f" - Title: {stats.title}")
        print(f" - Expected sell price: {stats.expected_sell_price}")
        print(f" - Avg rank 90d: {stats.avg_rank_90d}")
        print(f" - Profit: {profit:.0f}, ROI: {roi:.2%}")
        print(
            f" - Amazon presence ratio: {stats.amazon_presence_ratio}, "
            f"buybox_count: {stats.amazon_buybox_count}, "
            f"current_is_amazon: {stats.amazon_current}"
        )
        print(f" - Decision: {'OK' if ok else 'NG'} ({reason})")

        if not ok:
            continue

        selected_rows.append(
            {
                "asin": c.asin,
                "title": stats.title,
                "buy_price": c.buy_price,
                "expected_sell_price": stats.expected_sell_price,
                "profit": round(profit),
                "roi": round(roi, 3),
                "avg_rank_90d": stats.avg_rank_90d,
                "amazon_presence_ratio": (
                    round(stats.amazon_presence_ratio, 3)
                    if stats.amazon_presence_ratio is not None
                    else None
                ),
                "amazon_buybox_count": stats.amazon_buybox_count,
                "source": c.source,
            }
        )

    # 結果を書き出し
    if not selected_rows:
        print("\nNo items passed the selection criteria. No CSV will be written.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    fieldnames = [
        "asin",
        "title",
        "buy_price",
        "expected_sell_price",
        "profit",
        "roi",
        "avg_rank_90d",
        "amazon_presence_ratio",
        "amazon_buybox_count",
        "source",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected_rows)

    print(f"\nWrote {len(selected_rows)} selected items to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
