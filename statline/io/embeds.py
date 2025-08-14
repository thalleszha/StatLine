from __future__ import annotations

import hikari

# Color constants (in decimal)
EMBED_COLORS = {
    "ok": 0x2ECC71,     # green
    "warn": 0xF1C40F,   # yellow
    "error": 0xE74C3C,  # red
}

def _make_embed(color_key: str, title: str, description: str = "") -> hikari.Embed:
    """
    Internal helper to create an embed with the given style.
    """
    return hikari.Embed(
        title=title,
        description=description,
        color=EMBED_COLORS[color_key],
    )

def ok_embed(title: str, description: str = "") -> hikari.Embed:
    return _make_embed("ok", title, description)

def warn_embed(title: str, description: str = "") -> hikari.Embed:
    return _make_embed("warn", title, description)

def err_embed(title: str, description: str = "") -> hikari.Embed:
    return _make_embed("error", title, description)
