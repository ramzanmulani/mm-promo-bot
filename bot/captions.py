"""Caption builder.

Instagram is Story-only here and Meta gives stories no caption field at
all, so there is no instagram_caption(): that text lives inside the image
(see render.py's story variant). Facebook and LinkedIn carry the full
description.
"""
from __future__ import annotations


def _links_block(cfg: dict, post: dict, with_discord: bool = True) -> list[str]:
    L = cfg["links"]
    primary_key = post.get("cta_link", "site")
    lines = []
    if primary_key != "animbelt":
        lines.append(f"→ {post['cta']}: {L.get(primary_key, L['site'])}")
        lines.append(f"→ AnimBelt (Maya toolkit): {L['animbelt']}")
    else:
        lines.append(f"→ Buy AnimBelt: {L['animbelt']}")
        lines.append(f"→ Free mentorship demo: {L['mentorship']}")
    lines.append(f"→ Everything else: {L['site']}")
    if with_discord:
        lines.append(f"→ Free animator Discord: {L['discord']}")
    return lines


def _body(post: dict, cfg: dict, tags: list[str],
          with_discord: bool = True) -> str:
    parts = [post["caption_hook"].strip(), "",
             post["caption_body"].strip(), "",
             *_links_block(cfg, post, with_discord)]
    if tags:
        parts += ["", " ".join("#" + t for t in tags)]
    return "\n".join(parts)


def linkedin_caption(post: dict, cfg: dict) -> str:
    """LinkedIn: few hashtags, same substance."""
    return _body(post, cfg, post.get("hashtags", [])[:4])[:2900]


def facebook_caption(post: dict, cfg: dict) -> str:
    """Facebook Page: full description, a moderate hashtag set."""
    return _body(post, cfg, post.get("hashtags", [])[:6])[:5000]


def discord_caption(post: dict, cfg: dict) -> str:
    """Discord: no hashtags (noise there), no "join our Discord" link
    (they are already in it), and Discord caps a message at 2000 chars."""
    return _body(post, cfg, [], with_discord=False)[:1850]


def instagram_caption(post: dict, cfg: dict) -> str:
    """Only used if an Instagram FEED post is ever re-enabled."""
    return _body(post, cfg, post.get("hashtags", []))[:2180]
