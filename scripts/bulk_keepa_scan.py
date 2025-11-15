from __future__ import annotations
import os
import csv
import time
from dataclasses import dataclass
from typing import List, Set, Optional

from .keepa_api import get_product_info



# ====== 設定値（ここを調整すれば絞り方を変えられる） ======

# 読み込む Keepa ベストセラー CSV のパターン
# 例: data/KeepaExport-*.csv を全部読む
KEEPA_EXPORT_GLOB = os.path.join("data", "KeepaExport-*.csv")

# 出力先 CSV
OUTPUT_CSV = os.path.join("data", "keepa_scan_candidates.csv")

# フィルタ条件
MAX_AVG_RANK_90D = 50_000         # 90日平均ランキング この位以内
MAX_AMAZON_PRESENCE = 0.1         # Amazon本体の在庫割合（0.0〜1.0）この値以下のみ
REQUIRE_AMAZON_NOT_CURRENT = True # 現在のBuyBoxがAmazonなら除外
MIN_SELL_PRICE = 2000.0           # 想定販売価格の最低ライン（円）

# Keepa API 呼び出し間隔（秒）
# 0 にすると全力で叩くので、トークン消費が気になる場合は 0.5〜1.0 くらいに
SLEEP_BETWEEN_CALLS = 0.0


# ====== ロジック ======

def load_asins_from_keepa_exports(pattern: str) -> List[str]:
    """
    data/KeepaExport-*.csv のようなファイル群から ASIN を全部集める。
    ・ヘッダに 'ASIN' or 'asin' カラムがあればそこを使う
    ・なければ 1列目を ASIN とみなす
    """
    import glob

    files = glob.glob(pattern)
    if not files:
        print(f"[WARN] No Keepa export files found for pattern: {pattern}")
        return []

    asin_set: Set[str] = set()

    for path in files:
        print(f"[INFO] Loading ASINs from {path}")
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            continue

        header = rows[0]
        body = rows[1:]

        # ヘッダに ASIN カラムがあるか判定
        asin_idx = None
        for i, col in enumerate(header):
            c = (col or "").strip().lower()
            if c == "asin":
                asin_idx = i
                break

        if asin_idx is None:
            # なければ 0列目を ASIN とみなす
            asin_idx = 0

        for row in body:
            if len(row) <= asin_idx:
                continue
            asin = row[asin_idx].strip()
            if asin:
                asin_set.add(asin)

    asins = sorted(asin_set)
    print(f"[INFO] Total unique ASINs loaded: {len(asins)}")
    return asins


@dataclass
class ScanResult:
    asin: str
    title: str
    expected_sell_price: float
    avg_rank_90d: int
    amazon_presence_ratio: Optional[float]
    amazon_buybox_count: Optional[int]
    amazon_current: bool


def is_good_candidate(p: "ProductStats") -> bool:
    """
    Keepa から取得した ProductStats が「仕入れ候補として優秀か」を判定。
    利益はまだ見ない。あくまで「回転」「Amazon本体」「価格」での事前フィルタ。
    """
    # ランクフィルタ
    if p.avg_rank_90d is None:
        return False
    if p.avg_rank_90d > MAX_AVG_RANK_90D:
        return False

    # 販売価格フィルタ
    if p.expected_sell_price is None:
        return False
    if p.expected_sell_price < MIN_SELL_PRICE:
        return False

    # Amazon本体フィルタ
    if REQUIRE_AMAZON_NOT_CURRENT and p.amazon_current:
        # 現在のBuyBoxがAmazonなら除外
        return False

    if p.amazon_presence_ratio is not None:
        if p.amazon_presence_ratio > MAX_AMAZON_PRESENCE:
            # Amazon本体が過去にそこそこ出ている商品は除外
            return False

    # ここまで通れば候補OK
    return True


def main():
    # 1. CSV群から ASIN を集める
    asins = load_asins_from_keepa_exports(KEEPA_EXPORT_GLOB)
    if not asins:
        print("[ERROR] No ASINs found. Please put Keepa export CSVs under data/ with pattern 'KeepaExport-*.csv'.")
        return

    results: List[ScanResult] = []

    # 2. ASINごとに Keepa API を叩く
    for idx, asin in enumerate(asins, start=1):
        print(f"\n=== [{idx}/{len(asins)}] ASIN {asin} ===")

        product = get_product_info(asin)
        if not product:
            print(" - Skip: Could not fetch Keepa data.")
            continue

        print(f" - Title: {product.title}")
        print(f" - Expected sell price: {product.expected_sell_price}")
        print(f" - Avg rank 90d: {product.avg_rank_90d}")
        print(f" - Amazon presence ratio: {product.amazon_presence_ratio}")
        print(f" - buybox_count: {product.amazon_buybox_count}")
        print(f" - current_is_amazon: {product.amazon_current}")

        if is_good_candidate(product):
            print(" - Decision: OK (good candidate)")
            results.append(
                ScanResult(
                    asin=product.asin,
                    title=product.title,
                    expected_sell_price=product.expected_sell_price or 0.0,
                    avg_rank_90d=product.avg_rank_90d or 0,
                    amazon_presence_ratio=product.amazon_presence_ratio,
                    amazon_buybox_count=product.amazon_buybox_count,
                    amazon_current=product.amazon_current,
                )
            )
        else:
            print(" - Decision: NG")

        if SLEEP_BETWEEN_CALLS > 0:
            time.sleep(SLEEP_BETWEEN_CALLS)

    # 3. 結果を書き出し
    if not results:
        print("[INFO] No good candidates found. No CSV will be written.")
        return

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "asin",
                "title",
                "expected_sell_price",
                "avg_rank_90d",
                "amazon_presence_ratio",
                "amazon_buybox_count",
                "amazon_current",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.asin,
                    r.title,
                    r.expected_sell_price,
                    r.avg_rank_90d,
                    r.amazon_presence_ratio,
                    r.amazon_buybox_count,
                    r.amazon_current,
                ]
            )

    print(f"[INFO] Saved candidates to {OUTPUT_CSV}")
    print(f"[INFO] Total good candidates: {len(results)}")


if __name__ == "__main__":
    main()
