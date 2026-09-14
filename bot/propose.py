"""Step 1 of 2: decide, render, and send the post out for review.

Runs daily. The 3-day cadence is enforced here from state, not from cron,
so a skipped or delayed Actions run cannot silently shift the schedule
or fire twice.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import state
from .captions import discord_caption, facebook_caption, linkedin_caption
from .config import (OUT_DIR, PUBLIC_IMG_DIR, load_config, load_posts,
                     public_base_url)
from .discord import make_notifier
from .render import render

IST = timezone(timedelta(hours=5, minutes=30))


def _due(cfg: dict, hist: dict, force: bool) -> tuple[bool, str]:
    if force:
        return True, "forced"
    last = hist.get("last_posted_at")
    if not last:
        return True, "no previous post"
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True, "unreadable last_posted_at"
    age = datetime.now(timezone.utc) - last_dt
    need = timedelta(days=cfg["schedule"]["interval_days"])
    if age >= need:
        return True, f"last post was {age.days}d {age.seconds // 3600}h ago"
    left = need - age
    return False, f"next post in {left.days}d {left.seconds // 3600}h"


def _pick(cfg: dict, deck: dict, hist: dict) -> tuple[str, dict]:
    rotation = [t for t in cfg["tracks"]["rotation"] if deck.get(t)]
    if not rotation:
        raise RuntimeError("No usable tracks: check config.yaml tracks.rotation "
                           "against content/posts.yaml")
    track = rotation[hist["rotation_index"] % len(rotation)]
    posts = deck[track]
    idx = hist["track_cursor"].get(track, 0) % len(posts)
    return track, posts[idx]


def _advance(hist: dict, cfg: dict, deck: dict, track: str) -> None:
    rotation = [t for t in cfg["tracks"]["rotation"] if deck.get(t)]
    hist["rotation_index"] = (hist["rotation_index"] + 1) % max(len(rotation), 1)
    hist["track_cursor"][track] = (hist["track_cursor"].get(track, 0) + 1) % len(deck[track])
    state.write_history(hist)


def _prune_public_images(cfg: dict, keep: int = 20) -> None:
    """Old post images would stay public forever otherwise, and the repo
    would grow by ~1.5 MB per post. Keep the most recent `keep` files."""
    pngs = sorted(PUBLIC_IMG_DIR.glob("*.png"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for old in pngs[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def active_platforms(cfg: dict) -> list[str]:
    return [p for p in ("instagram_story", "facebook", "linkedin", "discord")
            if cfg["platforms"].get(p)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore the 3-day gate")
    ap.add_argument("--dry-run", action="store_true",
                    help="render + Discord preview only; never posts publicly")
    ap.add_argument("--post-id", default="",
                    help="render this specific post id instead of the next one")
    args = ap.parse_args(argv)

    cfg, deck = load_config(), load_posts()
    hist = state.read_history()

    if state.read_pending():
        print("[propose] a post is already in the queue - nothing to do.")
        return 0

    due, why = _due(cfg, hist, args.force)
    print(f"[propose] due={due} ({why})")
    if not due:
        return 0

    if args.post_id:
        track, post = next(((t, p) for t, ps in deck.items() for p in ps
                            if p["id"] == args.post_id), (None, None))
        if not post:
            print(f"[propose] no post with id {args.post_id}")
            return 1
    else:
        track, post = _pick(cfg, deck, hist)

    platforms = active_platforms(cfg)
    if not platforms:
        print("[propose] every platform is disabled in config.yaml")
        return 1
    formats = sorted({cfg["image_for"][p] for p in platforms})

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    slug = f"{stamp}-{post['id']}"
    pngs = render(post, cfg, formats, slug, out_dir=OUT_DIR)

    # Instagram and Facebook both FETCH the image by URL - neither accepts an
    # upload - so the rendered PNG goes into docs/ for GitHub Pages to serve.
    PUBLIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
    _prune_public_images(cfg)
    public = {}
    for fmt, path in pngs.items():
        dest = PUBLIC_IMG_DIR / path.name
        shutil.copyfile(path, dest)
        public[fmt] = f"{public_base_url()}/img/{dest.name}"

    caps = {"linkedin": linkedin_caption(post, cfg),
            "facebook": facebook_caption(post, cfg),
            "discord": discord_caption(post, cfg)}

    dc = make_notifier()
    hours = cfg["schedule"]["auto_approve_hours"]
    ist_now = datetime.now(IST).strftime("%d %b, %I:%M %p")

    where = ", ".join({"instagram_story": "Instagram Story",
                       "facebook": "Facebook Page",
                       "linkedin": "LinkedIn",
                       "discord": "Discord"}[p] for p in platforms)
    head = (f"**MM Promo Bot — post ready**\n"
            f"`{post['id']}` · track **{track}** · {ist_now} IST\n"
            f"Jayega: **{where}**\n")
    if args.dry_run:
        head += "\n**DRY RUN — kuch bhi post nahi hoga.**\n"
    elif dc.can_approve:
        head += (f"\nReact **✅ post karne ke liye**, **❌ skip karne ke liye**.\n"
                 f"{hours}h me react nahi kiya to apne aap chala jayega.\n")
    else:
        head += (f"\n**{hours}h baad apne aap post ho jayega.**\n"
                 f"Rokna ho to GitHub → Actions → *Cancel pending post* → "
                 f"Run workflow.\n")
    head += ("\n_Instagram Story me caption nahi ja sakti (Meta API deta hi "
             "nahi) — isliye saara text image me hai._\n")
    head += f"\n**Facebook + LinkedIn caption:**\n```\n{caps['linkedin'][:1100]}\n```"

    msg = dc.post(head, files=list(pngs.values()))
    if dc.can_approve:
        dc.seed_reactions(msg["id"])

    state.write_pending({
        "post_id": post["id"],
        "track": track,
        "slug": slug,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "discord_message_id": msg.get("id", ""),
        "approval_mode": dc.mode,
        "dry_run": bool(args.dry_run),
        "attempts": 0,
        "platforms": platforms,
        "alt_text": f"{post['eyebrow']} — {post['headline'].replace(chr(10), ' ')}",
        "images": {k: str(v) for k, v in pngs.items()},
        "image_urls": public,
        "captions": caps,
        "done": [],
        "results": {},
    })
    _advance(hist, cfg, deck, track)
    print(f"[propose] queued {post['id']} ({dc.mode} mode) for {platforms}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        try:
            make_notifier().post("⚠️ **MM Promo Bot: propose step failed**\n```\n"
                                 + traceback.format_exc()[-1400:] + "\n```")
        except Exception:
            pass
        sys.exit(1)
