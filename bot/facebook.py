"""Facebook Page posting via the Graph API.

Uses the same Page token as Instagram (needs pages_manage_posts). The photo
is posted by URL, like Instagram - the Page is what actually owns the post,
so the full description rides along as the `message`.
"""
from __future__ import annotations

import requests

from .instagram import GRAPH, InstagramError, verify_public_image

TIMEOUT = 60


class FacebookError(RuntimeError):
    pass


def resolve_page_token(page_id: str, token: str) -> str:
    """Accept either a Page token or a long-lived USER token.

    Posting to a Page feed needs a PAGE token - a user token posts as the
    user or fails with (#200). But the same long-lived user token can mint
    the Page token, so ask for it and fall back to what we were given.
    /me/accounts is deliberately NOT used: once an IG account is linked to
    the Page it can come back empty, which is how this silently breaks.
    """
    try:
        r = requests.get(f"{GRAPH}/{page_id}",
                         params={"fields": "access_token", "access_token": token},
                         timeout=TIMEOUT)
        data = r.json() if r.text else {}
        page_token = data.get("access_token")
        if page_token:
            return page_token
    except requests.RequestException:
        pass
    return token          # already a Page token (or we will fail loudly later)


def publish_photo(page_id: str, token: str, image_url: str,
                  message: str) -> tuple[str, str]:
    """Post a photo with its caption to the Page feed.

    Returns (post_id, permalink).
    """
    try:
        verify_public_image(image_url)
    except InstagramError as exc:
        raise FacebookError(str(exc)) from exc

    r = requests.post(f"{GRAPH}/{page_id}/photos", data={
        "url": image_url,
        "message": message,
        "published": "true",
        "access_token": resolve_page_token(page_id, token),
    }, timeout=TIMEOUT)
    data = r.json() if r.text else {}
    if r.status_code >= 400 or "error" in data:
        raise FacebookError(f"{page_id}/photos -> {r.status_code} {data}")

    post_id = data.get("post_id") or data.get("id", "")
    return post_id, (f"https://www.facebook.com/{post_id}" if post_id else "")
