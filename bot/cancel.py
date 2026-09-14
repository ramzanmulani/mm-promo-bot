"""Drop whatever is queued. This is the veto when Discord is a webhook
(a webhook cannot read reactions, so there is nothing to react to).

Triggered by the "Cancel pending post" workflow.
"""
from __future__ import annotations

import sys

from . import state
from .discord import make_notifier


def main() -> int:
    pending = state.read_pending()
    if not pending:
        print("[cancel] nothing queued.")
        return 0
    state.clear_pending()
    print(f"[cancel] dropped {pending['post_id']}")
    try:
        make_notifier().post(
            f"🛑 **Cancel kar diya** — `{pending['post_id']}` post nahi hoga.\n"
            f"Agla post schedule pe hi aayega.")
    except Exception as exc:
        print(f"[cancel] discord notice failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
