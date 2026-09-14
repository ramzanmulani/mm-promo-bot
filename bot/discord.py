"""Discord notifications + (optional) approval.

Two modes, picked automatically by which secret exists:

  BOT MODE      DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID
                Posts the preview, seeds a checkmark and a cross, and reads
                back which one you pressed. Full veto.

  WEBHOOK MODE  DISCORD_WEBHOOK_URL
                Posts the preview only. A webhook has no token, so Discord
                gives it no way to READ anything - reactions included. The
                post therefore goes out automatically once the review
                window passes; the "Cancel pending post" workflow is the
                veto.

Adding DISCORD_BOT_TOKEN later upgrades a webhook setup to full approval
with no code change.
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Iterable

import requests

API = "https://discord.com/api/v10"
APPROVE = "✅"
REJECT = "❌"
TIMEOUT = 30


class DiscordError(RuntimeError):
    pass


def _send_multipart(url: str, payload: dict, files: list[pathlib.Path],
                    headers: dict | None = None) -> requests.Response:
    multipart = {"payload_json": (None, json.dumps(payload), "application/json")}
    handles = []
    try:
        for i, f in enumerate(files):
            fh = open(f, "rb")
            handles.append(fh)
            multipart[f"files[{i}]"] = (f.name, fh, "image/png")
        return requests.post(url, files=multipart, headers=headers or {},
                             timeout=TIMEOUT)
    finally:
        for fh in handles:
            fh.close()


class WebhookNotifier:
    mode = "webhook"
    can_approve = False

    def __init__(self, url: str):
        self.url = url.split("?")[0] + "?wait=true"

    def _send(self, content: str, files: Iterable[pathlib.Path] = ()) -> dict:
        files = list(files)
        payload = {"content": content[:1990],
                   "allowed_mentions": {"parse": []}}
        if files:
            r = _send_multipart(self.url, payload, files)
        else:
            r = requests.post(self.url, json=payload, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise DiscordError(f"webhook -> {r.status_code} {r.text[:300]}")
        return r.json() if r.text else {"id": "webhook"}

    def post(self, content, files=()):
        return self._send(content, files)

    def seed_reactions(self, message_id):        # nothing to seed
        return

    def read_decision(self, message_id):          # nothing to read
        return "pending"

    def reply(self, message_id, content):
        self._send(content)


class BotNotifier:
    mode = "bot"
    can_approve = True

    def __init__(self, token: str, channel_id: str):
        self.channel_id = str(channel_id)
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bot {token}",
            "User-Agent": "MMPromoBot (https://mythicalmotions.com, 1.0)",
        })

    def _req(self, method: str, path: str, **kw):
        for _ in range(5):
            r = self.s.request(method, API + path, timeout=TIMEOUT, **kw)
            if r.status_code == 429:
                time.sleep(min(float(r.headers.get("Retry-After", 2)) + 0.5, 15))
                continue
            if r.status_code >= 400:
                raise DiscordError(f"{method} {path} -> {r.status_code} {r.text[:400]}")
            return r.json() if r.text else {}
        raise DiscordError(f"{method} {path} -> still rate limited after retries")

    def post(self, content: str, files: Iterable[pathlib.Path] = ()) -> dict:
        files = list(files)
        payload = {"content": content[:1990], "allowed_mentions": {"parse": []}}
        if not files:
            return self._req("POST", f"/channels/{self.channel_id}/messages",
                             json=payload)
        r = _send_multipart(API + f"/channels/{self.channel_id}/messages",
                            payload, files, dict(self.s.headers))
        if r.status_code >= 400:
            raise DiscordError(f"post -> {r.status_code} {r.text[:400]}")
        return r.json()

    def seed_reactions(self, message_id: str) -> None:
        for emoji in (APPROVE, REJECT):
            self._req("PUT", f"/channels/{self.channel_id}/messages/"
                             f"{message_id}/reactions/"
                             f"{requests.utils.quote(emoji)}/@me")
            time.sleep(0.35)

    def read_decision(self, message_id: str) -> str:
        """'approved' | 'rejected' | 'pending'.

        The bot's own seeded reaction counts as 1, so a human press makes it
        2 or more. Rejection wins over approval.
        """
        try:
            msg = self._req("GET", f"/channels/{self.channel_id}/messages/{message_id}")
        except DiscordError as exc:
            if "404" in str(exc):          # message deleted = treat as skip
                return "rejected"
            raise
        counts = {r["emoji"].get("name"): r.get("count", 0)
                  for r in msg.get("reactions", []) or []}
        if counts.get(REJECT, 0) >= 2:
            return "rejected"
        if counts.get(APPROVE, 0) >= 2:
            return "approved"
        return "pending"

    def reply(self, message_id: str, content: str) -> None:
        self._req("POST", f"/channels/{self.channel_id}/messages", json={
            "content": content[:1990],
            "message_reference": {"message_id": str(message_id),
                                  "fail_if_not_exists": False},
            "allowed_mentions": {"parse": []},
        })


def post_to_channel(webhook_url: str, content: str,
                    files: Iterable[pathlib.Path] = ()) -> str:
    """Post the promo itself into a community channel. Deliberately a
    separate webhook from the approval one - same URL would show members
    the review message."""
    hook = WebhookNotifier(webhook_url)
    msg = hook.post(content, files)
    cid = msg.get("channel_id", "")
    mid = msg.get("id", "")
    return (f"https://discord.com/channels/@me/{cid}/{mid}"
            if cid and mid else "posted")


def make_notifier():
    """Bot if its secrets are present, else webhook. Never both."""
    from .config import secret
    token = secret("DISCORD_BOT_TOKEN", required=False)
    channel = secret("DISCORD_CHANNEL_ID", required=False)
    if token and channel:
        return BotNotifier(token, channel)
    hook = secret("DISCORD_WEBHOOK_URL", required=False)
    if hook:
        return WebhookNotifier(hook)
    raise DiscordError(
        "Discord ka koi secret nahi mila. Ya to DISCORD_WEBHOOK_URL set karo, "
        "ya DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID.")
