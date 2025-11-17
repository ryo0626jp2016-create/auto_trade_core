"""
bulk_keepa_scan.py
KeepaエクスポートCSVをまとめて読み込み → ASINごとにKeepa APIで詳細取得
→ 仕入れ候補をCSV化するスクリプト
"""

from __future__ import annotations
import os
import csv
from typing import List, Dict, Any, Optional

# ★重要★ keepa_client を読み込む（あなたの環境に合わせて修正済）
from scripts.keepa_client import get_product_info, ProductStats


# === 入出力パス ===
INPUT_DIR = os.path.join("data", "raw_keepa")
OUTPUT_PATH = os.path.join("data", "keepa_scan_candidates.csv")


def load_asin_from_csv(file_path: str) -> List[str]:
    """
    Keepa BestSeller CSV から ASIN を抽出する
    - 1列目 or "ASIN" 列を優先して読み込む
    """
    asins: List[str] = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])

        asin_index = None
        for i, col in enumerate(header):
            if col.strip().lower() == "asin":
                asin_index = i
                break

        for row in reader:
            if asin_index is not None and len(row) > asin_index:
                asin = row[asin_index].strip()
            else:
                asin = row[0].strip()  # fallback

            if asin and asin not in asins:
                asins.append(asin)

    return asins


def scan_bulk_asins(asins: List[str]) -> List[Dict[str, Any]]:
    """
    ASINリストを順にKeepa APIで問い合わせて、必要情報を抽出してまとめる
    """
    results: List[Dict[str, Any]] = []

    for asin in asins:
        print(f"=== Evaluating ASIN {asin} ===")

        info: Optional[ProductStats] = get_product_info(asin)
        if info is None:
            print(f" - Skip: Could not fetch Keepa data.")
            continue

        row = {
            "asin": info.asin,
            "title": info.title,
            "avg_rank_90d": info.avg_rank_90d,
            "expected_sell_price": info.expected_sell_price,
            "amazon_presence_ratio": info.amazon_presence_ratio,
            "amazon_buybox_count": info.amazon_buybox_count,
            "amazon_current": info.amazon_current,
            "weight_kg": info.weight_kg,
            "dimensions_cm": info.dimensions_cm,
            "category": info.category,
        }
        results.append(row)

    return results


def save_results_to_csv(rows: List[Dict[str, Any]], output_path: str) -> None:
    """
    スキャン結果をCSVで保存
    """
    if not rows:
        print("No results to save.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {output_path}")


def main():
    # === Step1: raw_keepa フォルダ内のCSVを全部読み込む ===
    if not os.path.exists(INPUT_DIR):
        print(f"[ERROR] Input directory not found: {INPUT_DIR}")
        return

    all_asins: List[str] = []
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".csv"):
            path = os.path.join(INPUT_DIR, filename)
            print(f"[INFO] Loading ASINs from {path}")
            asins = load_asin_from_csv(path)
            all_asins.extend(asins)

    # 重複除去
    all_asins = list(dict.fromkeys(all_asins))
    print(f"[INFO] Total ASINs loaded: {len(all_asins)}")

    # === Step2: Keepaで詳細スキャン ===
    results = scan_bulk_asins(all_asins)

    # === Step3: 保存 ===
    save_results_to_csv(results, OUTPUT_PATH)


if __name__ == "__main__":
    main()