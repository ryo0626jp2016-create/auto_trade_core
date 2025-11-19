"""
bulk_keepa_scan.py
KeepaエクスポートCSVをまとめて読み込み → ASINごとにKeepa APIで詳細取得
→ evaluator.py で判定 → 合格した仕入れ候補のみCSV化するスクリプト
"""

from __future__ import annotations
import os
import csv
from typing import List, Dict, Any, Optional

# 既存のクライアント読み込み
from scripts.keepa_client import get_product_info, ProductStats
# 【追加】判定ロジックを読み込み
from scripts.evaluator import evaluate_item


# === 入出力パス ===
INPUT_DIR = os.path.join("data", "raw_keepa")
OUTPUT_PATH = os.path.join("data", "keepa_scan_candidates.csv")


def load_asin_from_csv(file_path: str) -> List[str]:
    """
    Keepa BestSeller CSV から ASIN を抽出する
    """
    asins: List[str] = []
    if not os.path.exists(file_path):
        return asins

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader, [])
        except StopIteration:
            return asins

        asin_index = None
        for i, col in enumerate(header):
            if col.strip().lower() == "asin":
                asin_index = i
                break

        for row in reader:
            if not row: continue
            
            if asin_index is not None and len(row) > asin_index:
                asin = row[asin_index].strip()
            else:
                # ヘッダーにASINがない場合、1列目をASINとみなす
                asin = row[0].strip()

            if asin and asin not in asins:
                asins.append(asin)

    return asins


def scan_bulk_asins(asins: List[str]) -> List[Dict[str, Any]]:
    """
    ASINリストを順にKeepa APIで問い合わせて、
    evaluate_item でフィルタリングを行い、合格したものだけを返す
    """
    results: List[Dict[str, Any]] = []
    total = len(asins)

    for i, asin in enumerate(asins, 1):
        print(f"[{i}/{total}] Checking ASIN: {asin} ...", end=" ", flush=True)

        # 1. Keepaデータ取得
        info: Optional[ProductStats] = get_product_info(asin)
        if info is None:
            print("Skip (No Data)")
            continue

        # 2. 判定ロジック実行
        # ※ CSV入力には仕入れ値情報がないため、暫定的に buy_price=0 とする
        #    これによりROI判定は機能しませんが、ランキングやAmazon有無判定は動きます。
        evaluation = evaluate_item(asin=asin, buy_price=0, product_stats=info)

        # 3. 不合格ならスキップ
        if not evaluation["is_ok"]:
            print(f"NG -> {evaluation['reason']}")
            continue

        print("OK!")

        # 4. 合格データを整形
        row = {
            "asin": info.asin,
            "title": info.title,
            "reason": evaluation["reason"],  # 合格理由
            "avg_rank_90d": info.avg_rank_90d,
            "expected_sell_price": info.expected_sell_price,
            "amazon_current": info.amazon_current, # Amazon本体価格
            "is_amazon_buybox": info.buybox_is_amazon,
            "category": info.category,
            "keepa_link": f"https://keepa.com/#!product/5-{info.asin}"
        }
        results.append(row)

    return results


def save_results_to_csv(rows: List[Dict[str, Any]], output_path: str) -> None:
    """
    スキャン結果をCSVで保存
    """
    if not rows:
        print("\nNo candidates found. CSV will not be created.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        # 辞書のキーをヘッダーにする
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} candidates to: {output_path}")


def main():
    # === Step1: raw_keepa フォルダ内のCSVを全部読み込む ===
    if not os.path.exists(INPUT_DIR):
        print(f"[WARNING] Input directory not found: {INPUT_DIR}")
        # 動作確認用にディレクトリだけ作っておく
        os.makedirs(INPUT_DIR, exist_ok=True)
        print(f"Created empty directory: {INPUT_DIR}. Please upload CSVs here.")
        return

    all_asins: List[str] = []
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".csv")]
    
    if not files:
        print(f"[WARNING] No CSV files found in {INPUT_DIR}")
        return

    for filename in files:
        path = os.path.join(INPUT_DIR, filename)
        print(f"[INFO] Loading ASINs from {filename}")
        asins = load_asin_from_csv(path)
        all_asins.extend(asins)

    # 重複除去
    all_asins = list(dict.fromkeys(all_asins))
    print(f"[INFO] Total Unique ASINs loaded: {len(all_asins)}")

    if not all_asins:
        print("No ASINs to process.")
        return

    # === Step2: Keepaで詳細スキャン & 判定 ===
    results = scan_bulk_asins(all_asins)

    # === Step3: 保存 ===
    save_results_to_csv(results, OUTPUT_PATH)


if __name__ == "__main__":
    main()
