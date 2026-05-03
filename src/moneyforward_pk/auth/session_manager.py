"""Playwright storage_state persistence for ID/PW logged-in sessions.

Each ``(site, login_user)`` pair maps to a per-account JSON state file under
``runtime/state/`` so that subsequent spider invocations can reuse the
session cookies without re-running ``login_flow``. The login user is masked
into the filename — first three characters of the local + domain parts
followed by a fixed ``xxx`` literal and an 8-char hash — so the directory
listing is human-recognisable without revealing the full email address
(Issue #42).

This is the MoneyForward (ID/PW) counterpart of
``scrapy_smbcnikko_pk``'s ``PasskeySessionManager`` — same storage_state
contract, but no passkey machinery (MoneyForward uses email + password
only).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _mask_user(login_user: str) -> str:
    """Mask ``login_user`` into a recognisable but reduced filename component.

    Format: ``{local[:3]}xxx_{domain_head[:3]}xxx_{sha256(login_user)[:8]}``.
    Parts shorter than 3 characters are emitted verbatim with no ``xxx``
    suffix. The trailing 8-char hash disambiguates collisions when two
    users share a 3-char prefix on both sides.
    """
    local, _, domain = login_user.partition("@")
    domain_head = domain.split(".", 1)[0] if domain else ""

    def _mask(s: str) -> str:
        return s if len(s) < 3 else f"{s[:3]}xxx"

    head = f"{_mask(local)}_{_mask(domain_head)}" if domain_head else _mask(local)
    digest = hashlib.sha256(login_user.encode("utf-8")).hexdigest()[:8]
    return f"{head}_{digest}"


class SessionManager:
    """Track Playwright storage_state for one ``(site, login_user)`` pair."""

    def __init__(self, state_dir: Path, site: str, login_user: str) -> None:
        self.state_dir = Path(state_dir)
        self.site = site
        self.login_user = login_user
        suffix = _mask_user(login_user) if login_user else "anon"
        self.state_path = self.state_dir / f"{site}_{suffix}.json"

    # ------------------------------------------------------------------ status

    def has_saved_session(self) -> bool:
        """Return True when a non-empty state file exists on disk.

        Mirrors ``PasskeySessionManager.has_saved_session()`` from
        ``scrapy_smbcnikko_pk`` so callers can use the same idiom across
        projects.
        """
        try:
            return self.state_path.exists() and self.state_path.stat().st_size > 0
        except OSError:
            return False

    def get_storage_state(self) -> str | None:
        """Path string for ``playwright_context_kwargs['storage_state']``.

        Returns ``None`` when no usable state file is present so callers
        can branch without raising. API name aligned with
        ``scrapy_smbcnikko_pk.PasskeySessionManager.get_storage_state()``.
        """
        return str(self.state_path) if self.has_saved_session() else None

    # --------------------------------------------------------------- mutators

    async def save_from_context(self, context) -> None:
        """Persist the current Playwright ``BrowserContext`` storage_state.

        Parameters
        ----------
        context : playwright.async_api.BrowserContext
            Live context whose cookies + localStorage represent the
            authenticated session. Caller must have completed login_flow
            (or otherwise verified the session is logged in) before calling.
        """
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            # Playwright's storage_state(path=...) writes JSON atomically.
            await context.storage_state(path=str(self.state_path))
            logger.info(
                "SessionManager: state saved (site=%s, path=%s)",
                self.site,
                self.state_path,
            )
        except Exception:  # noqa: BLE001
            # Persistence failure is non-fatal — the spider can still run,
            # it just won't reuse the session next time.
            logger.exception(
                "SessionManager: failed to save state (site=%s)", self.site
            )

    def invalidate_session(self) -> None:
        """Delete the state file so the next run forces a fresh login.

        Aligned with ``PasskeySessionManager.invalidate_session()``.
        """
        if not self.state_path.exists():
            return
        try:
            self.state_path.unlink()
            logger.info(
                "SessionManager: state invalidated (site=%s, path=%s)",
                self.site,
                self.state_path,
            )
        except OSError as exc:
            logger.warning(
                "SessionManager: invalidate failed (site=%s): %s",
                self.site,
                exc,
            )
