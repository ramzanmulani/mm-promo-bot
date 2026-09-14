"""Instagram publishing via the Meta Graph API (Page-token route).

Instagram will NOT accept a file upload for feed images - it fetches a
public URL itself. That is why the rendered PNG is committed to docs/ and
served by GitHub Pages, and why we verify the URL is actually reachable
before creating the container (otherwise Meta returns an opaque error).
"""
from __future__ import annotations

import time
import requests

GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 60


class InstagramError(RuntimeError):
    pass


def verify_public_image(url: str) -> None:
    """Fail loudly and early if GitHub Pages has not published the image."""
    last = ""
    for attempt in range(6):                       # Pages deploy lag
        try:
            r = requests.get(url, timeout=30, stream=True,
                             headers={"Range": "bytes=0-1023"})
            ctype = r.headers.get("Content-Type", "")
            if r.status_code in (200, 206) and ctype.startswith("image/"):
                return
            last = f"HTTP {r.status_code}, content-type {ctype!r}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(20)
    raise InstagramError(
        f"Image URL not publicly reachable: {url} ({last}).\n"
        "Check: GitHub repo is public AND Settings > Pages is set to "
        "'Deploy from a branch: main / docs'."
    )


def _post(path: str, params: dict) -> dict:
    r = requests.post(f"{GRAPH}/{path}", data=params, timeout=TIMEOUT)
    data = r.json() if r.text else {}
    if r.status_code >= 400 or "error" in data:
        raise InstagramError(f"{path} -> {r.status_code} {data}")
    return data


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=TIMEOUT)
    data = r.json() if r.text else {}
    if r.status_code >= 400 or "error" in data:
        raise InstagramError(f"{path} -> {r.status_code} {data}")
    return data


def publish_story(ig_user_id: str, token: str, image_url: str) -> str:
    """Publish a 9:16 image as an Instagram Story.

    Stories take NO caption and the API exposes no link/text stickers, so
    everything the viewer needs is burned into the image by render.py.
    Passing a caption here is silently ignored by Meta - we do not send one,
    so nobody later wonders why it never appears.
    """
    return _publish(ig_user_id, token, image_url, caption=None,
                    media_type="STORIES")


def publish_image(ig_user_id: str, token: str, image_url: str,
                  caption: str) -> str:
    """Feed post. Kept for when a normal grid post is wanted again."""
    return _publish(ig_user_id, token, image_url, caption=caption)


def _publish(ig_user_id: str, token: str, image_url: str,
             caption: str | None = None, media_type: str = "") -> str:
    """Create container -> wait until FINISHED -> publish. Returns media id."""
    verify_public_image(image_url)

    params = {"image_url": image_url, "access_token": token}
    if caption is not None:
        params["caption"] = caption
    if media_type:
        params["media_type"] = media_type
    container = _post(f"{ig_user_id}/media", params)
    cid = container["id"]

    # Containers are async. Publishing an IN_PROGRESS container fails.
    for _ in range(30):
        status = _get(cid, {"fields": "status_code,status",
                            "access_token": token})
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Container {cid} -> {status}")
        time.sleep(5)
    else:
        raise InstagramError(f"Container {cid} never finished processing")

    published = _post(f"{ig_user_id}/media_publish", {
        "creation_id": cid,
        "access_token": token,
    })
    return published["id"]


def permalink(media_id: str, token: str) -> str:
    try:
        return _get(media_id, {"fields": "permalink",
                               "access_token": token}).get("permalink", "")
    except InstagramError:
        return ""
