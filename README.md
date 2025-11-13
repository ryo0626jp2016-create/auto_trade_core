# auto_trade_core

Amazon転売用の「仕入れ候補自動評価コア」プロジェクトです。

## セットアップ

```bash
pip install -r requirements.txt
```

`scripts/config.example.toml` を `scripts/config.toml` にコピーし、Keepa APIキーなどを設定してください。

```bash
cp scripts/config.example.toml scripts/config.toml
# その後エディタで api_key を書き換え
```

## 使い方

1. `data/input_candidates.csv` に評価したい ASIN と仕入れ価格を入力します。
2. 下記コマンドを実行します。

```bash
python -m scripts.run_selection
```

3. `data/output_selected.csv` に「仕入れOK」の商品のみが出力されます。
