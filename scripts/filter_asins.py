from __future__ import annotations

import os
import argparse
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from keepa_client import load_keepa_config, _get_domain_id, analyze_amazon_presence
from rakuten_client import get_lowest_price_and_url_by_jan

# ===== 判定条件 =====

MAX_AVG_RANK_90D = 250_000       # 高回転の目安
MIN_SALES_RANK_DROPS_30 = 20     # 30日で20回以上のランクドロップ
MIN_PROFIT_YEN = 300             # 利益300円以上
MIN_ROI_PERCENT = 30             # ROI30%以上

# ====================


def detect_asin_column(df: pd.DataFrame) -> str:
    candidates = ["ASIN", "asin", "Asin"]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(f"ASIN列が見つかりません: {candidates} のいずれかの列名を使ってください。")


def detect_category_column(df: pd.DataFrame) -> Optional[str]:
    candidates = ["カテゴリ", "カテゴリー", "category", "Category"]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def estimate_amazon_fee(price: Optional[float]) -> float:
    """
    簡易なAmazon手数料モデル（近似）:
    販売価格の15% + 100円 を仮定。
    """
    if price is None:
        return 0.0
    return price * 0.15 + 100.0


def calc_profit_and_roi(
    selling_price: Optional[float],
    cost_price: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if selling_price is None or cost_price is None or cost_price <= 0:
        return None, None
    fee = estimate_amazon_fee(selling_price)
    profit = selling_price - cost_price - fee
    roi = (profit / cost_price) * 100.0
    return profit, roi


def load_candidate_df(path: str) -> Optional[pd.DataFrame]:
    """
    CSV / Excel を拡張子で自動判定して読み込む。
    ファイルが無い場合は None を返して終了させる。
    """
    if not os.path.exists(path):
        print(f"[WARN] 入力ファイルが存在しません: {path}")
        print("[WARN] run_selection で output_selected.csv が生成されなかった可能性があります。")
        return None

    print(f"[INFO] Loading candidate ASIN list from: {path}")
    lower = path.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    return df


def fetch_keepa_basic(asin: str) -> Optional[Dict[str, Any]]:
    """
    単一ASINの Keepa product 情報から、
    フィルタに必要な情報だけ抽出して返す。
    """
    config = load_keepa_config()
    domain_id = _get_domain_id(config.domain)

    params = {
        "key": config.api_key,
        "domain": domain_id,
        "asin": asin,
        "stats": 90,
        "history": 1,
    }

    try:
        resp = requests.get("https://api.keepa.com/product", params=params, timeout=30)
    except Exception as e:
        print(f"[ERROR] HTTP error when calling Keepa for ASIN {asin}: {e}")
        return None

    print(f"[DEBUG] Keepa HTTP status for {asin}: {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] JSON decode error for ASIN {asin}: {e}")
        print(f"[DEBUG] Raw response (first 200 chars): {resp.text[:200]}")
        return None

    if "error" in data and data["error"]:
        print(f"[ERROR] Keepa API error for ASIN {asin}: {data['error']}")
        return None

    products = data.get("products") or []
    if not products:
        print(f"[WARN] Keepa returned no products for ASIN {asin}")
        return None

    p = products[0]
    stats: Dict[str, Any] = p.get("stats") or {}

    # タイトル
    title = p.get("title", "") or ""

    # 90日平均ランキング（avg90[3] = SALES）
    avg_rank_90d: Optional[int] = None
    avg90 = stats.get("avg90") or []
    if len(avg90) > 3:
        value = avg90[3]
        if value is not None and value > 0:
            avg_rank_90d = int(value)

    # 30日間のランキングドロップ回数
    sales_rank_drops_30 = stats.get("salesRankDrops30")

    # 販売想定価格（BuyBox）
    raw_buybox = stats.get("buyBoxPrice")
    selling_price: Optional[float] = None
    if isinstance(raw_buybox, (int, float)) and raw_buybox > 0:
        selling_price = raw_buybox / 100.0  # 1/100通貨単位

    # JANコード（eanList）
    ean_list = p.get("eanList") or []
    jan: Optional[str] = ean_list[0] if ean_list else None

    # Amazon本体関連
    amazon_info = analyze_amazon_presence(p)
    buybox_is_amazon = bool(stats.get("buyBoxIsAmazon", False))

    # ざっくりカテゴリ
    category = p.get("productGroup")

    return {
        "asin": asin,
        "title": title,
        "avg_rank_90d": avg_rank_90d,
        "sales_rank_drops_30": sales_rank_drops_30,
        "selling_price": selling_price,
        "jan": jan,
        "buybox_is_amazon": buybox_is_amazon,
        "amazon_presence_ratio": amazon_info["amazon_presence_ratio"],
        "amazon_buybox_count": amazon_info["amazon_buybox_count"],
        "amazon_current": amazon_info["amazon_current"],
        "category": category,
    }


def is_amazon_absent(product: Dict[str, Any]) -> bool:
    """
    Amazon本体が「ほぼいない」とみなせるかどうか判定。
    """
    if product.get("buybox_is_amazon"):
        return False

    if product.get("amazon_current"):
        return False

    ratio = product.get("amazon_presence_ratio")
    if ratio is not None and ratio > 0.1:
        # 履歴の1割以上でAmazon在庫あり → 参入多いとみなして除外
        return False

    return True


def filter_asins(input_path: str, output_dir: str) -> None:
    df = load_candidate_df(input_path)
    if df is None:
        # ファイルが無い場合はここで静かに終了
        return

    asin_col = detect_asin_column(df)
    cat_col = detect_category_column(df)

    asins: List[str] = (
        df[asin_col]
        .astype(str)
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )

    print(f"[INFO] {len(asins)} 個のASINを評価します。")

    results: List[Dict[str, Any]] = []

    for asin in asins:
        print(f"\n=== Evaluating ASIN {asin} ===")
        product = fetch_keepa_basic(asin)
        if not product:
            print(" - Skip: Keepaデータ取得失敗")
            continue

        # 1) 回転率（ランキング）チェック
        avg_rank_90d = product.get("avg_rank_90d")
        drops_30 = product.get("sales_rank_drops_30")

        if avg_rank_90d is None or avg_rank_90d > MAX_AVG_RANK_90D:
            print(f" - Skip: avg_rank_90d={avg_rank_90d} > {MAX_AVG_RANK_90D}")
            continue

        if drops_30 is None or drops_30 < MIN_SALES_RANK_DROPS_30:
            print(f" - Skip: sales_rank_drops_30={drops_30} < {MIN_SALES_RANK_DROPS_30}")
            continue

        # 2) Amazon本体不在チェック
        if not is_amazon_absent(product):
            print(" - Skip: Amazon本体の参入頻度が高いと判断")
            continue

        # 3) 楽天の最安値取得（JANベース）
        jan = product.get("jan")
        if not jan:
            print(" - Skip: JANコードが無いため楽天検索不可")
            continue

        rakuten_price, rakuten_url = get_lowest_price_and_url_by_jan(jan)
        if rakuten_price is None:
            print(" - Skip: 楽天で商品が見つからず")
            continue

        # 4) 利益・ROI計算
        selling_price = product.get("selling_price")
        profit, roi = calc_profit_and_roi(selling_price, rakuten_price)

        if profit is None or roi is None:
            print(" - Skip: 利益 or ROI 計算不可")
            continue

        if profit < MIN_PROFIT_YEN or roi < MIN_ROI_PERCENT:
            print(f" - Skip: profit={profit:.0f}, ROI={roi:.1f}% が条件未達")
            continue

        print(f" -> OK: profit={profit:.0f}円, ROI={roi:.1f}%")

        result_row: Dict[str, Any] = {
            "ASIN": asin,
            "タイトル": product.get("title"),
            "カテゴリ(Keepa)": product.get("category"),
            "avg_rank_90d": avg_rank_90d,
            "sales_rank_drops_30": drops_30,
            "Amazon本体参入率": product.get("amazon_presence_ratio"),
            "販売価格_想定(Amazon)": selling_price,
            "仕入れ価格_楽天": rakuten_price,
            "概算利益": round(profit),
            "ROI(%)": round(roi, 1),
            "楽天リンク": rakuten_url,
        }

        if cat_col:
            # 元ファイルのカテゴリも引き継ぎ
            original_cat = (
                df.loc[df[asin_col].astype(str) == asin, cat_col]
                .astype(str)
                .iloc[0]
            )
            result_row["カテゴリ(元ファイル)"] = original_cat

        results.append(result_row)

    if not results:
        print("[INFO] 条件を満たすASINがありませんでした。")
        return

    out_df = pd.DataFrame(results)
    os.makedirs(output_dir, exist_ok=True)

    # 全体ファイル
    all_path = os.path.join(output_dir, "filtered_asins_all.xlsx")
    out_df.to_excel(all_path, index=False)
    print(f"[INFO] 全体ファイルを出力しました: {all_path}")

    # カテゴリ別出力（元ファイルのカテゴリがある場合）
    if "カテゴリ(元ファイル)" in out_df.columns:
        for cat, g in out_df.groupby("カテゴリ(元ファイル)"):
            safe_cat = str(cat) if cat else "unknown"
            fname = f"filtered_asins_{safe_cat}.xlsx"
            path = os.path.join(output_dir, fname)
            g.to_excel(path, index=False)
            print(f"[INFO] カテゴリ別ファイルを出力しました: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/output_selected.csv",
        help="ASIN候補リストのパス（CSV/Excel 両対応。デフォルト: data/output_selected.csv）",
    )
    parser.add_argument(
        "--output-dir",
        default="output/filtered_asins",
        help="出力ディレクトリ（デフォルト: output/filtered_asins）",
