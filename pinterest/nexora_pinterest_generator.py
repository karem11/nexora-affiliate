"""
NEXORA Pinterest Pin Generator v1.0
====================================

Generates 30 ready-to-publish Pinterest pins from products.js.

Outputs:
  - output/pins/<category>/<NN>_<slug>.png    (1000x1500 PNG)
  - output/nexora_pins.csv                     (Pinterest Bulk Create format)

Usage:
  python nexora_pinterest_generator.py
  python nexora_pinterest_generator.py --products /path/to/products.js
  python nexora_pinterest_generator.py --limit 5    # generate only 5 pins (test)
  python nexora_pinterest_generator.py --site https://nexora-shop-us.netlify.app

Designed for the NEXORA dark theme:
  bg=#06111f surface=#0c1e35 blue=#2176ff text=#e8f0ff muted=#8aa4cc
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import textwrap
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


# ─── CONFIG ────────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent.resolve()
DEFAULT_PRODUCTS_JS = HERE.parent / "website" / "products.js"
FONTS_DIR = HERE / "fonts"
LOGO_PATH = HERE / "nexora_logo.png"
OUTPUT_DIR = HERE / "output"
PINS_DIR = OUTPUT_DIR / "pins"
CACHE_DIR = OUTPUT_DIR / "cache"
CSV_PATH = OUTPUT_DIR / "nexora_pins.csv"

PIN_W, PIN_H = 1000, 1500   # Pinterest's recommended 2:3 ratio

# NEXORA brand colors
BG          = (6, 17, 31)
SURFACE     = (12, 30, 53)
SURFACE_2   = (17, 36, 68)
BLUE        = (33, 118, 255)
BLUE_DARK   = (16, 87, 212)
TEXT        = (232, 240, 255)
MUTED       = (138, 164, 204)
GREEN       = (34, 197, 94)
RED         = (239, 68, 68)
WHITE       = (255, 255, 255)
ORANGE      = (255, 153, 0)        # Amazon orange
ORANGE_DARK = (230, 132, 0)

# Category metadata: display name + Pinterest board name + hashtags + color
# (No emojis on the pin canvas — Inter doesn't include emoji glyphs.
#  Pin descriptions and CSV may include emojis since Pinterest renders them server-side.)
CATEGORIES = {
    "tech": {
        "emoji": "⚡",
        "display": "ELECTRONICS",
        "board": "Smart Tech Finds",
        "hashtags": ["#amazonfinds", "#techgadgets", "#smarthome", "#techlovers", "#musthaves"],
        "color": (33, 118, 255),
    },
    "home": {
        "emoji": "🏠",
        "display": "HOME & KITCHEN",
        "board": "Home & Kitchen Inspiration",
        "hashtags": ["#homedecor", "#kitchenmusthaves", "#amazonhome", "#homefinds", "#homestyle"],
        "color": (250, 184, 0),
    },
    "beauty": {
        "emoji": "💄",
        "display": "BEAUTY & PERSONAL CARE",
        "board": "Beauty & Self Care",
        "hashtags": ["#beautyfinds", "#selfcare", "#skincare", "#beautyamazon", "#beautymusthaves"],
        "color": (244, 114, 182),
    },
    "pet": {
        "emoji": "🐾",
        "display": "PET SUPPLIES",
        "board": "Pet Lover Essentials",
        "hashtags": ["#petlovers", "#petsupplies", "#dogmom", "#catlovers", "#petparent"],
        "color": (16, 185, 129),
    },
}


NON_ASCII_RE = re.compile(r"[^\x00-\x7F]+")

# Map of common fullwidth / smart punctuation -> ASCII equivalents.
_PUNCT_MAP = {
    "，": ", ", "、": ", ", "；": "; ", "：": ": ",
    "．": ". ", "。": ". ", "！": "! ", "？": "? ",
    "—": " - ", "–": " - ", "【": "[", "】": "]",
    "（": "(", "）": ")", "“": '"', "”": '"',
    "‘": "'", "’": "'",
}


def normalize_punct(text: str) -> str:
    """Replace fullwidth/smart punctuation with ASCII equivalents."""
    if not text:
        return ""
    for src, dst in _PUNCT_MAP.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


def clean_for_pin(text: str) -> str:
    """Strip non-ASCII characters that Inter cannot render (e.g. fullwidth comma).
    Used only for text painted onto the pin canvas — CSV/description retain the
    original Unicode (after light normalization)."""
    if not text:
        return ""
    cleaned = normalize_punct(text)
    cleaned = NON_ASCII_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# ─── UTILS ─────────────────────────────────────────────────────────────────────

def load_products(products_js_path: Path) -> list:
    """Parse products.js (a JS file containing a JSON array)."""
    raw = products_js_path.read_text(encoding="utf-8")
    # Strip `const products = ` and trailing `;`
    body = re.sub(r"^\s*const\s+products\s*=\s*", "", raw)
    body = re.sub(r";\s*$", "", body.strip())
    return json.loads(body)


def fonts():
    """Load font instances at common sizes (cached)."""
    paths = {
        "regular": FONTS_DIR / "Inter-Regular.ttf",
        "semibold": FONTS_DIR / "Inter-SemiBold.ttf",
        "bold": FONTS_DIR / "Inter-Bold.ttf",
        "extrabold": FONTS_DIR / "Inter-ExtraBold.ttf",
    }
    for name, p in paths.items():
        if not p.exists():
            raise FileNotFoundError(
                f"Missing font: {p}. Run the bundled setup script or "
                f"download Inter from https://rsms.me/inter/."
            )

    def F(weight: str, size: int):
        return ImageFont.truetype(str(paths[weight]), size)

    return F


# Browser-like User-Agent. Amazon's m.media-amazon.com serves a 403 / 503
# for the default Python urllib UA AND for short custom UAs. Use a real Chrome UA.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Track image fetch failures across the whole run so we can summarize at the end.
FAILED_IMAGES: list[tuple[str, str]] = []   # list of (url, reason)


def _is_image_bytes(data: bytes) -> bool:
    """Quick sniff: does this look like image data (PNG/JPEG/WEBP/GIF)?"""
    if not data or len(data) < 8:
        return False
    return (
        data[:8] == b"\x89PNG\r\n\x1a\n"        # PNG
        or data[:3] == b"\xff\xd8\xff"           # JPEG
        or data[:6] in (b"GIF87a", b"GIF89a")    # GIF
        or data[:4] == b"RIFF" and data[8:12] == b"WEBP"  # WEBP
        or data[:2] == b"BM"                     # BMP
    )


def _amazon_url_variants(url: str) -> list[str]:
    """Generate fallback Amazon image URL variants. The original Amazon URL has
    a size suffix like `_AC_SL1500_` or `_AC_UL232_SR232,232_` — we strip the
    size encoding to get the base image, which usually works even if the
    sized variant is rate-limited."""
    if "media-amazon" not in url:
        return [url]
    # Remove size encoding patterns like ._AC_SL1500_ → .
    stripped = re.sub(r"\._[A-Z0-9_,]+_(?=\.(?:jpg|jpeg|png|webp|gif))", ".", url, flags=re.I)
    out = [url]
    if stripped != url and stripped not in out:
        out.append(stripped)
    # Try a forced large size as a 3rd attempt
    forced = re.sub(r"\._[A-Z0-9_,]+_(?=\.(?:jpg|jpeg|png|webp|gif))", "._AC_SL1200_.", url, flags=re.I)
    if forced not in out:
        out.append(forced)
    return out


def fetch_image(url: str) -> Image.Image:
    """Download (or cached-load) an image URL into a PIL Image (RGBA).

    Robust version:
      • Real Chrome User-Agent + Referer (Amazon CDN sometimes 403's otherwise)
      • 3 retries with exponential backoff
      • Falls back to alternative Amazon URL sizes if the original is blocked
      • Validates that response is actually image bytes (not an HTML error page)
      • Records failures in FAILED_IMAGES for end-of-run summary
    """
    if not url:
        return None

    safe_name = re.sub(r"[^a-zA-Z0-9.]+", "_", url)[-100:]
    cache_path = CACHE_DIR / safe_name
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            try:
                cache_path.unlink()
            except OSError:
                pass

    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.amazon.com/",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }

    last_err: str = ""
    candidates = _amazon_url_variants(url)

    for variant in candidates:
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(variant, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                if not _is_image_bytes(data):
                    last_err = f"server returned non-image data ({len(data)} bytes; "\
                               f"likely error page)"
                    break  # try next variant
                cache_path.write_bytes(data)
                return Image.open(io.BytesIO(data)).convert("RGBA")
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}"
                if e.code in (404, 410):
                    break  # try next variant
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = f"network: {e}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
            if attempt < 3:
                import time as _t
                _t.sleep(2 ** (attempt - 1))   # 1s, 2s

    FAILED_IMAGES.append((url, last_err))
    print(f"  [warn] Could not fetch image: {url}\n         reason: {last_err}")
    return None


def report_failed_images() -> None:
    """Print a human-friendly summary of all failed image fetches."""
    if not FAILED_IMAGES:
        return
    print("")
    print("─" * 64)
    print(f" ⚠  {len(FAILED_IMAGES)} image(s) could not be downloaded:")
    print("─" * 64)
    for u, reason in FAILED_IMAGES:
        print(f"   • {u[:80]}{'…' if len(u) > 80 else ''}")
        print(f"     {reason}")
    print("")
    print(" Likely causes:")
    print("   1. Your network/ISP is blocking Amazon's image CDN.")
    print("   2. Amazon is rate-limiting your IP — wait 5 minutes and re-run.")
    print("   3. A VPN may bypass the block. Try connecting to a US/EU server.")
    print("─" * 64)


def slugify(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^\w\s-]", "", text or "", flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s.strip()).lower()
    return s[:maxlen].strip("-") or "product"


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    """Return (w, h) for a single line of text."""
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:
        return draw.textsize(text, font=font)


def wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """Word-wrap text to a list of lines that each fit max_width pixels."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        candidate = (cur + " " + w).strip()
        cand_w, _ = text_size(draw, candidate, font)
        if cand_w <= max_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None, outline=None, width: int = 1):
    """ImageDraw.rounded_rectangle wrapper that handles older PIL versions."""
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    else:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)


def fit_image(img: Image.Image, target_w: int, target_h: int, bg=(255, 255, 255, 0)) -> Image.Image:
    """Resize img to fit inside (target_w, target_h) preserving aspect ratio,
    then center it on a transparent canvas of that size."""
    if img is None:
        canvas = Image.new("RGBA", (target_w, target_h), bg)
        return canvas
    iw, ih = img.size
    scale = min(target_w / iw, target_h / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (target_w, target_h), bg)
    canvas.paste(img_resized, ((target_w - new_w) // 2, (target_h - new_h) // 2), img_resized)
    return canvas


def shorten_title(title: str, max_chars: int = 70) -> str:
    """Return a punchy short version of the title (used on the pin)."""
    title = re.sub(r"\s+", " ", title or "").strip()
    # Drop everything after the first comma OR dash if title is long
    if len(title) > max_chars:
        for sep in [",", " - ", " – ", " | ", "("]:
            if sep in title:
                cut = title.split(sep, 1)[0].strip()
                if len(cut) >= 20:
                    title = cut
                    break
    if len(title) > max_chars:
        title = title[:max_chars].rsplit(" ", 1)[0] + "…"
    return title


# ─── PIN COMPOSITION ───────────────────────────────────────────────────────────

GOLD       = (212, 175, 55)
GOLD_DARK  = (167, 134, 34)
IVORY      = (250, 248, 243)
INK        = (15, 23, 36)
INK_SOFT   = (32, 42, 58)


def make_pin(product: dict, F, style: str = "bold-dark") -> Image.Image:
    """Dispatch to one of the four style renderers."""
    style = (style or "bold-dark").lower()
    if style == "minimalist":
        return _pin_minimalist(product, F)
    if style == "luxe":
        return _pin_luxe(product, F)
    if style == "vibrant":
        return _pin_vibrant(product, F)
    return _pin_bold_dark(product, F)


def _pin_bold_dark(product: dict, F) -> Image.Image:
    canvas = Image.new("RGBA", (PIN_W, PIN_H), BG + (255,))
    draw = ImageDraw.Draw(canvas)

    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    accent = cat["color"]

    # ─── Decorative background blobs ─────────────────────────────────
    # subtle colored radial blobs so the bg isn't flat
    blob = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((-200, -200, 500, 500), fill=accent + (40,))
    bd.ellipse((PIN_W - 300, PIN_H - 700, PIN_W + 300, PIN_H - 100), fill=BLUE + (28,))
    blob = blob.filter(ImageFilter.GaussianBlur(120))
    canvas = Image.alpha_composite(canvas, blob)
    draw = ImageDraw.Draw(canvas)

    # ─── HEADER (top 110px) ──────────────────────────────────────────
    pad_x = 56
    header_y = 50

    # NEXORA logo + wordmark
    if LOGO_PATH.exists():
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo = fit_image(logo, 60, 60)
            canvas.paste(logo, (pad_x, header_y - 5), logo)
        except Exception:
            pass

    draw.text((pad_x + 76, header_y - 3), "NEXORA", font=F("extrabold", 38), fill=WHITE)
    draw.text((pad_x + 76, header_y + 38), "Smart Finds. Better Life.",
              font=F("regular", 17), fill=MUTED)

    # Category badge (top-right pill) — colored dot + plain label, no emoji
    cat_label = cat["display"]
    cat_font = F("extrabold", 20)
    cw, ch = text_size(draw, cat_label, cat_font)
    dot_d = 14
    pill_x2 = PIN_W - pad_x
    pill_x1 = pill_x2 - cw - 64 - dot_d
    pill_y1 = header_y + 6
    pill_y2 = pill_y1 + ch + 24
    rounded_rect(draw, (pill_x1, pill_y1, pill_x2, pill_y2), radius=26,
                 fill=accent + (255,))
    dot_x = pill_x1 + 22
    dot_y = (pill_y1 + pill_y2) // 2 - dot_d // 2
    draw.ellipse((dot_x, dot_y, dot_x + dot_d, dot_y + dot_d), fill=WHITE)
    draw.text((dot_x + dot_d + 14, pill_y1 + 12), cat_label, font=cat_font, fill=WHITE)

    # ─── PRODUCT IMAGE CARD ──────────────────────────────────────────
    # White rounded card so any product photo stands out on dark bg
    card_x1, card_y1 = pad_x, 160
    card_x2, card_y2 = PIN_W - pad_x, 880
    card_w = card_x2 - card_x1
    card_h = card_y2 - card_y1

    # Soft drop shadow
    shadow = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    rounded_rect(sd, (card_x1 + 6, card_y1 + 12, card_x2 + 6, card_y2 + 12),
                 radius=36, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)

    # White card
    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), radius=32,
                 fill=(255, 255, 255, 255))

    # Product image
    img = fetch_image(product.get("image", ""))
    if img is not None:
        # leave a 40px inset so image breathes
        img_box = (40, 40, card_w - 40, card_h - 40)
        target_w = img_box[2] - img_box[0]
        target_h = img_box[3] - img_box[1]
        fit = fit_image(img, target_w, target_h, bg=(255, 255, 255, 0))
        canvas.paste(fit, (card_x1 + img_box[0], card_y1 + img_box[1]), fit)
    else:
        # fallback placeholder
        ph_font = F("bold", 36)
        ph_text = "Image Unavailable"
        tw, th = text_size(draw, ph_text, ph_font)
        draw.text((card_x1 + (card_w - tw) // 2, card_y1 + (card_h - th) // 2),
                  ph_text, font=ph_font, fill=MUTED)

    # Discount ribbon on top-left corner of card
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        ribbon_text = f"{discount} OFF"
        rf = F("extrabold", 30)
        rw, rh = text_size(draw, ribbon_text, rf)
        rb_x1 = card_x1 + 24
        rb_y1 = card_y1 + 24
        rb_x2 = rb_x1 + rw + 32
        rb_y2 = rb_y1 + rh + 18
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=14, fill=RED + (255,))
        draw.text((rb_x1 + 16, rb_y1 + 6), ribbon_text, font=rf, fill=WHITE)

    # Rating badge on top-right of card
    rating = (product.get("rating") or "").strip()
    review_count = (product.get("reviewCount") or "").strip()
    if rating:
        star = f"★ {rating}"
        if review_count:
            star += f"  ({review_count})"
        rf = F("bold", 24)
        rw, rh = text_size(draw, star, rf)
        rt_x2 = card_x2 - 24
        rt_y1 = card_y1 + 24
        rt_x1 = rt_x2 - rw - 28
        rt_y2 = rt_y1 + rh + 16
        rounded_rect(draw, (rt_x1, rt_y1, rt_x2, rt_y2), radius=14, fill=(15, 23, 42, 235))
        draw.text((rt_x1 + 14, rt_y1 + 7), star, font=rf, fill=(253, 224, 71))  # amber

    # ─── INFO PANEL (below card) ─────────────────────────────────────
    info_y = card_y2 + 36

    # Title
    title = clean_for_pin(shorten_title(product.get("title", ""), 75))
    title_font = F("extrabold", 44)
    title_lines = wrap_text(title, title_font, PIN_W - pad_x * 2, draw)
    title_lines = title_lines[:3]
    line_h = 50
    for i, line in enumerate(title_lines):
        draw.text((pad_x, info_y + i * line_h), line, font=title_font, fill=WHITE)
    info_y += len(title_lines) * line_h + 18

    # Price block (BIG)
    price = (product.get("price") or "").strip()
    list_price = (product.get("listPrice") or "").strip()
    price_font = F("extrabold", 78)
    listprice_font = F("regular", 36)

    if price:
        # green price
        pw, ph = text_size(draw, price, price_font)
        draw.text((pad_x, info_y), price, font=price_font, fill=GREEN)
        # list price (strikethrough) next to it
        if list_price and list_price != price:
            lp_x = pad_x + pw + 24
            lp_y = info_y + 26
            draw.text((lp_x, lp_y), list_price, font=listprice_font, fill=MUTED)
            lp_w, lp_h = text_size(draw, list_price, listprice_font)
            draw.line(
                (lp_x, lp_y + lp_h // 2, lp_x + lp_w, lp_y + lp_h // 2),
                fill=MUTED, width=3,
            )
        info_y += ph + 24

    # ─── CTA BUTTON ──────────────────────────────────────────────────
    btn_y1 = PIN_H - 220
    btn_y2 = btn_y1 + 110
    btn_x1, btn_x2 = pad_x, PIN_W - pad_x
    rounded_rect(draw, (btn_x1, btn_y1, btn_x2, btn_y2), radius=24, fill=ORANGE + (255,))

    cta = product.get("_cta", "Shop on Amazon  \u2192")
    cta_font = F("extrabold", 50)
    cw, ch = text_size(draw, cta, cta_font)
    draw.text(
        (btn_x1 + (btn_x2 - btn_x1 - cw) // 2, btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 4),
        cta, font=cta_font, fill=(35, 23, 0),
    )

    # ─── FOOTER URL ──────────────────────────────────────────────────
    foot_font = F("semibold", 22)
    foot_text = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot_text, foot_font)
    draw.text(((PIN_W - fw) // 2, PIN_H - 70), foot_text, font=foot_font, fill=MUTED)

    return canvas.convert("RGB")


# ─── STYLE B: MINIMALIST LIGHT ────────────────────────────────────────────────

def _pin_minimalist(product: dict, F) -> Image.Image:
    """Editorial / clean: white bg, soft gray card, big black type, accent dot."""
    canvas = Image.new("RGBA", (PIN_W, PIN_H), IVORY + (255,))
    draw = ImageDraw.Draw(canvas)

    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    accent = cat["color"]
    pad_x = 64

    # Top accent line
    draw.rectangle((pad_x, 50, pad_x + 56, 56), fill=accent + (255,))

    # Category eyebrow
    eyebrow = cat["display"]
    eyebrow_font = F("extrabold", 18)
    draw.text((pad_x + 80, 44), eyebrow, font=eyebrow_font, fill=accent)

    # Brand wordmark (right side)
    nf = F("extrabold", 28)
    nw, nh = text_size(draw, "NEXORA", nf)
    draw.text((PIN_W - pad_x - nw, 38), "NEXORA", font=nf, fill=INK)

    # Subhead under brand
    sf = F("regular", 14)
    sw, sh = text_size(draw, "Smart Finds. Better Life.", sf)
    draw.text((PIN_W - pad_x - sw, 72), "Smart Finds. Better Life.", font=sf, fill=(120, 120, 120))

    # Product photo (no card — direct on bg, but with soft tint)
    img_y1, img_y2 = 140, 920
    img = fetch_image(product.get("image", ""))
    if img is not None:
        target_w = PIN_W - pad_x * 2
        target_h = img_y2 - img_y1
        fit = fit_image(img, target_w, target_h, bg=(0, 0, 0, 0))
        canvas.paste(fit, (pad_x, img_y1), fit)

    # Discount tag (top-left, small black pill)
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        tag = f"{discount} OFF"
        tf = F("extrabold", 26)
        tw, th = text_size(draw, tag, tf)
        rb_x1 = pad_x
        rb_y1 = img_y1 + 10
        rb_x2 = rb_x1 + tw + 28
        rb_y2 = rb_y1 + th + 16
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=8, fill=INK + (255,))
        draw.text((rb_x1 + 14, rb_y1 + 5), tag, font=tf, fill=IVORY)

    # Star rating (top-right)
    rating = (product.get("rating") or "").strip()
    if rating:
        review_count = (product.get("reviewCount") or "").strip()
        star = f"\u2605 {rating}" + (f"  ({review_count})" if review_count else "")
        rf = F("bold", 22)
        rw, rh = text_size(draw, star, rf)
        draw.text((PIN_W - pad_x - rw, img_y1 + 14), star, font=rf, fill=INK)

    # Thin divider
    draw.line((pad_x, 950, PIN_W - pad_x, 950), fill=(200, 200, 200), width=2)

    # Title
    title = clean_for_pin(shorten_title(product.get("title", ""), 80))
    title_font = F("extrabold", 50)
    lines = wrap_text(title, title_font, PIN_W - pad_x * 2, draw)[:3]
    ty = 990
    for line in lines:
        draw.text((pad_x, ty), line, font=title_font, fill=INK)
        ty += 56

    # Price block — accent color
    price = (product.get("price") or "").strip()
    list_price = (product.get("listPrice") or "").strip()
    if price:
        price_font = F("extrabold", 90)
        pw, ph = text_size(draw, price, price_font)
        py = ty + 24
        draw.text((pad_x, py), price, font=price_font, fill=accent)
        if list_price and list_price != price:
            lf = F("regular", 36)
            lp_x = pad_x + pw + 24
            lp_y = py + 32
            draw.text((lp_x, lp_y), list_price, font=lf, fill=(160, 160, 160))
            lpw, lph = text_size(draw, list_price, lf)
            draw.line((lp_x, lp_y + lph // 2, lp_x + lpw, lp_y + lph // 2),
                      fill=(160, 160, 160), width=3)

    # CTA — outlined black button
    btn_y1, btn_y2 = PIN_H - 220, PIN_H - 110
    rounded_rect(draw, (pad_x, btn_y1, PIN_W - pad_x, btn_y2),
                 radius=18, fill=INK + (255,))
    cta = product.get("_cta", "Shop on Amazon  \u2192")
    cf = F("extrabold", 46)
    cw, ch = text_size(draw, cta, cf)
    draw.text(((PIN_W - cw) // 2, btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 2),
              cta, font=cf, fill=IVORY)

    # Footer URL
    foot_font = F("semibold", 22)
    foot_text = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot_text, foot_font)
    draw.text(((PIN_W - fw) // 2, PIN_H - 70), foot_text, font=foot_font, fill=(140, 140, 140))

    return canvas.convert("RGB")


# ─── STYLE C: LUXE GOLD ───────────────────────────────────────────────────────

def _pin_luxe(product: dict, F) -> Image.Image:
    """Premium / editorial: deep black bg, gold accents, thin gold borders."""
    BLACK = (8, 8, 12)
    canvas = Image.new("RGBA", (PIN_W, PIN_H), BLACK + (255,))
    draw = ImageDraw.Draw(canvas)

    pad_x = 64

    # Outer gold hairline border
    draw.rectangle((28, 28, PIN_W - 28, PIN_H - 28), outline=GOLD, width=2)
    draw.rectangle((38, 38, PIN_W - 38, PIN_H - 38), outline=GOLD_DARK, width=1)

    # Top section
    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])

    # Category eyebrow centered
    eyebrow = "— " + cat["display"] + " —"
    ef = F("semibold", 18)
    ew, eh = text_size(draw, eyebrow, ef)
    draw.text(((PIN_W - ew) // 2, 70), eyebrow, font=ef, fill=GOLD)

    # NEXORA wordmark BIG centered
    nf = F("extrabold", 56)
    nw, nh = text_size(draw, "NEXORA", nf)
    draw.text(((PIN_W - nw) // 2, 102), "NEXORA", font=nf, fill=IVORY)

    # Tiny tagline
    tag = "C U R A T E D    F I N D S"
    tf = F("regular", 14)
    tw, th = text_size(draw, tag, tf)
    draw.text(((PIN_W - tw) // 2, 178), tag, font=tf, fill=GOLD)

    # Decorative gold separator
    draw.line((PIN_W // 2 - 60, 215, PIN_W // 2 + 60, 215), fill=GOLD, width=1)

    # Product image — direct on black with subtle frame
    img_y1, img_y2 = 260, 940
    img = fetch_image(product.get("image", ""))
    if img is not None:
        # White stage card
        rounded_rect(draw, (pad_x, img_y1, PIN_W - pad_x, img_y2), radius=4,
                     fill=(245, 243, 237, 255))
        draw.rectangle((pad_x, img_y1, PIN_W - pad_x, img_y2), outline=GOLD, width=2)

        target_w = (PIN_W - pad_x * 2) - 60
        target_h = (img_y2 - img_y1) - 60
        fit = fit_image(img, target_w, target_h, bg=(0, 0, 0, 0))
        canvas.paste(fit, (pad_x + 30, img_y1 + 30), fit)

    # Discount badge
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        tag_text = f"{discount} OFF"
        tagf = F("extrabold", 24)
        tw, th = text_size(draw, tag_text, tagf)
        rb_x1 = pad_x + 16
        rb_y1 = img_y1 + 16
        rb_x2 = rb_x1 + tw + 28
        rb_y2 = rb_y1 + th + 14
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=2, fill=BLACK + (255,))
        draw.rectangle((rb_x1, rb_y1, rb_x2, rb_y2), outline=GOLD, width=1)
        draw.text((rb_x1 + 14, rb_y1 + 5), tag_text, font=tagf, fill=GOLD)

    # Title — italic-feeling serif vibe (we use Inter Bold, smaller, centered)
    title = clean_for_pin(shorten_title(product.get("title", ""), 70))
    title_font = F("bold", 36)
    lines = wrap_text(title, title_font, PIN_W - pad_x * 2 - 40, draw)[:3]
    ty = 980
    for line in lines:
        lw, lh = text_size(draw, line, title_font)
        draw.text(((PIN_W - lw) // 2, ty), line, font=title_font, fill=IVORY)
        ty += 46

    # Price (gold, big)
    price = (product.get("price") or "").strip()
    list_price = (product.get("listPrice") or "").strip()
    if price:
        pf = F("extrabold", 78)
        pw, ph = text_size(draw, price, pf)
        py = ty + 30
        draw.text(((PIN_W - pw) // 2, py), price, font=pf, fill=GOLD)
        if list_price and list_price != price:
            lf = F("regular", 30)
            lpw, lph = text_size(draw, list_price, lf)
            draw.text((((PIN_W - pw) // 2) + pw + 18, py + 32), list_price, font=lf, fill=(140, 130, 100))
            lpx = ((PIN_W - pw) // 2) + pw + 18
            lpy = py + 32
            draw.line((lpx, lpy + lph // 2, lpx + lpw, lpy + lph // 2),
                      fill=(140, 130, 100), width=2)

    # CTA — gold-bordered black button
    btn_y1, btn_y2 = PIN_H - 220, PIN_H - 130
    rounded_rect(draw, (pad_x + 60, btn_y1, PIN_W - pad_x - 60, btn_y2),
                 radius=2, fill=BLACK + (255,))
    draw.rectangle((pad_x + 60, btn_y1, PIN_W - pad_x - 60, btn_y2), outline=GOLD, width=2)
    cta = product.get("_cta_luxe", "S H O P    N O W")
    cf = F("extrabold", 28)
    cw, ch = text_size(draw, cta, cf)
    draw.text(((PIN_W - cw) // 2, btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 2),
              cta, font=cf, fill=GOLD)

    # Footer
    ff = F("regular", 18)
    foot = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot, ff)
    draw.text(((PIN_W - fw) // 2, PIN_H - 80), foot, font=ff, fill=GOLD_DARK)

    return canvas.convert("RGB")


# ─── STYLE D: VIBRANT GRADIENT ────────────────────────────────────────────────

def _gradient_bg(color_top, color_bottom):
    """Vertical gradient between two RGB colors."""
    g = Image.new("RGB", (PIN_W, PIN_H), color_top)
    px = g.load()
    for y in range(PIN_H):
        t = y / (PIN_H - 1)
        r = int(color_top[0] * (1 - t) + color_bottom[0] * t)
        gr = int(color_top[1] * (1 - t) + color_bottom[1] * t)
        b = int(color_top[2] * (1 - t) + color_bottom[2] * t)
        for x in range(PIN_W):
            px[x, y] = (r, gr, b)
    return g


def _pin_vibrant(product: dict, F) -> Image.Image:
    """Playful / lifestyle: gradient bg per category, rounded everything."""
    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    accent = cat["color"]

    # Build gradient from accent (top) to a darker shade (bottom)
    a = accent
    bottom = (max(0, a[0] - 80), max(0, a[1] - 80), max(0, a[2] - 80))
    canvas = _gradient_bg(a, bottom).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    pad_x = 56

    # Sticker-like white badge top-left for category
    cat_label = cat["display"]
    cf = F("extrabold", 22)
    cw, ch = text_size(draw, cat_label, cf)
    bx2 = pad_x + cw + 44
    rounded_rect(draw, (pad_x, 50, bx2, 50 + ch + 28), radius=30, fill=(255, 255, 255, 255))
    draw.text((pad_x + 22, 60), cat_label, font=cf, fill=accent)

    # NEXORA top-right
    nf = F("extrabold", 32)
    nw, nh = text_size(draw, "NEXORA", nf)
    draw.text((PIN_W - pad_x - nw, 56), "NEXORA", font=nf, fill=WHITE)

    # White tagline
    sf = F("regular", 14)
    sw, sh = text_size(draw, "Smart Finds. Better Life.", sf)
    draw.text((PIN_W - pad_x - sw, 96), "Smart Finds. Better Life.", font=sf, fill=(255, 255, 255, 220))

    # Big rounded white card containing product image
    card_x1, card_y1 = pad_x, 160
    card_x2, card_y2 = PIN_W - pad_x, 920
    # Soft drop shadow
    shadow = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    rounded_rect(sd, (card_x1 + 8, card_y1 + 18, card_x2 + 8, card_y2 + 18),
                 radius=48, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)

    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), radius=44, fill=(255, 255, 255, 255))

    img = fetch_image(product.get("image", ""))
    if img is not None:
        target_w = card_x2 - card_x1 - 80
        target_h = card_y2 - card_y1 - 80
        fit = fit_image(img, target_w, target_h, bg=(0, 0, 0, 0))
        canvas.paste(fit, (card_x1 + 40, card_y1 + 40), fit)

    # Discount sticker (rotated-feeling pill)
    discount = (product.get("discount") or "").strip()
    if discount and re.search(r"\d", discount):
        tag = f"{discount} OFF"
        tagf = F("extrabold", 30)
        tw, th = text_size(draw, tag, tagf)
        rb_x1 = card_x1 + 24
        rb_y1 = card_y1 + 24
        rb_x2 = rb_x1 + tw + 32
        rb_y2 = rb_y1 + th + 20
        rounded_rect(draw, (rb_x1, rb_y1, rb_x2, rb_y2), radius=30, fill=RED + (255,))
        draw.text((rb_x1 + 16, rb_y1 + 8), tag, font=tagf, fill=WHITE)

    # Star rating
    rating = (product.get("rating") or "").strip()
    if rating:
        review_count = (product.get("reviewCount") or "").strip()
        star = f"\u2605 {rating}" + (f"  ({review_count})" if review_count else "")
        rf = F("bold", 24)
        rw, rh = text_size(draw, star, rf)
        rt_x2 = card_x2 - 24
        rt_y1 = card_y1 + 24
        rt_x1 = rt_x2 - rw - 28
        rt_y2 = rt_y1 + rh + 16
        rounded_rect(draw, (rt_x1, rt_y1, rt_x2, rt_y2), radius=24, fill=INK + (255,))
        draw.text((rt_x1 + 14, rt_y1 + 7), star, font=rf, fill=(253, 224, 71))

    # Title (white on gradient)
    title = clean_for_pin(shorten_title(product.get("title", ""), 70))
    title_font = F("extrabold", 46)
    lines = wrap_text(title, title_font, PIN_W - pad_x * 2, draw)[:3]
    ty = 960
    for line in lines:
        draw.text((pad_x, ty), line, font=title_font, fill=WHITE)
        ty += 52

    # Price card (white pill)
    price = (product.get("price") or "").strip()
    list_price = (product.get("listPrice") or "").strip()
    if price:
        pf = F("extrabold", 74)
        pw, ph = text_size(draw, price, pf)
        # white rounded background just behind the price
        pcx1 = pad_x - 6
        pcy1 = ty + 12
        pcx2 = pcx1 + pw + 32
        pcy2 = pcy1 + ph + 24
        if list_price and list_price != price:
            lf = F("regular", 36)
            lpw, lph = text_size(draw, list_price, lf)
            pcx2 += lpw + 28
        rounded_rect(draw, (pcx1, pcy1, pcx2, pcy2), radius=22, fill=(255, 255, 255, 255))
        draw.text((pcx1 + 16, pcy1 + 12), price, font=pf, fill=accent)
        if list_price and list_price != price:
            lf = F("regular", 36)
            lp_x = pcx1 + 16 + pw + 28
            lp_y = pcy1 + 30
            draw.text((lp_x, lp_y), list_price, font=lf, fill=(140, 140, 140))
            lpw, lph = text_size(draw, list_price, lf)
            draw.line((lp_x, lp_y + lph // 2, lp_x + lpw, lp_y + lph // 2),
                      fill=(140, 140, 140), width=3)

    # CTA — yellow pill button with bold black text
    btn_y1, btn_y2 = PIN_H - 220, PIN_H - 110
    rounded_rect(draw, (pad_x, btn_y1, PIN_W - pad_x, btn_y2),
                 radius=55, fill=ORANGE + (255,))
    cta = product.get("_cta", "Shop on Amazon  \u2192")
    cf = F("extrabold", 50)
    cw, ch = text_size(draw, cta, cf)
    draw.text(((PIN_W - cw) // 2, btn_y1 + (btn_y2 - btn_y1 - ch) // 2 - 4),
              cta, font=cf, fill=(35, 23, 0))

    # Footer
    ff = F("semibold", 22)
    foot = "nexora-shop-us.netlify.app"
    fw, fh = text_size(draw, foot, ff)
    draw.text(((PIN_W - fw) // 2, PIN_H - 70), foot, font=ff, fill=(255, 255, 255, 220))

    return canvas.convert("RGB")


# ─── COPY (TITLE / DESCRIPTION) FOR PINTEREST ─────────────────────────────────

def make_pin_title(product: dict) -> str:
    """Pinterest pin title (max 100 chars). Punchy, with category prefix."""
    cat = product.get("category", "").lower()
    label = {
        "tech": "Smart Tech Find",
        "home": "Home Essential",
        "beauty": "Beauty Pick",
        "pet": "Pet Lovers",
    }.get(cat, "Amazon Find")

    raw = normalize_punct(product.get("title", ""))
    discount = (product.get("discount") or "").strip()
    prefix = f"{label} ({discount} OFF): " if discount and re.search(r"\d", discount) else f"{label}: "

    budget = 100 - len(prefix)
    short = shorten_title(raw, max(40, budget))
    title = prefix + short
    if len(title) > 100:
        title = title[:97].rsplit(" ", 1)[0] + "…"
    return title


def make_pin_description(product: dict) -> str:
    """Pinterest description (max ~500 chars). 2-3 sentences + hashtags."""
    cat = CATEGORIES.get(product.get("category", "").lower(), CATEGORIES["tech"])
    short = shorten_title(normalize_punct(product.get("title", "")), 100)
    price = (product.get("price") or "").strip()
    rating = (product.get("rating") or "").strip()
    review_count = (product.get("reviewCount") or "").strip()
    social = (product.get("socialProof") or "").strip()
    discount = (product.get("discount") or "").strip()

    bits = [f"✨ {short}"]
    if price:
        prefix = f"💰 Now {price}"
        if discount and re.search(r"\d", discount):
            prefix += f" — {discount} OFF"
        bits.append(prefix + ".")
    if rating:
        if review_count:
            bits.append(f"⭐ {rating} stars ({review_count} reviews).")
        else:
            bits.append(f"⭐ {rating} stars.")
    if social:
        bits.append(f"🔥 {social}.")
    bits.append("Curated by NEXORA — Smart Amazon finds, handpicked for everyday life. As an Amazon Associate, NEXORA earns from qualifying purchases.")

    # Allow per-product hashtag overrides (used by v2 to inject seasonal tags)
    hashtags = product.get("_hashtags_override") or cat["hashtags"]
    tags = " ".join(hashtags)
    desc = " ".join(bits) + " " + tags
    return desc[:495]


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default=str(DEFAULT_PRODUCTS_JS),
                    help="Path to products.js")
    ap.add_argument("--limit", type=int, default=0,
                    help="Generate only the first N pins (0 = all)")
    ap.add_argument("--site", default="https://nexora-shop-us.netlify.app",
                    help="Site URL (used in CSV metadata)")
    ap.add_argument("--style", default="mix",
                    choices=["bold-dark", "minimalist", "luxe", "vibrant", "mix"],
                    help="Pin design style. 'mix' rotates through all 4 styles per category "
                         "for visual variety (recommended — helps Pinterest treat pins as fresh).")
    args = ap.parse_args()

    products_path = Path(args.products).resolve()
    if not products_path.exists():
        print(f"ERROR: products.js not found at {products_path}")
        sys.exit(1)

    products = load_products(products_path)
    if args.limit and args.limit > 0:
        products = products[: args.limit]

    PINS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    F = fonts()

    rows = []
    print(f"📌 Generating {len(products)} Pinterest pins from {products_path.name} ...")
    print(f"   Output: {PINS_DIR}")
    print()

    for i, product in enumerate(products, start=1):
        cat_key = (product.get("category") or "tech").lower()
        cat = CATEGORIES.get(cat_key, CATEGORIES["tech"])
        cat_dir = PINS_DIR / cat_key
        cat_dir.mkdir(parents=True, exist_ok=True)

        slug = slugify(product.get("title", "product"), 40)
        filename = f"{i:02d}_{slug}.png"
        out_path = cat_dir / filename

        print(f"  [{i:02d}/{len(products)}] {cat['emoji']} {cat_key:6s} → {filename}")
        # Pick style: explicit single style, or rotate per category for variety.
        if args.style == "mix":
            cat_order = {
                "tech":   ["bold-dark", "vibrant", "minimalist", "luxe"],
                "home":   ["minimalist", "vibrant", "bold-dark", "luxe"],
                "beauty": ["luxe", "minimalist", "vibrant", "bold-dark"],
                "pet":    ["vibrant", "bold-dark", "minimalist", "luxe"],
            }
            order = cat_order.get(cat_key, ["bold-dark", "minimalist", "luxe", "vibrant"])
            cat_seen = sum(1 for r in rows if r.get("_cat") == cat_key)
            chosen_style = order[cat_seen % len(order)]
        else:
            chosen_style = args.style

        try:
            pin = make_pin(product, F, style=chosen_style)
            pin.save(out_path, "PNG", optimize=True)
        except Exception as e:
            print(f"      ✗ Failed: {e}")
            continue

        rows.append({
            "Title": make_pin_title(product),
            "Pin description": make_pin_description(product),
            "Link": product.get("link", args.site),
            "Image file": f"{cat_key}/{filename}",
            "Board": cat["board"],
            "Keywords": ", ".join(t.lstrip("#") for t in cat["hashtags"]),
            "_cat": cat_key,
            "_style": chosen_style,
        })

    # CSV (drop internal _cat / _style fields before writing)
    if rows:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        public_fields = [k for k in rows[0].keys() if not k.startswith("_")]
        with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=public_fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in public_fields})

        # Style distribution summary
        from collections import Counter
        styles_used = Counter(r["_style"] for r in rows)
        print()
        print("Style distribution:")
        for st, n in styles_used.most_common():
            print(f"   • {st:12s} — {n:2d} pins")
        print()
        print(f"✅ Saved {len(rows)} pins to: {PINS_DIR}")
        print(f"✅ Saved CSV to:               {CSV_PATH}")
        print()
        print("Next steps:")
        print("  1. Open output/nexora_pins.csv to review titles & descriptions.")
        print("  2. Open output/pins/ — upload PNGs to Pinterest (Bulk Create or one by one).")
        print("  3. Match each PNG to its row in the CSV (same number prefix).")


if __name__ == "__main__":
    main()
