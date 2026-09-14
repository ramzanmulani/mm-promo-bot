"""Config + secrets loading. Single source of truth for both workflows."""
from __future__ import annotations

import os
import pathlib
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
PUBLIC_IMG_DIR = ROOT / "docs" / "img"
STATE_DIR = ROOT / "state"


def _load_dotenv() -> None:
    """Local convenience only. In CI everything comes from the environment."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_posts() -> dict:
    with open(ROOT / "content" / "posts.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class MissingSecret(RuntimeError):
    pass


def secret(name: str, required: bool = True, default: str = "") -> str:
    val = (os.environ.get(name) or "").strip()
    if not val and required:
        raise MissingSecret(
            f"Secret {name} is missing. Add it in GitHub > Settings > "
            f"Secrets and variables > Actions (or in your local .env)."
        )
    return val or default


def public_base_url() -> str:
    return secret("PUBLIC_BASE_URL").rstrip("/")
