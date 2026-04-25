"""派生サイト宣言的レジストリ ``VARIANTS``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VariantConfig:
    """派生サイト 1 件分の URL とフォーム名を表す不変構造体.

    Attributes
    ----------
    name : str
        レジストリキー (例: ``"mf"`` / ``"xmf_ssnb"``).
    base_url : str
        ログイン起点 URL.
    accounts_url : str
        口座一覧ページ URL (account spider が叩く).
    transactions_url : str
        取引一覧ページ URL (transaction spider が叩く).
    asset_allocation_url : str
        資産配分ページ URL (asset_allocation spider が叩く).
    login_form_email : str
        メール入力 ``input[name="..."]`` の name 属性.
    login_form_password : str
        パスワード入力 ``input[name="..."]`` の name 属性.
    is_partner_portal : bool
        ``x.moneyforward.com`` 系 (パートナーポータル) なら True.
    """

    name: str
    base_url: str
    accounts_url: str
    transactions_url: str
    asset_allocation_url: str
    login_form_email: str
    login_form_password: str
    is_partner_portal: bool


# 既知 variant. ``mf`` は既存 spider 群と等価設定 (refactor 前互換).
VARIANTS: dict[str, VariantConfig] = {
    "mf": VariantConfig(
        name="mf",
        base_url="https://moneyforward.com/",
        accounts_url="https://moneyforward.com/accounts",
        transactions_url="https://moneyforward.com/cf",
        asset_allocation_url="https://moneyforward.com/bs/portfolio",
        login_form_email="mfid_user[email]",
        login_form_password="mfid_user[password]",  # noqa: S106 - form field name, not a secret
        is_partner_portal=False,
    ),
    # c3 iter1 雛形. URL / selector の実値は c3 iter2 以降で実環境調査時に確定.
    "xmf_ssnb": VariantConfig(
        name="xmf_ssnb",
        base_url="https://ssnb.x.moneyforward.com/",
        accounts_url="https://ssnb.x.moneyforward.com/accounts",
        transactions_url="https://ssnb.x.moneyforward.com/cf",
        asset_allocation_url="https://ssnb.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106 - form field name, not a secret
        is_partner_portal=True,
    ),
}


def get_variant(name: str) -> VariantConfig:
    """``VARIANTS`` から ``name`` の設定を返す.

    Parameters
    ----------
    name : str
        variant 名.

    Returns
    -------
    VariantConfig
        対応する設定.

    Raises
    ------
    KeyError
        未登録の variant 名を指定した場合.
    """
    if name not in VARIANTS:
        raise KeyError(f"unknown variant: {name!r}; known={sorted(VARIANTS)}")
    return VARIANTS[name]
