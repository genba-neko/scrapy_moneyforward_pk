"""Coverage for small helpers: SlackNotifier, build_playwright_meta."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from moneyforward.utils.playwright_utils import build_playwright_meta
from moneyforward.utils.slack_notifier import SlackNotifier


def test_build_playwright_meta_defaults():
    meta = build_playwright_meta()
    assert meta["playwright"] is True
    assert meta["playwright_context"] == "default"
    assert meta["playwright_include_page"] is False
    # Default page_methods must contain at least one PageMethod.
    assert len(meta["playwright_page_methods"]) == 1


def test_build_playwright_meta_extra_merges():
    meta = build_playwright_meta(
        include_page=True,
        context="login",
        extra={"my_flag": 7},
    )
    assert meta["playwright_include_page"] is True
    assert meta["playwright_context"] == "login"
    assert meta["my_flag"] == 7


def test_slack_notifier_skips_when_webhook_unset(monkeypatch):
    monkeypatch.delenv("SLACK_INCOMING_WEBHOOK_URL", raising=False)
    notifier = SlackNotifier()
    # Must not raise even when slackweb is not installed; the empty webhook
    # short-circuits before the import.
    notifier.notify("hello")


def test_slack_notifier_uses_constructor_webhook():
    notifier = SlackNotifier(webhook_url="https://hooks.example.com/x")
    fake_slack_cls = MagicMock()
    fake_module = MagicMock()
    fake_module.Slack = fake_slack_cls
    with patch.dict("sys.modules", {"slackweb": fake_module}):
        notifier.notify("hi")
    fake_slack_cls.assert_called_once_with(url="https://hooks.example.com/x")
    fake_slack_cls.return_value.notify.assert_called_once_with(text="hi")


def test_slack_notifier_swallows_send_failure():
    notifier = SlackNotifier(webhook_url="https://hooks.example.com/x")
    fake_module = MagicMock()
    fake_module.Slack.side_effect = RuntimeError("boom")
    with patch.dict("sys.modules", {"slackweb": fake_module}):
        notifier.notify("hi")  # must not raise
