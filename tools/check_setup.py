"""Pre-flight check. Run this BEFORE the first real post.

    python tools/check_setup.py

Verifies every secret, every API token and the public image URL, and tells
you exactly what to fix. It never posts anything.
"""
import sys, pathlib, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests
from bot.config import load_config, load_posts, secret, MissingSecret

OK, BAD = "  OK  ", " FAIL "
fails = []


def check(name, fn):
    try:
        detail = fn()
        print(f"[{OK}] {name}" + (f"  - {detail}" if detail else ""))
    except Exception as exc:
        print(f"[{BAD}] {name}\n         {exc}")
        fails.append(name)


def main():
    cfg, deck = load_config(), load_posts()
    print(f"\nDeck: {sum(len(v) for v in deck.values())} posts across "
          f"{len(deck)} tracks\n")

    def discord():
        t = secret("DISCORD_BOT_TOKEN", required=False)
        ch = secret("DISCORD_CHANNEL_ID", required=False)
        if t and ch:
            h = {"Authorization": f"Bot {t}"}
            me = requests.get("https://discord.com/api/v10/users/@me",
                              headers=h, timeout=20)
            me.raise_for_status()
            c = requests.get(f"https://discord.com/api/v10/channels/{ch}",
                             headers=h, timeout=20)
            if c.status_code == 403:
                raise RuntimeError("Bot channel dekh nahi pa raha. Server me "
                                   "invite karo aur View Channel + Send Messages "
                                   "+ Attach Files + Add Reactions + Read "
                                   "Message History permissions do.")
            c.raise_for_status()
            return f"BOT mode - {me.json()['username']} -> #{c.json().get('name')}"
        hook = secret("DISCORD_WEBHOOK_URL")
        r = requests.get(hook.split("?")[0], timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"Webhook URL kaam nahi kar raha ({r.status_code}). "
                               f"Channel > Edit Channel > Integrations > Webhooks "
                               f"se naya URL copy karo.")
        d = r.json()
        return (f"WEBHOOK mode - #{d.get('name', '?')} "
                f"(approval nahi - {cfg['schedule']['auto_approve_hours']}h baad "
                f"auto post, Cancel workflow se rok sakte ho)")

    def pages():
        base = secret("PUBLIC_BASE_URL").rstrip("/")
        r = requests.get(base + "/", timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"{base}/ returned {r.status_code}. Enable "
                               "Settings > Pages > Deploy from a branch: "
                               "main / docs, and make the repo public.")
        return base

    def meta_ig():
        uid, tok = secret("IG_USER_ID"), secret("META_PAGE_TOKEN")
        r = requests.get(f"https://graph.facebook.com/v21.0/{uid}",
                         params={"fields": "username,followers_count",
                                 "access_token": tok}, timeout=30)
        d = r.json()
        if "error" in d:
            raise RuntimeError(d["error"].get("message", d))
        return f"@{d.get('username')} (story posting)"

    def meta_fb():
        pid = secret("FB_PAGE_ID", required=False,
                     default=str(cfg["facebook"]["page_id"]))
        tok = secret("META_PAGE_TOKEN")
        r = requests.get(f"https://graph.facebook.com/v21.0/{pid}",
                         params={"fields": "name,fan_count",
                                 "access_token": tok}, timeout=30)
        d = r.json()
        if "error" in d:
            raise RuntimeError(d["error"].get("message", d))
        perms = requests.get("https://graph.facebook.com/v21.0/debug_token",
                             params={"input_token": tok, "access_token": tok},
                             timeout=30).json()
        scopes = (perms.get("data") or {}).get("scopes", [])
        if scopes and "pages_manage_posts" not in scopes:
            raise RuntimeError("Token me pages_manage_posts nahi hai - Facebook "
                               "post nahi kar payega. Token dobara banao us "
                               "permission ke saath.")
        return f"Page \"{d.get('name')}\""

    def li():
        tok = secret("LINKEDIN_ACCESS_TOKEN")
        r = requests.get("https://api.linkedin.com/v2/userinfo",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("Token rejected/expired. Re-run tools/linkedin_auth.py")
        r.raise_for_status()
        urn = secret("LINKEDIN_PERSON_URN")
        if r.json()["sub"] not in urn:
            raise RuntimeError(f"LINKEDIN_PERSON_URN does not match this token. "
                               f"Should be urn:li:person:{r.json()['sub']}")
        issued = secret("LINKEDIN_TOKEN_ISSUED", required=False)
        left = ""
        if issued:
            days = (datetime.date.today()
                    - datetime.date.fromisoformat(issued)).days
            left = f", ~{cfg['linkedin']['token_lifetime_days'] - days} days left"
        return f"{r.json().get('name', '')}{left}"

    def discord_post():
        hook = secret("DISCORD_POST_WEBHOOK_URL")
        r = requests.get(hook.split("?")[0], timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"Webhook URL kaam nahi kar raha ({r.status_code}).")
        d = r.json()
        approve = secret("DISCORD_WEBHOOK_URL", required=False)
        if approve:
            a = requests.get(approve.split("?")[0], timeout=20)
            if a.status_code < 400 and a.json().get("channel_id") == d.get("channel_id"):
                raise RuntimeError(
                    "Ye wahi channel hai jahan approval preview jata hai. "
                    "Members ko 'post this?' wala message dikh jayega - "
                    "alag channel ka webhook banao.")
        return f"#{d.get('name', '?')}"

    check("Discord (approval / preview)", discord)
    if cfg["platforms"].get("discord"):
        check("Discord (community post)", discord_post)
    check("GitHub Pages (public image host)", pages)
    if cfg["platforms"].get("instagram_story"):
        check("Instagram Story", meta_ig)
    if cfg["platforms"].get("facebook"):
        check("Facebook Page", meta_fb)
    if cfg["platforms"].get("linkedin"):
        check("LinkedIn", li)

    print()
    if fails:
        print(f"{len(fails)} problem(s): " + ", ".join(fails))
        return 1
    print("All good. Run the Propose workflow with dry_run = true next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
