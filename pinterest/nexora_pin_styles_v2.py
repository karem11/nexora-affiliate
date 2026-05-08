"""
NEXORA Pinterest — Extra Pin Styles v2 (Magazine, Headline Hook, Splash Pop)
============================================================================

These three styles extend the original 4 (bold-dark, vibrant, minimalist, luxe).
They are designed for higher Pinterest engagement — using patterns proven to
convert on Pinterest:

* MAGAZINE   — premium editorial feel, like a curated magazine cover.
* HEADLINE   — text-on-top question/answer hook (Pinterest's #1 saves pattern).
* SPLASH     — colorful sticker-pop with multiple eye-catching badges.

All three reuse the helpers + colors from nexora_pinterest_generator.py and
share the brand elements (NEXORA wordmark, footer URL).
"""

from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw, ImageFilter

from nexora_pinterest_generator import (
    BG, BLUE, BLUE_DARK, CATEGORIES, GREEN, GOLD, GOLD_DARK, INK,
    INK_SOFT, IVORY, LOGO_PATH, MUTED, ORANGE, ORANGE_DARK,
    PIN_H, PIN_W, RED, SURFACE, SURFACE_2, TEXT, WHITE,
    clean_for_pin, fetch_image, fit_image, rounded_rect,
    shorten_title, text_size, wrap_text,
)


# ─── HOT-BADGE OVERLAY (used by ALL styles) ────────────────────────────────────

def _draw_star_burst(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int,
                     fill, outline=None):
    """Draw a 12-point star burst shape (Pinterest-style 'NEW!' burst)."""
    import math as _m
    pts = []
    for i in range(24):
        ang = (i * (360 / 24)) - 90
        r = radius if i % 2 == 0 else radius * 0.72
        x = cx + r * _m.cos(_m.radians(ang))
        y = cy + r * _m.sin(_m.radians(ang))
        pts.append((x, y))
    draw.polygon(pts, fill=fill, outline=outline)


def overlay_hot_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, F,
                      product: dict, pos: str = "top-right") -> None:
    """If product["_is_hot"] is True, paint a star-burst HOT badge.
    pos: one of 'top-right', 'top-left', 'top-center', or (x, y) tuple.
    """
    if not product.get("_is_hot"):
        return
    label = product.get("_hot_label", "TOP\nPICK")
    if "\n" not in label:
        words = label.split()
        if len(words) == 2:
            label = "\n".join(words)
    # Star burst position
    R = 78
    if pos == "top-left":
        cx, cy = 100, 100
    elif pos == "top-center":
        cx, cy = PIN_W // 2, 100
    elif isinstance(pos, tuple):
        cx, cy = pos
    else:  # top-right
        cx, cy = PIN_W - 100, 100

    # Soft glow behind the burst
    glow = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((cx - R - 20, cy - R - 20, cx + R + 20, cy + R + 20),
               fill=(255, 200, 0, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(20))
    canvas.alpha_composite(glow)

    # Star burst (yellow on black border)
    _draw_star_burst(draw, cx, cy, R + 4, fill=(20, 20, 20, 255))
    _draw_star_burst(draw, cx, cy, R, fill=(255, 200, 0, 255))

    # Centered 2-line label
    tf = F("extrabold", 22)
    lines = label.split("\n")
    total_h = sum(text_size(draw, ln, tf)[1] for ln in lines) + (len(lines) - 1) * 2
    ty = cy - total_h // 2
    for ln in lines:
        lw, lh = text_size(draw, ln, tf)
        draw.text((cx - lw // 2, ty), ln, font=tf, fill=(40, 20, 0))
        ty += lh + 2


def overlay_save_callout(draw: ImageDraw.ImageDraw, F, product: dict,
                         x: int, y: int, on_dark: bool = True) -> None:
    """Print 'Save $X.XX' next to the discount, if we can compute it."""
    price = (product.get("price") or "").strip()
    listp = (product.get("originalPrice") or product.get("listPrice") or "").strip()
    try:
        cur = float(re.sub(r"[^0-9.]", "", price))
        old = float(re.sub(r"[^0-9.]", "", listp))
    except (ValueError, TypeError):
        return
    if old <= cur:
        return
    saved = old - cur
    if saved < 1:
        return
    text = f"Save ${saved:.2f}"
    f = F("bold", 22)
    fill = GREEN if not on_dark else (180, 255, 200)
    draw.text((x, y), text, font=f, fill=fill)


# ─── STYLE 5: MAGAZINE EDITORIAL ───────────────────────────────────────────────

def _pin_magazine(product: dict, F) -> Image.Image:
    """Premium editorial magazine cover feel: ivory bg, gold accents, big serif feel."""
    canvas = Image.new("RGBA", (PIN_W, PIN_H), (250, 247, 240, 255))
    draw = ImageDraw.Draw(canvas)

    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    accent = cat["color"]
    pad_x = 70

    # Top thin gold rule + masthead
    draw.line((pad_x, 60, PIN_W - pad_x, 60), fill=GOLD, width=2)
    draw.line((pad_x, 70, PIN_W - pad_x, 70), fill=GOLD_DARK, width=1)

    # Eyebrow text (magazine-style)
    eyebrow_font = F("extrabold", 16)
    eb_text = "ISSUE 12  ·  CURATED BY NEXORA  ·  TOP DEAL"
    ebw, ebh = text_size(draw, eb_text, eyebrow_font)
    draw.text(((PIN_W - ebw) // 2, 86), eb_text, font=eyebrow_font, fill=(110, 90, 40))

    # Big editorial headline
    headline = "DEAL OF THE WEEK"
    hf = F("extrabold", 64)
    hw, hh = text_size(draw, headline, hf)
    draw.text(((PIN_W - hw) // 2, 122), headline, font=hf, fill=INK)

    # Sub-headline (category)
    cat_text = "✦   " + cat["display"] + "   ✦"
    cf = F("semibold", 18)
    cw, ch = text_size(draw, cat_text, cf)
    draw.text(((PIN_W - cw) // 2, 200), cat_text, font=cf, fill=accent)

    # Product image — clean white card with thin gold border
    card_x1, card_y1 = pad_x + 30, 250
    card_x2, card_y2 = PIN_W - pad_x - 30, 970
    card_w = card_x2 - card_x1
    card_h = card_y2 - card_y1
    # Soft shadow
    shadow = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    rounded_rect(sd, (card_x1 + 6, card_y1 + 14, card_x2 + 6, card_y2 + 14),
                 radius=8, fill=(0, 0, 0, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    canvas.alpha_composite(shadow)
    # White card
    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), radius=2,
                 fill=(255, 255, 255, 255))
    # Gold border
    draw.rectangle((card_x1, card_y1, card_x2, card_y2), outline=GOLD_DARK, width=2)
    draw.rectangle((card_x1 + 8, card_y1 + 8, card_x2 - 8, card_y2 - 8),
                   outline=GOLD + (180,), width=1)

    # Product image
    img = fetch_image(product.get("image", ""))
    if img is not None:
        target_w = card_w - 80
        target_h = card_h - 80
        fit = fit_image(img, target_w, target_h, bg=(0, 0, 0, 0))
        canvas.paste(fit, (card_x1 + 40, card_y1 + 40), fit)

    # Discount tag — refined, top-left of card
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        tag = f"{discount} OFF"
        tf = F("extrabold", 22)
        tw, th = text_size(draw, tag, tf)
        rb_x1 = card_x1 + 22
        rb_y1 = card_y1 + 22
        rb_x2 = rb_x1 + tw + 28
        rb_y2 = rb_y1 + th + 16
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=4,
                     fill=INK + (255,))
        draw.text((rb_x1 + 14, rb_y1 + 6), tag, font=tf, fill=GOLD)

    # Title — italic-feel sans serif, 2 lines max
    title = clean_for_pin(shorten_title(product.get("title", ""), 70))
    tf = F("extrabold", 36)
    lines = wrap_text(title, tf, PIN_W - pad_x * 2 - 100, draw)[:2]
    ty = 1010
    for line in lines:
        lw, lh = text_size(draw, line, tf)
        draw.text(((PIN_W - lw) // 2, ty), line, font=tf, fill=INK)
        ty += 50

    # Price block — center, with old price strikethrough above
    price = (product.get("price") or "").strip()
    listp = (product.get("originalPrice") or "").strip()
    if listp and listp != price:
        lf = F("regular", 26)
        lw, lh = text_size(draw, listp, lf)
        lpx, lpy = (PIN_W - lw) // 2, ty + 16
        draw.text((lpx, lpy), listp, font=lf, fill=(140, 130, 110))
        draw.line((lpx, lpy + lh // 2 + 2, lpx + lw, lpy + lh // 2 + 2),
                  fill=(140, 130, 110), width=2)
        ty += 42
    if price:
        pf = F("extrabold", 72)
        pw, ph = text_size(draw, price, pf)
        draw.text(((PIN_W - pw) // 2, ty + 4), price, font=pf, fill=accent)

    # CTA — thin gold-border button
    btn_y1, btn_y2 = PIN_H - 200, PIN_H - 110
    rounded_rect(draw, (pad_x + 80, btn_y1, PIN_W - pad_x - 80, btn_y2),
                 radius=2, fill=INK + (255,))
    draw.rectangle((pad_x + 80, btn_y1, PIN_W - pad_x - 80, btn_y2),
                   outline=GOLD, width=2)
    cta = product.get("_cta_magazine", "S H O P    T H E    F I N D")
    cf = F("extrabold", 26)
    cw, ch = text_size(draw, cta, cf)
    draw.text(((PIN_W - cw) // 2, btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 2),
              cta, font=cf, fill=GOLD)

    # Footer
    ff = F("regular", 16)
    foot = "n e x o r a - s h o p - u s . n e t l i f y . a p p"
    fw, fh = text_size(draw, foot, ff)
    draw.text(((PIN_W - fw) // 2, PIN_H - 75), foot, font=ff, fill=(110, 90, 40))

    overlay_hot_badge(canvas, draw, F, product)
    return canvas.convert("RGB")


# ─── STYLE 6: HEADLINE HOOK ────────────────────────────────────────────────────

# Category-keyed hooks (rotated; one chosen at render time based on title hash so
# successive pins of the same category get different hooks).
HOOKS_BY_CATEGORY = {
    "tech": [
        "Need this in 2026?",
        "Tired of clutter?",
        "Tech everyone is buying.",
        "This is on every list.",
        "The smartest find this week.",
    ],
    "home": [
        "Upgrade in one click.",
        "Cozy home essentials.",
        "Your kitchen needs this.",
        "Make home feel new.",
        "10K+ already added it.",
    ],
    "beauty": [
        "Glow without the price tag.",
        "Self-care, sorted.",
        "Editor's beauty pick.",
        "Smooth skin, made simple.",
        "Why everyone's buying this.",
    ],
    "pet": [
        "Your pup will love this.",
        "Pet parents swear by it.",
        "Made for happy pets.",
        "Buy it, thank yourself later.",
        "Your fur-baby's new favorite.",
    ],
}


def _pin_headline_hook(product: dict, F) -> Image.Image:
    """Pinterest's highest-converting layout: text-on-top hook + product reveal."""
    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    accent = cat["color"]
    canvas = Image.new("RGBA", (PIN_W, PIN_H), accent + (255,))
    draw = ImageDraw.Draw(canvas)
    pad_x = 56

    # Top half: bold question hook on solid color background
    hooks = HOOKS_BY_CATEGORY.get(product.get("category", "").lower(),
                                  HOOKS_BY_CATEGORY["tech"])
    seed = abs(hash(product.get("title", ""))) % len(hooks)
    hook_text = hooks[seed]

    # Brand top line
    nf = F("extrabold", 24)
    draw.text((pad_x, 50), "NEXORA", font=nf, fill=WHITE)
    sf = F("regular", 14)
    draw.text((pad_x, 82), "Smart Finds. Better Life.", font=sf, fill=(255, 255, 255, 220))

    # Category eyebrow (top-right) — opaque white pill so dark text is legible.
    # Suppress when the product is HOT, so the star-burst can take that corner.
    if not product.get("_is_hot"):
        cat_label = cat["display"]
        cf = F("extrabold", 16)
        cw, ch = text_size(draw, cat_label, cf)
        rounded_rect(draw, (PIN_W - pad_x - cw - 32, 60, PIN_W - pad_x, 96),
                     radius=18, fill=(255, 255, 255, 240))
        draw.text((PIN_W - pad_x - cw - 16, 68), cat_label, font=cf, fill=accent)

    # Hook headline (huge, multiple lines)
    hf = F("extrabold", 78)
    lines = wrap_text(hook_text, hf, PIN_W - pad_x * 2, draw)
    hy = 170
    for line in lines:
        draw.text((pad_x, hy), line, font=hf, fill=WHITE)
        hy += 90

    # Hook subtitle
    sub = "We found the answer →"
    sf2 = F("semibold", 28)
    draw.text((pad_x, hy + 20), sub, font=sf2, fill=(255, 255, 255, 220))

    # Bottom half: white card with product photo, price, CTA
    band_y = 700
    rounded_rect(draw, (0, band_y, PIN_W, PIN_H), radius=0, fill=IVORY + (255,))
    # Curve top
    rounded_rect(draw, (-40, band_y - 60, PIN_W + 40, band_y + 60),
                 radius=80, fill=IVORY + (255,))

    # Product image area (top-center of bottom half)
    img_y1, img_y2 = band_y + 30, band_y + 530
    img = fetch_image(product.get("image", ""))
    if img is not None:
        target_w = PIN_W - pad_x * 2
        target_h = img_y2 - img_y1
        fit = fit_image(img, target_w, target_h, bg=(0, 0, 0, 0))
        canvas.paste(fit, (pad_x, img_y1), fit)

    # Discount + Save callout (top-left of card area)
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        tag = f"{discount} OFF"
        tf = F("extrabold", 26)
        tw, th = text_size(draw, tag, tf)
        rb_x1 = pad_x
        rb_y1 = img_y1 + 8
        rb_x2 = rb_x1 + tw + 28
        rb_y2 = rb_y1 + th + 14
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=24,
                     fill=RED + (255,))
        draw.text((rb_x1 + 14, rb_y1 + 5), tag, font=tf, fill=WHITE)
        overlay_save_callout(draw, F, product, rb_x2 + 12, rb_y1 + 6, on_dark=False)

    # Title (one line, ellipsised)
    title = clean_for_pin(shorten_title(product.get("title", ""), 60))
    tf = F("bold", 28)
    lines_t = wrap_text(title, tf, PIN_W - pad_x * 2, draw)[:2]
    ty = img_y2 + 24
    for line in lines_t:
        draw.text((pad_x, ty), line, font=tf, fill=INK)
        ty += 36

    # Price + CTA row
    price = (product.get("price") or "").strip()
    if price:
        pf = F("extrabold", 60)
        draw.text((pad_x, PIN_H - 195), price, font=pf, fill=accent)

    # CTA button on the right
    btn_x1 = PIN_W - pad_x - 380
    btn_y1, btn_y2 = PIN_H - 200, PIN_H - 110
    rounded_rect(draw, (btn_x1, btn_y1, PIN_W - pad_x, btn_y2),
                 radius=44, fill=INK + (255,))
    cta = product.get("_cta_headline", "Shop Now  →")
    cf2 = F("extrabold", 32)
    cw, ch = text_size(draw, cta, cf2)
    draw.text((btn_x1 + (PIN_W - pad_x - btn_x1 - cw) // 2,
               btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 2),
              cta, font=cf2, fill=IVORY)

    # Footer URL
    ff = F("regular", 16)
    foot = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot, ff)
    draw.text(((PIN_W - fw) // 2, PIN_H - 60), foot, font=ff, fill=(120, 120, 120))

    overlay_hot_badge(canvas, draw, F, product)
    return canvas.convert("RGB")


# ─── STYLE 7: SPLASH POP (sticker-feel, very Pinterest-lifestyle) ──────────────

# Per-category soft pastel palettes
SPLASH_PALETTES = {
    "tech":   [(178, 209, 255), (124, 168, 252)],   # blue
    "home":   [(255, 218, 173), (255, 178, 122)],   # peach
    "beauty": [(255, 207, 230), (244, 168, 200)],   # pink
    "pet":    [(186, 240, 220), (130, 213, 184)],   # mint
}


def _gradient_45(c1, c2):
    """Diagonal gradient bg."""
    g = Image.new("RGB", (PIN_W, PIN_H), c1)
    px = g.load()
    diag_max = PIN_W + PIN_H
    for y in range(PIN_H):
        for x in range(PIN_W):
            t = (x + y) / diag_max
            r = int(c1[0] * (1 - t) + c2[0] * t)
            gr = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            px[x, y] = (r, gr, b)
    return g


def _paste_rotated(canvas, item, x, y, angle):
    """Paste an RGBA image onto canvas at (x, y) rotated `angle` degrees."""
    rotated = item.rotate(angle, resample=Image.BICUBIC, expand=True)
    canvas.paste(rotated, (x, y), rotated)


def _sticker(text, F, font_weight="extrabold", font_size=24, fill=(255, 220, 0),
             txt_color=(40, 20, 0), pad_x=18, pad_y=10, radius=20):
    """Build a small RGBA sticker image with text, rounded rect, soft border."""
    tmp = Image.new("RGBA", (1, 1))
    td = ImageDraw.Draw(tmp)
    f = F(font_weight, font_size)
    tw, th = text_size(td, text, f)
    w = tw + pad_x * 2
    h = th + pad_y * 2
    img = Image.new("RGBA", (w + 6, h + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Normalise fill to RGBA
    if len(fill) == 3:
        fill_rgba = fill + (255,)
    else:
        fill_rgba = fill
    rounded_rect(d, (3, 3, w + 3, h + 3), radius=radius, fill=fill_rgba)
    rounded_rect(d, (3, 3, w + 3, h + 3), radius=radius, outline=(0, 0, 0, 60), width=2)
    d.text((3 + pad_x, 3 + pad_y - 2), text, font=f, fill=txt_color)
    return img


def _pin_splash_pop(product: dict, F) -> Image.Image:
    """Colorful sticker-pop with multiple eye-catching badges + lifestyle feel."""
    cat_key = product.get("category", "").lower()
    cat = CATEGORIES.get(cat_key, CATEGORIES["tech"])
    palette = SPLASH_PALETTES.get(cat_key, SPLASH_PALETTES["tech"])

    canvas = _gradient_45(palette[0], palette[1]).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    pad_x = 56

    # Soft white blob behind product (looks like a "spot")
    blob = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((100, 250, PIN_W - 100, PIN_H - 350), fill=(255, 255, 255, 220))
    blob = blob.filter(ImageFilter.GaussianBlur(40))
    canvas.alpha_composite(blob)
    draw = ImageDraw.Draw(canvas)

    # Brand top
    nf = F("extrabold", 30)
    draw.text((pad_x, 56), "NEXORA", font=nf, fill=INK)
    sf = F("regular", 14)
    draw.text((pad_x, 92), "Smart Finds. Better Life.", font=sf, fill=(80, 80, 80))

    # Category eyebrow (top-right, pill). Suppressed for HOT products so the
    # TOP-PICK star-burst can take that corner.
    if not product.get("_is_hot"):
        cat_label = "✦  " + cat["display"]
        cf = F("extrabold", 18)
        cw, ch = text_size(draw, cat_label, cf)
        rounded_rect(draw, (PIN_W - pad_x - cw - 32, 60, PIN_W - pad_x, 102),
                     radius=22, fill=INK + (255,))
        draw.text((PIN_W - pad_x - cw - 16, 70), cat_label, font=cf, fill=IVORY)

    # Product image — large white card with slight rotation
    img = fetch_image(product.get("image", ""))
    if img is not None:
        # Make a card with product
        card_w, card_h = 720, 720
        card = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
        cd = ImageDraw.Draw(card)
        cd.rectangle((0, 0, card_w, card_h), outline=(0, 0, 0, 30), width=2)
        fit = fit_image(img, card_w - 80, card_h - 80, bg=(0, 0, 0, 0))
        card.paste(fit, (40, 40), fit)
        # Drop shadow
        shadow = Image.new("RGBA", (card_w + 60, card_h + 60), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        rounded_rect(sd, (30, 40, card_w + 30, card_h + 40), radius=8,
                     fill=(0, 0, 0, 80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        canvas.paste(shadow, (((PIN_W - card_w) // 2 - 30), 240), shadow)
        # Rotate slight angle
        seed = abs(hash(product.get("title", "")))
        angle = -2 + (seed % 5)  # -2 to +2 degrees
        rotated = card.rotate(angle, resample=Image.BICUBIC, expand=True)
        rx = (PIN_W - rotated.size[0]) // 2
        ry = 240
        canvas.paste(rotated, (rx, ry), rotated)

    # Title at bottom
    title = clean_for_pin(shorten_title(product.get("title", ""), 60))
    tf = F("extrabold", 36)
    lines = wrap_text(title, tf, PIN_W - pad_x * 2, draw)[:2]
    ty = 1040
    for line in lines:
        lw, lh = text_size(draw, line, tf)
        draw.text(((PIN_W - lw) // 2, ty), line, font=tf, fill=INK)
        ty += 50

    # Price + CTA row
    price = (product.get("price") or "").strip()
    listp = (product.get("originalPrice") or "").strip()
    if price:
        pf = F("extrabold", 64)
        if listp and listp != price:
            # show old price strikethrough left of new price
            lf = F("semibold", 28)
            old_w, old_h = text_size(draw, listp, lf)
            new_w, new_h = text_size(draw, price, pf)
            total_w = old_w + 24 + new_w
            ox = (PIN_W - total_w) // 2
            oy = ty + 32
            draw.text((ox, oy), listp, font=lf, fill=(120, 120, 120))
            draw.line((ox, oy + old_h // 2 + 2, ox + old_w, oy + old_h // 2 + 2),
                      fill=(120, 120, 120), width=2)
            draw.text((ox + old_w + 24, ty + 16), price, font=pf, fill=INK)
        else:
            new_w, _ = text_size(draw, price, pf)
            draw.text(((PIN_W - new_w) // 2, ty + 16), price, font=pf, fill=INK)

    # CTA — yellow rounded pill
    btn_y1, btn_y2 = PIN_H - 200, PIN_H - 110
    rounded_rect(draw, (pad_x + 80, btn_y1, PIN_W - pad_x - 80, btn_y2),
                 radius=44, fill=(255, 220, 60, 255))
    cta = product.get("_cta_splash", "Get Yours  →")
    cf2 = F("extrabold", 38)
    cw2, ch2 = text_size(draw, cta, cf2)
    draw.text(((PIN_W - cw2) // 2, btn_y1 + (btn_y2 - btn_y1 - ch2) // 2 - 2),
              cta, font=cf2, fill=(40, 20, 0))

    # Footer
    ff = F("regular", 16)
    foot = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot, ff)
    draw.text(((PIN_W - fw) // 2, PIN_H - 60), foot, font=ff, fill=(80, 80, 80))

    # ── Stickers (last so they sit on top of everything) ──
    discount = (product.get("discount") or "").strip()
    rating = (product.get("rating") or "").strip()
    review_count = (product.get("reviewCount") or "").strip()
    social = (product.get("socialProof") or "").strip()

    stickers: list[tuple[Image.Image, int, int, float]] = []
    if discount and re.search(r"\d", discount):
        s = _sticker(f"{discount} OFF", F, font_size=28, fill=(255, 80, 80),
                     txt_color=WHITE, radius=24, pad_x=20, pad_y=12)
        stickers.append((s, 80, 320, -8))
    if rating:
        rt = f"★ {rating}" + (f"  ({review_count})" if review_count else "")
        s = _sticker(rt, F, font_size=22, fill=WHITE, txt_color=INK,
                     radius=24, pad_x=18, pad_y=10)
        stickers.append((s, PIN_W - 320, 320, 6))
    if social:
        s = _sticker("🔥 " + social, F, font_size=20, fill=(255, 255, 255, 240),
                     txt_color=INK, radius=22, pad_x=16, pad_y=10)
        stickers.append((s, PIN_W - 380, 920, -4))

    for sticker, x, y, ang in stickers:
        _paste_rotated(canvas, sticker, x, y, ang)

    overlay_hot_badge(canvas, draw, F, product)
    return canvas.convert("RGB")


# ─── DISPATCH ──────────────────────────────────────────────────────────────────

EXTRA_STYLE_MAP = {
    "magazine": _pin_magazine,
    "headline": _pin_headline_hook,
    "splash":   _pin_splash_pop,
}


def make_pin_v2(product: dict, F, style: str):
    """Make a pin using either an original style (delegated to v1) OR one of the
    v2 styles defined in this module. Also applies the TOP PICK star-burst
    overlay to ANY style if product["_is_hot"] is True."""
    style = (style or "bold-dark").lower()
    if style in EXTRA_STYLE_MAP:
        # v2 styles draw the hot badge themselves (each picks the best position).
        return EXTRA_STYLE_MAP[style](product, F)

    # Fallback to v1
    from nexora_pinterest_generator import make_pin
    img = make_pin(product, F, style=style)

    # If the product is HOT, paint a star-burst on top of the v1 render.
    if product.get("_is_hot"):
        rgba = img.convert("RGBA")
        draw = ImageDraw.Draw(rgba)
        # v1 styles all keep top-left/top-right corners pretty clean — top-right
        # is consistently safest for a star-burst overlay.
        overlay_hot_badge(rgba, draw, F, product, pos="top-right")
        return rgba.convert("RGB")
    return img
