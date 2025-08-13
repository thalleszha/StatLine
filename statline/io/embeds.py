import hikari

def ok_embed(title: str, description: str = "") -> hikari.Embed:
    return hikari.Embed(title=title, description=description, color=0x2ecc71)

def warn_embed(title: str, description: str = "") -> hikari.Embed:
    return hikari.Embed(title=title, description=description, color=0xf1c40f)

def err_embed(title: str, description: str = "") -> hikari.Embed:
    return hikari.Embed(title=title, description=description, color=0xe74c3c)
