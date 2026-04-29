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

    Notes
    -----
    Derived attribute ``login_url`` returns the explicit sign-in form URL
    (``/sign_in`` for mf, ``/users/sign_in`` for partner portals) so
    spiders can navigate directly without scraping the top-page header.
    """

    name: str
    base_url: str
    accounts_url: str
    transactions_url: str
    asset_allocation_url: str
    login_form_email: str
    login_form_password: str
    is_partner_portal: bool

    @property
    def login_url(self) -> str:
        """Direct URL of the login form for this variant."""
        suffix = "users/sign_in" if self.is_partner_portal else "sign_in"
        return self.base_url.rstrip("/") + "/" + suffix


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
    # c3 iter1 で追加. T3 で 3 spider 完全実装.
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
    # 元 PJ XmfSpider 系列 (一般 partner portal). c3 iter2 T4 で追加.
    "xmf": VariantConfig(
        name="xmf",
        base_url="https://x.moneyforward.com/",
        accounts_url="https://x.moneyforward.com/accounts",
        transactions_url="https://x.moneyforward.com/cf",
        asset_allocation_url="https://x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_mizuho": VariantConfig(
        name="xmf_mizuho",
        base_url="https://mizuho.x.moneyforward.com/",
        accounts_url="https://mizuho.x.moneyforward.com/accounts",
        transactions_url="https://mizuho.x.moneyforward.com/cf",
        asset_allocation_url="https://mizuho.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_jabank": VariantConfig(
        name="xmf_jabank",
        base_url="https://jabank.x.moneyforward.com/",
        accounts_url="https://jabank.x.moneyforward.com/accounts",
        transactions_url="https://jabank.x.moneyforward.com/cf",
        asset_allocation_url="https://jabank.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_smtb": VariantConfig(
        name="xmf_smtb",
        base_url="https://smtb.x.moneyforward.com/",
        accounts_url="https://smtb.x.moneyforward.com/accounts",
        transactions_url="https://smtb.x.moneyforward.com/cf",
        asset_allocation_url="https://smtb.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_linkx": VariantConfig(
        name="xmf_linkx",
        base_url="https://linkx.x.moneyforward.com/",
        accounts_url="https://linkx.x.moneyforward.com/accounts",
        transactions_url="https://linkx.x.moneyforward.com/cf",
        asset_allocation_url="https://linkx.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_okashin": VariantConfig(
        name="xmf_okashin",
        base_url="https://okashin.x.moneyforward.com/",
        accounts_url="https://okashin.x.moneyforward.com/accounts",
        transactions_url="https://okashin.x.moneyforward.com/cf",
        asset_allocation_url="https://okashin.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_shiga": VariantConfig(
        name="xmf_shiga",
        base_url="https://shiga.x.moneyforward.com/",
        accounts_url="https://shiga.x.moneyforward.com/accounts",
        transactions_url="https://shiga.x.moneyforward.com/cf",
        asset_allocation_url="https://shiga.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
        is_partner_portal=True,
    ),
    "xmf_shiz": VariantConfig(
        name="xmf_shiz",
        base_url="https://shiz.x.moneyforward.com/",
        accounts_url="https://shiz.x.moneyforward.com/accounts",
        transactions_url="https://shiz.x.moneyforward.com/cf",
        asset_allocation_url="https://shiz.x.moneyforward.com/bs/portfolio",
        login_form_email="sign_in_session_service[email]",
        login_form_password="sign_in_session_service[password]",  # noqa: S106
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
