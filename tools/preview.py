"""Local preview: render every post in the deck without posting anything.

    python tools/preview.py            # all posts, both formats
    python tools/preview.py belt-01    # one post
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bot.config import load_config, load_posts, ROOT
from bot.render import render

def main():
    cfg, deck = load_config(), load_posts()
    want = sys.argv[1] if len(sys.argv) > 1 else None
    out = ROOT / "out" / "preview"
    n = 0
    for track, posts in deck.items():
        for p in posts:
            if want and p["id"] != want:
                continue
            render(p, cfg, ["story", "square"], p["id"], out_dir=out)
            n += 1
    print(f"\n{n} post(s) rendered to {out}")

if __name__ == "__main__":
    main()
