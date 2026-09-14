"""HTML -> PNG renderer (Playwright/Chromium).

One browser, one page per format. Fonts are awaited explicitly so a slow
Google Fonts response can never produce a fallback-font screenshot silently.
"""
from __future__ import annotations

import base64
import pathlib
from typing import Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT, OUT_DIR

TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates"
FONT_DIR = pathlib.Path(__file__).resolve().parent / "fonts"
LOGO = ROOT / "assets" / "logo.png"


def _logo_data_uri() -> str:
    """Optional: drop your gold creature-head PNG at assets/logo.png."""
    if not LOGO.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()


def _font_uri(name: str) -> str:
    """Fonts are bundled, never fetched. A network hiccup must not be able
    to silently change the typeface of a published post."""
    path = FONT_DIR / f"{name}.woff2"
    if not path.exists():
        raise FileNotFoundError(f"Bundled font missing: {path}")
    return "data:font/woff2;base64," + base64.b64encode(path.read_bytes()).decode()


def _short_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")


def build_html(post: dict, brand: dict, variant: str = "card",
               cta_url: str = "") -> str:
    env = Environment(
        loader=FileSystemLoader(str(TPL_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    tpl = env.get_template("card.html.j2")
    return tpl.render(
        post=post,
        b=brand,
        variant=variant,
        cta_url_short=_short_url(cta_url) if variant == "story" else "",
        logo_data_uri=_logo_data_uri(),
        font_outfit=_font_uri("Outfit"),
        font_inter=_font_uri("Inter"),
    )


def render(post: dict, cfg: dict, formats: Iterable[str], slug: str,
           out_dir: pathlib.Path | None = None) -> dict:
    """Render `post` into one PNG per format. Returns {format: Path}."""
    from playwright.sync_api import sync_playwright

    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cta_url = cfg["links"].get(post.get("cta_link", "site"), cfg["links"]["site"])

    results: dict[str, pathlib.Path] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--font-render-hinting=none",
                                           "--force-color-profile=srgb"])
        try:
            for fmt in formats:
                dims = cfg["render"][fmt]
                variant = dims.get("variant", "card")
                html_path = out_dir / f"{slug}-{fmt}.html"
                html_path.write_text(
                    build_html(post, cfg["brand"], variant, cta_url),
                    encoding="utf-8")
                page = browser.new_page(
                    viewport={"width": dims["width"], "height": dims["height"]},
                    device_scale_factor=cfg["render"].get("scale", 1),
                )
                page.goto(html_path.as_uri(), wait_until="load")
                # Fonts are inline data: URIs, so this resolves immediately -
                # but assert it rather than assume it.
                page.wait_for_function("document.fonts.status === 'loaded'",
                                       timeout=15000)
                if not page.evaluate('document.fonts.check("800 100px Outfit")'):
                    raise RuntimeError("Outfit font failed to load - refusing "
                                       "to render an off-brand image.")
                fit = page.evaluate("window.__fit()")
                if fit and fit.get("overflow", 0) > 2:
                    print(f"[render] WARNING {slug}/{fmt}: content still "
                          f"overflows by {fit['overflow']}px - shorten the copy.")
                png = out_dir / f"{slug}-{fmt}.png"
                page.screenshot(path=str(png), type="png")
                page.close()
                results[fmt] = png
                print(f"[render] {png.name}  {dims['width']}x{dims['height']}"
                      f"  headline={fit.get('headlineVw') if fit else '?'}vw")
        finally:
            browser.close()
    return results
