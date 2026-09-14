"""LinkedIn personal-feed publishing (w_member_social).

Primary path  : versioned Images API + /rest/posts  (current, supported)
Fallback path : /v2/assets registerUpload + /v2/ugcPosts  (legacy)

The fallback exists because which path an app may use depends on when the
app was created and which products are enabled - and finding out costs a
failed post. So we try the modern one and drop back automatically on
403 / 426 / 404 rather than losing the post.
"""
from __future__ import annotations

import pathlib
import re
import requests

BASE = "https://api.linkedin.com"
TIMEOUT = 90

# /rest/posts commentary uses LinkedIn's "Little Text" format, where these
# characters are reserved and MUST be backslash-escaped or the call 422s.
_RESERVED = r"\(\)\[\]\{\}<>@|~_*#"
_ESCAPE_RE = re.compile(f"([{_RESERVED}])")


class LinkedInError(RuntimeError):
    pass


def escape_commentary(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", text)


class LinkedIn:
    def __init__(self, token: str, person_urn: str, api_version: str = "202506"):
        self.token = token
        self.author = (person_urn if person_urn.startswith("urn:li:")
                       else f"urn:li:person:{person_urn}")
        self.version = api_version

    def _h(self, versioned: bool, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.token}",
             "X-Restli-Protocol-Version": "2.0.0"}
        if versioned:
            h["LinkedIn-Version"] = self.version
        h.update(extra or {})
        return h

    # ---------------- modern path ------------------------------------
    def _post_versioned(self, png: pathlib.Path, text: str, alt: str) -> str:
        r = requests.post(
            f"{BASE}/rest/images?action=initializeUpload",
            headers=self._h(True, {"Content-Type": "application/json"}),
            json={"initializeUploadRequest": {"owner": self.author}},
            timeout=TIMEOUT)
        if r.status_code in (403, 404, 426):
            raise _Fallback(f"initializeUpload -> {r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            raise LinkedInError(f"initializeUpload -> {r.status_code} {r.text[:400]}")
        val = r.json()["value"]

        up = requests.put(val["uploadUrl"], data=png.read_bytes(),
                          headers={"Authorization": f"Bearer {self.token}"},
                          timeout=TIMEOUT)
        if up.status_code >= 400:
            raise LinkedInError(f"image upload -> {up.status_code} {up.text[:300]}")

        body = {
            "author": self.author,
            "commentary": escape_commentary(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED",
                             "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "content": {"media": {"id": val["image"], "altText": alt[:200]}},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        pr = requests.post(f"{BASE}/rest/posts",
                           headers=self._h(True, {"Content-Type": "application/json"}),
                           json=body, timeout=TIMEOUT)
        if pr.status_code in (403, 404, 426):
            raise _Fallback(f"/rest/posts -> {pr.status_code} {pr.text[:200]}")
        if pr.status_code >= 400:
            raise LinkedInError(f"/rest/posts -> {pr.status_code} {pr.text[:500]}")
        return pr.headers.get("x-restli-id", "") or "posted"

    # ---------------- legacy path ------------------------------------
    def _post_legacy(self, png: pathlib.Path, text: str, alt: str) -> str:
        reg = requests.post(
            f"{BASE}/v2/assets?action=registerUpload",
            headers=self._h(False, {"Content-Type": "application/json"}),
            json={"registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.author,
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"}]}},
            timeout=TIMEOUT)
        if reg.status_code >= 400:
            raise LinkedInError(f"registerUpload -> {reg.status_code} {reg.text[:400]}")
        v = reg.json()["value"]
        asset = v["asset"]
        url = (v["uploadMechanism"]
               ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
               ["uploadUrl"])

        up = requests.put(url, data=png.read_bytes(),
                          headers={"Authorization": f"Bearer {self.token}"},
                          timeout=TIMEOUT)
        if up.status_code >= 400:
            raise LinkedInError(f"legacy upload -> {up.status_code} {up.text[:300]}")

        body = {
            "author": self.author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": [{"status": "READY",
                           "media": asset,
                           "description": {"text": alt[:200]},
                           "title": {"text": "Mythical Motions"}}]}},
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        pr = requests.post(f"{BASE}/v2/ugcPosts",
                           headers=self._h(False, {"Content-Type": "application/json"}),
                           json=body, timeout=TIMEOUT)
        if pr.status_code >= 400:
            raise LinkedInError(f"ugcPosts -> {pr.status_code} {pr.text[:500]}")
        return pr.headers.get("x-restli-id", "") or pr.json().get("id", "posted")

    # ---------------- public -----------------------------------------
    def publish_image(self, png: pathlib.Path, text: str, alt: str) -> str:
        try:
            return self._post_versioned(png, text, alt)
        except _Fallback as why:
            print(f"[linkedin] versioned API unavailable ({why}); "
                  f"using legacy ugcPosts path")
            return self._post_legacy(png, text, alt)


class _Fallback(Exception):
    pass


def post_url(urn: str) -> str:
    if urn.startswith("urn:li:share:") or urn.startswith("urn:li:ugcPost:"):
        return f"https://www.linkedin.com/feed/update/{urn}/"
    return ""
