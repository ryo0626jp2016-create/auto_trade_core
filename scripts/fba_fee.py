from __future__ import annotations
from typing import Any


def estimate_fba_fee(product: Any) -> float:
    """
    デバッグ用の FBA 手数料計算。

    本番ではサイズ・重量などから FBA 手数料を計算する想定だが、
    今回はまずパイプラインを動かしたいので「常に 0 円」を返す。

    run_selection.py 側は「estimate_fba_fee(product)」という
    呼び出し方をしているので、ここも引数 1 個 (product) に揃える。
    """
    return 0.0
