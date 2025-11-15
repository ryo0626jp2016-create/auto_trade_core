# scripts/bulk_keepa_scan.py
from __future__ import annotations

import csv
import glob
import os
from pathlib import Path
from typing import List, Set

from .keepa_client import get_product_info, ProductStats


# === パス設定 =========================================================

# リポジトリルート … scripts/ の 1 つ上
BASE_DIR = Path(__file__).resolve().parent.parent

# Keepa のベストセラー CSV を置くフォルダ
# 必要なら自分の環境に合わせてフォルダ名だけ変えてOK
INPUT_DIR = BASE_DIR / "data" / "bestsellers"

# 出力する候補リスト CSV
OUTPUT_PATH = BASE_DIR / "data" / "bulk_candidates.csv"


# === ユーティリティ ====================================================

def collect_asins_from_csv(file_path: Path) -> List[str]:
    """1つの Keepa Export CSV から ASIN カラムを集める。"""
    asins: List[str] = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        # ヘッダー名のブレ対策（asin, ASIN など）
        fieldnames = [name.lower() for name in reader.fieldnames or []]
        if "asin" not in fieldnames:
            print(f"[WARN] {file_path.name} に ASIN カラムがありません。スキップします。")
            return asins

        for row in reader:
            asin = (row.get("ASIN") or row.get("asin") or "").strip()
            if asin:
                asins.append(asin)

    print(f"[INFO] {file_path.name} から {len(asins)} 件の ASIN を取得しました。")
    return asins


def collect_all_asins(input_dir: Path) -> List[str]:
    """指定フォルダ配下の CSV から ASIN を重複なしで集約。"""
    if not input_dir.exists():
        print(f"[WARN] 入力ディレクトリが見つかりません: {input_dir}")
        return []

    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print(f"[WARN] {input_dir} 配下に CSV ファイルがありません。")
        return []

    all_asins: Set[str] = set()

    for csv_file in csv_files:
        asins = collect_asins_from_csv(csv_file)
        all_asins.update(asins)

    all_list = sorted(all_asins)
    print(f"[INFO] 合計 {len(all_list)} 件のユニーク ASIN を収集しました。")
    return all_list


# === メイン処理 ========================================================

def main() -> None:
    print("=== bulk_keepa_scan start ===")

    asins = collect_all_asins(INPUT_DIR)
    if not asins:
        print("[WARN] ASIN が 1 件もありません。空の CSV を出力します。")

    candidates: List[dict] = []

    for idx, asin in enumerate(asins, start=1):
        print(f"\n=== {idx}/{len(asins)} Evaluating ASIN {asin} ===")

        info: ProductStats | None = get_product_info(asin)
        if info is None:
            print(" - Skip: Keepa から情報取得できませんでした。")
            continue

        # サイズ展開（None 対応）
        length_cm = width_cm = height_cm = None
        if info.dimensions_cm is not None:
            length_cm, width_cm, height_cm = info.dimensions_cm

        row = {
            "asin": info.asin,
            "title": info.title,
            "avg_rank_90d": info.avg_rank_90d or "",
            "expected_sell_price": info.expected_sell_price or "",
            "amazon_presence_ratio": (
                round(info.amazon_presence_ratio, 4)
                if info.amazon_presence_ratio is not None
                else ""
            ),
            "amazon_buybox_count": info.amazon_buybox_count or "",
            "amazon_current": info.amazon_current,
            "weight_kg": info.weight_kg or "",
            "length_cm": length_cm or "",
            "width_cm": width_cm or "",
            "height_cm": height_cm or "",
            "category": info.category or "",
            # ここは仕入れ値をあとで手入力するための空欄
            "buy_price": "",
        }

        candidates.append(row)
        print(
            f" - Title: {info.title[:60]}..."
            f"\n   avg_rank_90d={info.avg_rank_90d}, "
            f"sell_price={info.expected_sell_price}, "
            f"amazon_current={info.amazon_current}"
        )

    # data ディレクトリを念のため作成
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "asin",
        "title",
        "avg_rank_90d",
        "expected_sell_price",
        "amazon_presence_ratio",
        "amazon_buybox_count",
        "amazon_current",
        "weight_kg",
        "length_cm",
        "width_cm",
        "height_cm",
        "category",
        "buy_price",
    ]

    # ★候補が 0 件でも必ず CSV を出力する★
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        if candidates:
            writer.writerows(candidates)

    print(
        f"\n[INFO] {len(candidates)} 件の候補を {OUTPUT_PATH} に書き出しました。"
        "（0 件でもヘッダーのみの CSV を出力）"
    )
    print("=== bulk_keepa_scan end ===")


if __name__ == "__main__":
    main()