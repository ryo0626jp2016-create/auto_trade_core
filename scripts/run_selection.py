from __future__ import annotations
import csv
import os
from typing import List, Dict, Any

from .keepa_client import get_product_info
from .evaluator import evaluate_item


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_PATH = os.path.join(DATA_DIR, "input_candidates.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "output_selected.csv")


def read_candidates() -> List[Dict[str, Any]]:
    with open(INPUT_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_selected(selected: List[Dict[str, Any]]) -> None:
    if not selected:
        print("No items selected.")
        return

    fieldnames = list(selected[0].keys())
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)
    print(f"Selected {len(selected)} items -> {OUTPUT_PATH}")


def main() -> None:
    candidates = read_candidates()
    selected: List[Dict[str, Any]] = []

    print(f"Loaded {len(candidates)} candidate items.")

    for row in candidates:
        asin = row["asin"].strip()
        buy_price = float(row["buy_price"])

        print(f"\n=== Evaluating ASIN {asin} ===")

        product_stats = get_product_info(asin)
        result = evaluate_item(asin, buy_price, product_stats)

        if result.get("is_ok"):
            print(f"OK: {asin} profit={result['profit']} roi={result['roi']}")
            selected.append(result)
        else:
            print(f"NG: {asin} reason={result.get('reason')}")

    write_selected(selected)


if __name__ == "__main__":
    main()
