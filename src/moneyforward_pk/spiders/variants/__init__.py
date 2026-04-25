"""Moneyforward 派生サイト (xmf_*) 対応の宣言的レジストリ.

元 PJ では Makefile + 継承スパイダーで 7 派生サイト (ssnb / mizuho / jabank /
linkx / okashin / shiga / shiz) を表現していた. ここでは
``VariantConfig`` dataclass + ``VARIANTS`` 辞書で同等の情報を宣言的に持つ.

c3 iter1 では ``mf`` (本サイト) と ``xmf_ssnb`` (雛形) の 2 件のみ.
他 6 サイトは c3 iter2+ で URL/selector 調査済み次第追加する.
"""

from moneyforward_pk.spiders.variants.registry import (
    VARIANTS,
    VariantConfig,
    get_variant,
)

__all__ = ["VARIANTS", "VariantConfig", "get_variant"]
