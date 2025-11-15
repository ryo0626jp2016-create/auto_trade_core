from __future__ import annotations
import csv
import os
from typing import List

from .keepa_client import get_product_info   # ←ここが重要！

INPUT_DIR = "data/input_lists"
OUTPUT_DIR = "data/output_scans"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_asin_list(filepath: str) -> List[str]:
    asins = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            asin = row[0].strip()
            if len(asin) == 10:
                asins.append(asin)
    return asins


def main():
    print("=== Bulk Keepa Scan Start ===")

    for filename in os.listdir(INPUT_DIR):
        if not filename.endswith(".csv"):
            continue

        in_path = os.path.join(INPUT_DIR, filename)
        print(f"\n--- Loading {in_path} ---")

        asin_list = load_asin_list(in_path)
        print(f"{len(asin_list)} ASIN loaded")

        out_path = os.path.join(OUTPUT_DIR, f"scan_{filename}")
        rows = []

        for asin in asin_list:
            print(f"Checking ASIN {asin} ...")
            info = get_product_info(asin)

            if info is None:
                rows.append([asin, "ERROR"])
                continue

            rows.append([
                info.asin,
                info.title,
                info.avg_rank_90d,
                info.expected_sell_price,
                info.amazon_current,
                info.amazon_presence_ratio,
                info.amazon_buybox_count,
                info.weight_kg,
                info.dimensions_cm,
                info.category,
            ])

        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "asin", "title", "avg_rank_90d", "expected_sell_price",
                "amazon_current", "amazon_presence_ratio", "amazon_buybox_count",
                "weight_kg", "dimensions_cm", "category"
            ])
            writer.writerows(rows)

        print(f"Saved → {out_path}")

    print("\n=== Bulk Keepa Scan Completed ===")