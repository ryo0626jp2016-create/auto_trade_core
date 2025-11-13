def get_product_info(asin: str) -> Optional[ProductStats]:
    """
    指定した ASIN の Keepa 情報を取得し、仕入れ判定に必要な要約情報を返す。
    """
    config = load_keepa_config()
    api = keepa.Keepa(config.api_key)

    # デバッグ用：キー長 & ドメインを表示（キー本体はマスク）
    print(f"[DEBUG] Keepa domain = {config.domain}")
    print(f"[DEBUG] Keepa API key length = {len(config.api_key)}")
    if len(config.api_key) < 10:
        print("[ERROR] Keepa API key が短すぎます。config.toml / Secrets を確認してください。")

    try:
        # stats=90: 過去90日分の統計情報を含める
        products = api.query(
            asin,
            stats=90,
            domain=config.domain,
            history=False,   # とりあえず履歴は取らない（必要なら True に）
            buybox=True,
            rating=False,
            offers=0,
            progress_bar=False,
        )
    except RuntimeError as e:
        # ここで REQUEST_REJECTED などをキャッチして、そのASINだけスキップする
        print(f"[ERROR] Keepa request rejected for ASIN {asin}: {e}")
        return None

    if not products:
        print(f"[WARN] Keepa returned no product for ASIN {asin}")
        return None

    p = products[0]

    title = p.get("title", "")
    stats = p.get("stats") or {}

    avg_rank_90d = _get_avg_rank_90d_from_stats(stats)
    expected_sell_price = _get_expected_sell_price_from_stats(stats)

    buybox_is_amazon = bool(stats.get("buyBoxIsAmazon", False))

    return ProductStats(
        asin=asin,
        title=title,
        avg_rank_90d=avg_rank_90d,
        expected_sell_price=expected_sell_price,
        buybox_is_amazon=buybox_is_amazon,
    )
