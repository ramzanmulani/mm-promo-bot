"""Step 2 of 2: check the decision and publish.

Runs hourly. Safe to run at any time: it does nothing unless something is
queued, and it never posts the same platform twice for the same item.
"""
from __future__ import annotations

import pathlib
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import state
from .config import load_config, secret
from .discord import make_notifier, post_to_channel
from .facebook import publish_photo as fb_publish, resolve_page_token
from .instagram import permalink, publish_story as ig_story
from .linkedin import LinkedIn, post_url

IST = timezone(timedelta(hours=5, minutes=30))
MAX_ATTEMPTS = 3

LABEL = {"instagram_story": "Instagram Story",
         "facebook": "Facebook",
         "linkedin": "LinkedIn",
         "discord": "Discord"}


def _age_hours(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc)
                - datetime.fromisoformat(iso)).total_seconds() / 3600
    except ValueError:
        return 999.0


def _in_ist_window(cfg: dict) -> bool:
    lo, hi = cfg["schedule"]["ist_publish_window"]
    return lo <= datetime.now(IST).hour < hi


def _warn_linkedin_token(cfg: dict, dc) -> None:
    issued = secret("LINKEDIN_TOKEN_ISSUED", required=False)
    if not issued:
        return
    try:
        issued_dt = datetime.fromisoformat(issued).replace(tzinfo=timezone.utc)
    except ValueError:
        return
    life = cfg["linkedin"]["token_lifetime_days"]
    left = life - (datetime.now(timezone.utc) - issued_dt).days
    if left <= cfg["linkedin"]["token_warn_days_before_expiry"]:
        dc.post(f"🔑 **LinkedIn token ~{left} din me expire ho raha hai.**\n"
                f"`python tools/linkedin_auth.py` chala ke "
                f"`LINKEDIN_ACCESS_TOKEN` aur `LINKEDIN_TOKEN_ISSUED` "
                f"update kar dena.")


def _image_url(pending: dict, cfg: dict, platform: str) -> str:
    return pending["image_urls"][cfg["image_for"][platform]]


def _image_path(pending: dict, cfg: dict, platform: str) -> pathlib.Path:
    return pathlib.Path(pending["images"][cfg["image_for"][platform]])


def main() -> int:
    cfg = load_config()
    pending = state.read_pending()
    if not pending:
        print("[publish] nothing queued.")
        return 0

    dc = make_notifier()
    mid = pending.get("discord_message_id", "")
    decision = dc.read_decision(mid) if dc.can_approve else "pending"
    age = _age_hours(pending["created_at"])
    limit = cfg["schedule"]["auto_approve_hours"]

    if decision == "rejected":
        dc.reply(mid, "❌ Skip kar diya. Ye post nahi jayega. "
                      "Agla post schedule pe hi aayega.")
        state.clear_pending()
        print("[publish] rejected by reaction.")
        return 0

    if decision == "pending":
        if age < limit:
            print(f"[publish] waiting ({age:.1f}h of {limit}h).")
            return 0
        if not _in_ist_window(cfg):
            print("[publish] due, but outside the allowed IST window - holding.")
            return 0
        approved_by = (f"auto ({limit}h window)" if not dc.can_approve
                       else f"auto (no reaction in {limit}h)")
    else:
        approved_by = "✅ reaction"

    if pending.get("dry_run"):
        dc.reply(mid, f"🧪 Dry run poora hua — approved by {approved_by}, "
                      f"par kahin kuch post nahi kiya gaya.")
        state.clear_pending()
        return 0

    pending["attempts"] = pending.get("attempts", 0) + 1
    state.write_pending(pending)
    if pending["attempts"] > MAX_ATTEMPTS:
        dc.reply(mid, f"⚠️ {MAX_ATTEMPTS} koshishon ke baad chhod diya. "
                      f"Upar ka error theek karke workflow manually chala dena.")
        state.clear_pending()
        return 1

    wanted = [p for p in pending.get("platforms", [])
              if cfg["platforms"].get(p)]
    done = set(pending.get("done", []))
    results = dict(pending.get("results", {}))
    errors: list[str] = []

    for platform in wanted:
        if platform in done:
            continue
        try:
            if platform == "instagram_story":
                # Works with a Page token or a long-lived user token; we
                # normalise to the Page token so both paths behave the same.
                token = resolve_page_token(
                    secret("FB_PAGE_ID", required=False,
                           default=str(cfg["facebook"]["page_id"])),
                    secret("META_PAGE_TOKEN"))
                mediaid = ig_story(secret("IG_USER_ID"), token,
                                   _image_url(pending, cfg, platform))
                results[platform] = permalink(mediaid, token) or f"story {mediaid}"

            elif platform == "facebook":
                _, link = fb_publish(
                    secret("FB_PAGE_ID", required=False,
                           default=str(cfg["facebook"]["page_id"])),
                    secret("META_PAGE_TOKEN"),
                    _image_url(pending, cfg, platform),
                    pending["captions"]["facebook"])
                results[platform] = link

            elif platform == "discord":
                hook = secret("DISCORD_POST_WEBHOOK_URL", required=False)
                if not hook:
                    raise RuntimeError(
                        "DISCORD_POST_WEBHOOK_URL set nahi hai. Apne community "
                        "channel ka webhook banao (approval wale channel se ALAG) "
                        "aur `gh secret set DISCORD_POST_WEBHOOK_URL` se daal do. "
                        "Ya config.yaml me platforms.discord: false kar do.")
                results[platform] = post_to_channel(
                    hook, pending["captions"]["discord"],
                    [_image_path(pending, cfg, platform)])

            elif platform == "linkedin":
                li = LinkedIn(secret("LINKEDIN_ACCESS_TOKEN"),
                              secret("LINKEDIN_PERSON_URN"),
                              cfg["linkedin"]["api_version"])
                urn = li.publish_image(_image_path(pending, cfg, platform),
                                       pending["captions"]["linkedin"],
                                       pending.get("alt_text", "Mythical Motions"))
                results[platform] = post_url(urn) or urn

            done.add(platform)
            print(f"[publish] {platform} ok -> {results.get(platform)}")
        except Exception as exc:
            errors.append(f"{LABEL[platform]}: {exc}")

    # Persist partial progress FIRST, so a retry can never double-post.
    pending["done"] = sorted(done)
    pending["results"] = results
    state.write_pending(pending)

    if errors and not set(wanted).issubset(done):
        dc.reply(mid, f"⚠️ **Poora post nahi hua** (koshish "
                      f"{pending['attempts']}/{MAX_ATTEMPTS}, {approved_by})\n"
                      + "\n".join(f"• {e}" for e in errors)[:1500]
                      + "\nAgli hourly run pe sirf jo bacha hai wo retry hoga.")
        print("[publish] errors:", errors)
        return 1

    lines = [f"• {LABEL[k]}: {v}" for k, v in results.items() if v]
    dc.reply(mid, f"✅ **Post ho gaya** ({approved_by})\n" + "\n".join(lines))
    state.record_posted({"post_id": pending["post_id"],
                         "track": pending["track"],
                         "results": results,
                         "approved_by": approved_by})
    state.clear_pending()
    _warn_linkedin_token(cfg, dc)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        try:
            make_notifier().post("⚠️ **MM Promo Bot: publish step failed**\n```\n"
                                 + traceback.format_exc()[-1400:] + "\n```")
        except Exception:
            pass
        sys.exit(1)
