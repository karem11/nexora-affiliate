"""
NEXORA Pinterest Pin Generator v2.0  (Site-Crawler Edition)
=============================================================

What this script does
---------------------
1.  Crawls the LIVE NEXORA site (https://nexora-shop-us.netlify.app by default).
2.  Reads sitemap.xml → finds every /product/<slug>.html URL.
3.  Visits each product page and extracts the data we need from the Schema.org
    JSON-LD that the v3 site builder writes into every product page:
        title, image, current price, original price, discount %,
        rating, review count, category, social-proof line.
4.  Generates a 1000×1500 Pinterest pin per product, rotating through 4 visual
    styles (Bold Dark, Vibrant, Minimalist, Luxe) so the feed never looks
    repetitive.
5.  Writes every pin into its **own folder** — copy/paste-friendly:

        output_v2/upload/
          account1_morning/
              tech/
                  01_voice-remote-control-…/
                      pin.png
                      title.txt
                      description.txt
                      link.txt          ← NEXORA product page (not Amazon!)
                      board.txt
                      info.txt
              home/...
          account2_night/
              beauty/...
              pet/...

6.  Generates two convenience CSVs (one per account) for Pinterest Bulk Create.

Why v2
------
v1 read products.js and pointed pins straight at Amazon. v2 points each pin
at its NEXORA product page so that Pinterest traffic flows through the site
(SEO, branding, analytics) before it converts on Amazon.

Usage
-----
    pip install Pillow                        # one-time
    python nexora_pinterest_v2.py             # default — crawls live site
    python nexora_pinterest_v2.py --limit 5   # quick test with 5 pins
    python nexora_pinterest_v2.py --site https://your-other-domain.com
    python nexora_pinterest_v2.py --output ./my_output

The script is fully self-contained — it imports the rendering helpers from
nexora_pinterest_generator.py so the visual style stays identical to v1.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

# Reuse all the rendering / styling helpers from v1 ---------------------------
HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
try:
    from nexora_pinterest_generator import (  # noqa: E402
        CATEGORIES, fonts, fetch_image, make_pin,
        make_pin_title, make_pin_description, slugify,
        normalize_punct, shorten_title,
        FAILED_IMAGES, report_failed_images,
    )
except ImportError as exc:
    print("ERROR: Could not import nexora_pinterest_generator.py.")
    print("       Make sure this script lives next to it.")
    print(f"       Detail: {exc}")
    sys.exit(1)

# v2 extra styles (magazine, headline, splash) live in their own module
try:
    from nexora_pin_styles_v2 import make_pin_v2, EXTRA_STYLE_MAP  # noqa: E402
except ImportError as exc:
    print("ERROR: Could not import nexora_pin_styles_v2.py.")
    print("       Make sure this script lives next to it.")
    print(f"       Detail: {exc}")
    sys.exit(1)


# ─── CONFIG ────────────────────────────────────────────────────────────────────

DEFAULT_SITE = "https://nexora-shop-us.netlify.app"
DEFAULT_OUTPUT_DIR = HERE / "output_v2"

USER_AGENT = (
    "Mozilla/5.0 (compatible; NEXORA-PinterestGenerator/2.0; "
    "+https://nexora-shop-us.netlify.app)"
)
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
HTTP_BACKOFF = 2.0  # seconds; doubles each retry

# Account → categories mapping (matches the v1 split the user already approved)
ACCOUNT_CATS = {
    "account1_morning": ["tech", "home"],
    "account2_night":   ["beauty", "pet"],
}
ACCOUNT_LABEL = {
    "account1_morning": "Account 1 — Morning (7-10 AM US)",
    "account2_night":   "Account 2 — Night (8-11 PM US)",
}

# Style rotation per category. v2 extends to 7 styles so each category cycles
# through *every* style — Pinterest's algorithm rewards visual variety.
# Order is intentional: each category leads with the style that suits it best.
STYLE_ROTATION = {
    "tech":   ["bold-dark", "headline", "vibrant", "splash", "magazine", "minimalist", "luxe"],
    "home":   ["minimalist", "magazine", "vibrant", "headline", "splash", "luxe", "bold-dark"],
    "beauty": ["luxe", "magazine", "splash", "minimalist", "headline", "vibrant", "bold-dark"],
    "pet":    ["splash", "vibrant", "headline", "minimalist", "luxe", "bold-dark", "magazine"],
}

# How many top-trending products get a "TOP PICK" star-burst overlay.
HOT_PICK_COUNT = 6


# Seasonal hashtags — appended to descriptions based on the current month so
# the pins are timely (Pinterest indexes hashtags into seasonal feeds).
def get_seasonal_hashtags() -> list[str]:
    """Return up to 4 seasonal hashtags for the current calendar window."""
    from datetime import datetime
    m = datetime.now().month
    if m == 1:
        return ["#newyearnewme", "#wintervibes", "#januaryfinds"]
    if m == 2:
        return ["#valentinesday", "#valentinesgifts", "#februaryfinds"]
    if m in (3, 4):
        return ["#springfinds", "#springvibes", "#easterfinds"]
    if m == 5:
        return ["#mothersday", "#mothersdaygifts", "#springfinds"]
    if m == 6:
        return ["#summerfinds", "#fathersday", "#summervibes"]
    if m in (7, 8):
        return ["#summervibes", "#vacationfinds", "#poolside"]
    if m == 9:
        return ["#fallfinds", "#backtoschool", "#cozyseason"]
    if m == 10:
        return ["#fallfinds", "#halloween", "#cozyhome"]
    if m == 11:
        return ["#blackfriday", "#cybermonday", "#thanksgiving", "#giftguide"]
    if m == 12:
        return ["#christmasgifts", "#stockingstuffers", "#holidayfinds", "#giftguide"]
    return []

# Map breadcrumb category labels (as printed on the site) → internal short keys
CATEGORY_LABEL_TO_KEY = {
    "electronics": "tech",
    "home & kitchen": "home",
    "beauty & personal care": "beauty",
    "pet supplies": "pet",
}


# ─── HTTP HELPERS ──────────────────────────────────────────────────────────────

def http_get(url: str) -> str:
    """GET a URL with retries, sane UA, and clear error messages."""
    last_err: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (404, 410):
                # No point retrying a permanent 4xx
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        if attempt < HTTP_RETRIES:
            wait = HTTP_BACKOFF * (2 ** (attempt - 1))
            print(f"      [retry {attempt}/{HTTP_RETRIES - 1}] {url} → {last_err}; "
                  f"waiting {wait:.0f}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed to GET {url} after {HTTP_RETRIES} attempts: {last_err}")


# ─── SITEMAP & PAGE PARSING ────────────────────────────────────────────────────

def discover_product_urls(site: str) -> list[str]:
    """Read sitemap.xml and return every /product/<slug>.html URL."""
    sitemap_url = site.rstrip("/") + "/sitemap.xml"
    print(f"📥 Fetching {sitemap_url}")
    xml = http_get(sitemap_url)

    # Tiny regex extractor — sitemap is simple enough that we don't need lxml
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    product_urls = [u for u in locs if "/product/" in u]
    if not product_urls:
        raise RuntimeError(
            f"No product URLs found in sitemap {sitemap_url}. "
            "Has the v3 site been deployed yet?"
        )
    return sorted(product_urls)


def discover_hot_urls(site: str) -> set[str]:
    """Read the homepage and return the URLs of the Hot 6 trending products.

    The homepage embeds an ItemList Schema.org block titled 'Trending Now on
    NEXORA' that lists exactly the products shown in the hero grid. We parse
    that JSON-LD block to identify which products should get the TOP PICK
    star-burst overlay on their pin.
    """
    home_url = site.rstrip("/") + "/"
    try:
        html = http_get(home_url)
    except Exception as e:
        print(f"   [warn] Could not fetch homepage to detect Hot 6: {e}")
        return set()

    blocks = _extract_jsonld_blocks(html)
    hot: set[str] = set()
    for b in blocks:
        t = b.get("@type")
        if t != "ItemList" and (not isinstance(t, list) or "ItemList" not in t):
            continue
        name = (b.get("name") or "").lower()
        if "trending" not in name and "hot" not in name:
            continue
        for item in b.get("itemListElement") or []:
            if isinstance(item, dict):
                u = item.get("url") or ""
                if u and "/product/" in u:
                    hot.add(u)
    print(f"   ✓ Hot 6 detection: found {len(hot)} trending URLs")
    return hot


class _MetaImageScraper(HTMLParser):
    """Extracts <meta property='og:image' content='…'> from a product page."""

    def __init__(self) -> None:
        super().__init__()
        self.og_image: str | None = None
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta":
            prop = (a.get("property") or a.get("name") or "").lower()
            if prop == "og:image" and a.get("content"):
                self.og_image = a["content"]
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")


def _extract_jsonld_blocks(html: str) -> list[dict]:
    """Return every JSON-LD object embedded in <script type=application/ld+json> tags.
    Also flattens @graph wrappers (Schema.org's way of bundling multiple items)."""
    blocks: list[dict] = []
    for m in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html, flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict):
                    blocks.append(d)
                    if isinstance(d.get("@graph"), list):
                        blocks.extend(g for g in d["@graph"] if isinstance(g, dict))
        elif isinstance(data, dict):
            blocks.append(data)
            if isinstance(data.get("@graph"), list):
                blocks.extend(g for g in data["@graph"] if isinstance(g, dict))
    return blocks


def _find_product_block(jsonld_blocks: list[dict]) -> dict | None:
    """Pick the JSON-LD block whose @type is 'Product'."""
    for b in jsonld_blocks:
        t = b.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return b
    return None


def _find_breadcrumb_block(jsonld_blocks: list[dict]) -> dict | None:
    for b in jsonld_blocks:
        t = b.get("@type")
        if t == "BreadcrumbList" or (isinstance(t, list) and "BreadcrumbList" in t):
            return b
    return None


def _category_from_breadcrumb(bc: dict | None) -> str:
    """Return one of {tech, home, beauty, pet} from a BreadcrumbList block."""
    if not bc:
        return "tech"
    items = bc.get("itemListElement") or []
    for it in items:
        name = (it.get("name") or "").strip().lower()
        if name in CATEGORY_LABEL_TO_KEY:
            return CATEGORY_LABEL_TO_KEY[name]
    return "tech"


_SOCIAL_RE = re.compile(
    r"(\d[\d,]*K?\+?\s+bought\s+in\s+past\s+month)",
    flags=re.IGNORECASE,
)
_AMAZON_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?amazon\.[a-z.]+/[^"]*)"',
    flags=re.IGNORECASE,
)


def parse_product_page(url: str) -> dict:
    """Crawl a single /product/<slug>.html page and return a product dict
    in the shape the v1 renderer expects."""
    html = http_get(url)

    blocks = _extract_jsonld_blocks(html)
    product_ld = _find_product_block(blocks)
    if not product_ld:
        raise RuntimeError(
            f"No Schema.org Product block found on {url}. "
            "Did the v3 site builder generate this page?"
        )

    # --- core fields -----------------------------------------------------
    title = (product_ld.get("name") or "").strip()
    image_url = ""
    img_field = product_ld.get("image")
    if isinstance(img_field, list) and img_field:
        image_url = img_field[0]
    elif isinstance(img_field, str):
        image_url = img_field

    # offers → price
    price_str = ""
    offers = product_ld.get("offers") or {}
    if isinstance(offers, dict):
        p = offers.get("price")
        if p is not None:
            try:
                price_str = f"${float(p):.2f}"
            except (TypeError, ValueError):
                price_str = str(p)

    # aggregateRating → rating + review count
    rating_str = ""
    reviews_str = ""
    agg = product_ld.get("aggregateRating") or {}
    if isinstance(agg, dict):
        rv = agg.get("ratingValue")
        if rv is not None:
            try:
                rating_str = f"{float(rv):.1f}"
            except (TypeError, ValueError):
                rating_str = str(rv)
        rc = agg.get("reviewCount") or agg.get("ratingCount")
        if rc is not None:
            try:
                reviews_str = f"{int(rc):,}"
            except (TypeError, ValueError):
                reviews_str = str(rc)

    # category → from breadcrumb
    bc = _find_breadcrumb_block(blocks)
    cat_key = _category_from_breadcrumb(bc)

    # original price + discount % from visible HTML
    # The v3 site builder emits the prod-price / prod-list / prod-disc classes
    # in the hero row of every product page.
    original_price = ""
    discount = ""
    op_match = re.search(
        r'class=["\']prod-list["\'][^>]*>\s*\$([0-9]+(?:\.[0-9]+)?)',
        html,
    )
    if op_match:
        original_price = f"${float(op_match.group(1)):.2f}"
    disc_match = re.search(
        r'class=["\']prod-disc["\'][^>]*>\s*([0-9]+%)',
        html,
    )
    if disc_match:
        discount = disc_match.group(1)

    # social proof ("5K+ bought in past month")
    social = ""
    sm = _SOCIAL_RE.search(html)
    if sm:
        social = sm.group(1).strip()

    # The Amazon affiliate link (we keep it for reference; pin link points to NEXORA page)
    amazon_link = ""
    am = _AMAZON_LINK_RE.search(html)
    if am:
        amazon_link = am.group(1).replace("&amp;", "&")

    # og:image fallback
    if not image_url:
        meta = _MetaImageScraper()
        meta.feed(html)
        if meta.og_image:
            image_url = meta.og_image

    return {
        "title": title,
        "image": image_url,
        "price": price_str,
        "originalPrice": original_price,
        "discount": discount,
        "rating": rating_str,
        "reviewCount": reviews_str,
        "socialProof": social,
        "category": cat_key,
        "link": url,                # ← Pinterest pin → NEXORA product page
        "amazonLink": amazon_link,  # ← kept for info.txt only
        # CTAs that match the new destination (NEXORA, not Amazon directly).
        # The renderers in v1 fall back to "Shop on Amazon" if these keys are
        # missing, so v2 explicitly overrides them.
        "_cta": "Shop Now  \u2192",
        "_cta_luxe": "S H O P    N O W",
    }


# ─── PER-PIN FOLDER OUTPUT ─────────────────────────────────────────────────────

def format_description_lines(desc: str) -> str:
    """Turn the single-line description from make_pin_description into a
    nicely-broken multiline block for the description.txt file."""
    EMOJIS = ["✨", "💰", "⭐", "🔥"]
    rest, parts = desc, []
    for em in EMOJIS:
        idx = rest.find(em)
        if idx > 0:
            parts.append(rest[:idx].rstrip())
            rest = rest[idx:]
    parts.append(rest)
    parts = [p.strip() for p in parts if p.strip()]

    last = parts[-1]
    if last.startswith("🔥") or "Curated by" in last or "As an Amazon" in last:
        rest = last
        sub = []
        for marker in ("Curated by", "As an Amazon"):
            i = rest.find(marker)
            if i > 0:
                sub.append(rest[:i].rstrip(" ."))
                rest = rest[i:]
        sub.append(rest)
        sub = [s.strip() for s in sub if s.strip()]
        cleaned: list[str] = []
        for s in sub:
            if "#" in s and not s.startswith("#"):
                main, _, tags = s.partition("#")
                main = main.strip()
                if main:
                    cleaned.append(main)
                cleaned.append("")  # blank line before hashtags
                cleaned.append("#" + tags.strip())
            else:
                cleaned.append(s)
        parts = parts[:-1] + cleaned
    return "\n".join(parts)


def info_txt(product: dict, account_key: str, board: str, title: str,
             description: str, keywords: str, pin_url: str) -> str:
    return f"""\
================================================================
NEXORA Pinterest Pin
================================================================

ACCOUNT       : {ACCOUNT_LABEL[account_key]}
CATEGORY      : {product['category'].upper()}
BOARD         : {board}

----------------------------------------------------------------
TITLE  (paste into Pinterest "Title")
----------------------------------------------------------------
{title}

----------------------------------------------------------------
DESCRIPTION  (paste into Pinterest "Description")
----------------------------------------------------------------
{description}

----------------------------------------------------------------
DESTINATION LINK  (paste into Pinterest "Destination URL")
----------------------------------------------------------------
{pin_url}

(NOTE: this is the NEXORA product page. The visitor lands on
your site first, then clicks Buy on Amazon — that gives you
on-site traffic + SEO authority + Pinterest analytics.)

----------------------------------------------------------------
KEYWORDS / TAGS
----------------------------------------------------------------
{keywords}

================================================================
HOW TO USE THIS FOLDER
================================================================
1. Drag pin.png into Pinterest's "Create Pin" image area.
2. Open title.txt          → copy → paste into "Title".
3. Open description.txt    → copy → paste into "Description".
4. Open link.txt           → copy → paste into "Destination URL".
5. Select board: {board}
6. Click Publish (or Schedule).
================================================================
"""


def write_pin_folder(product: dict, pin_image, account_key: str, idx: int) -> dict:
    """Render the per-pin folder for a single product. Returns a CSV row."""
    cat_key = product["category"]
    cat = CATEGORIES[cat_key]
    board = cat["board"]
    keywords = ", ".join(t.lstrip("#") for t in cat["hashtags"])

    title = make_pin_title(product)
    description = make_pin_description(product)
    description_pretty = format_description_lines(description)

    slug = slugify(product["title"], 50)
    folder_name = f"{idx:02d}_{slug}"

    out_root: Path = product["_out_root"]
    folder = out_root / "upload" / account_key / cat_key / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    pin_path = folder / "pin.png"
    pin_image.save(pin_path, "PNG", optimize=True)

    (folder / "title.txt").write_text(title + "\n", encoding="utf-8")
    (folder / "description.txt").write_text(description_pretty + "\n", encoding="utf-8")
    (folder / "link.txt").write_text(product["link"] + "\n", encoding="utf-8")
    (folder / "board.txt").write_text(board + "\n", encoding="utf-8")
    # Structured metadata for downstream tools (build_make_sheet.py, etc.)
    import json as _json
    (folder / "meta.json").write_text(
        _json.dumps({
            "id":              f"{cat_key}-{idx:02d}",
            "account_key":     account_key,
            "category":        cat_key,
            "board":           board,
            "style":           product.get("_style", ""),
            "is_hot":          bool(product.get("_is_hot", False)),
            "title":           title,
            "description":     description_pretty,
            "destination_url": product["link"],
            "amazon_link":     product.get("amazonLink", ""),
            "price":           product.get("price"),
            "rating":          product.get("rating"),
            "reviews":         product.get("reviews"),
            "discount":        product.get("discount"),
            "image_path":      str(pin_path.relative_to(out_root)),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (folder / "info.txt").write_text(
        info_txt(product, account_key, board, title, description_pretty,
                 keywords, product["link"]),
        encoding="utf-8",
    )

    return {
        "Title": title,
        "Pin description": description,
        "Link": product["link"],
        "Image file": f"upload/{account_key}/{cat_key}/{folder_name}/pin.png",
        "Board": board,
        "Keywords": keywords,
        "_account": account_key,
        "_cat": cat_key,
    }


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def assign_account(cat_key: str) -> str:
    for acc, cats in ACCOUNT_CATS.items():
        if cat_key in cats:
            return acc
    return "account1_morning"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=DEFAULT_SITE,
                    help=f"NEXORA site URL (default: {DEFAULT_SITE})")
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR),
                    help=f"Output root directory (default: {DEFAULT_OUTPUT_DIR})")
    ap.add_argument("--limit", type=int, default=0,
                    help="Generate only the first N pins (0 = all). Useful for testing.")
    ap.add_argument("--refresh", action="store_true",
                    help="Only generate pins for products NOT already present in "
                         "output_v2/upload/. Useful when you've added new products "
                         "and don't want to re-render existing ones.")
    ap.add_argument("--no-seasonal", action="store_true",
                    help="Skip seasonal hashtags (Mother's Day, Black Friday, etc.).")
    ap.add_argument("--styles", default="all",
                    help="Comma-separated styles to use, or 'all' (default). "
                         "Valid: bold-dark, vibrant, minimalist, luxe, magazine, "
                         "headline, splash. Example: --styles bold-dark,headline,luxe")
    args = ap.parse_args()

    site = args.site.rstrip("/")
    out_root = Path(args.output).resolve()

    print()
    print("=" * 64)
    print(" NEXORA Pinterest Pin Generator v2.0  (Site Crawler Edition)")
    print("=" * 64)
    print(f" Site:   {site}")
    print(f" Output: {out_root}")
    print()

    # 1) Discover URLs (and Hot 6)
    try:
        urls = discover_product_urls(site)
    except Exception as e:
        print(f"✗ Could not read sitemap: {e}")
        sys.exit(2)

    hot_urls = discover_hot_urls(site)

    # Style filter
    valid_styles = {"bold-dark", "vibrant", "minimalist", "luxe",
                    "magazine", "headline", "splash"}
    style_filter: set[str] | None = None
    if args.styles and args.styles != "all":
        requested = {s.strip() for s in args.styles.split(",") if s.strip()}
        bad = requested - valid_styles
        if bad:
            print(f"✗ Unknown styles: {sorted(bad)}. Valid: {sorted(valid_styles)}")
            sys.exit(2)
        style_filter = requested

    # Seasonal hashtags
    seasonal_tags: list[str] = [] if args.no_seasonal else get_seasonal_hashtags()
    if seasonal_tags:
        print(f"   ✓ Seasonal hashtags: {' '.join(seasonal_tags)}")

    if args.limit and args.limit > 0:
        urls = urls[: args.limit]
    print(f"   Found {len(urls)} product URLs in sitemap.xml")
    print()

    # Refresh mode: skip URLs that already have a per-pin folder
    if args.refresh:
        existing_slugs: set[str] = set()
        upload_root = out_root / "upload"
        if upload_root.exists():
            for sub in upload_root.rglob("*"):
                if sub.is_dir() and re.match(r"^\d{2}_", sub.name):
                    existing_slugs.add(sub.name.split("_", 1)[1])
        before = len(urls)
        urls = [u for u in urls if slugify(u.rsplit("/", 1)[-1].replace(".html", ""), 50)
                not in existing_slugs]
        print(f"   ↻ Refresh mode: skipping {before - len(urls)} already-rendered "
              f"products. {len(urls)} new to render.")
        print()
        if not urls:
            print("✓ Nothing new to render. Existing pack is up-to-date.")
            return

    # 2) Crawl each product page
    products: list[dict] = []
    for i, url in enumerate(urls, start=1):
        print(f"  [{i:02d}/{len(urls)}] Reading {url.replace(site, '')}")
        try:
            p = parse_product_page(url)
        except Exception as e:
            print(f"      ✗ Skipping: {e}")
            continue
        # Sanity checks
        if not p["title"] or not p["image"]:
            print(f"      ✗ Missing title/image; skipping")
            continue
        p["_out_root"] = out_root

        # Mark Hot 6 products so they get the TOP PICK overlay
        if url in hot_urls or p["link"] in hot_urls:
            p["_is_hot"] = True
            p["_hot_label"] = "TOP\nPICK"

        # Inject seasonal hashtags into the description hashtag list. The
        # generator's make_pin_description() reads CATEGORIES[cat]["hashtags"] —
        # so we patch the per-product hashtag list right here.
        if seasonal_tags:
            base_tags = list(CATEGORIES.get(p["category"], CATEGORIES["tech"])["hashtags"])
            # Replace the last 1-2 hashtags with seasonal ones to keep total ≤ 5
            keep = max(1, 5 - len(seasonal_tags))
            p["_hashtags_override"] = base_tags[:keep] + seasonal_tags[: 5 - keep]

        products.append(p)

    if not products:
        print("✗ No usable products found. Nothing to generate.")
        sys.exit(3)

    hot_n = sum(1 for p in products if p.get("_is_hot"))
    print()
    print(f"   ✓ Crawled {len(products)} products successfully")
    if hot_n:
        print(f"   ✓ {hot_n} of them are HOT (will get TOP PICK star-burst)")
    print()

    # 3) Sort: tech first, then home, beauty, pet (so per-account numbering is clean)
    cat_order = {"tech": 0, "home": 1, "beauty": 2, "pet": 3}
    products.sort(key=lambda x: (cat_order.get(x["category"], 99), x["title"]))

    # 4) Render pins → per-pin folders
    F = fonts()
    rows: list[dict] = []
    print("📌 Rendering pins ...")
    print()

    # Reset the upload tree so re-runs are clean (unless --refresh)
    upload_root = out_root / "upload"
    if upload_root.exists() and not args.refresh:
        import shutil
        shutil.rmtree(upload_root)

    cat_counter: Counter[str] = Counter()
    cat_seen: Counter[str] = Counter()
    for p in products:
        cat_counter[p["category"]] += 1

    for p in products:
        cat_key = p["category"]
        cat = CATEGORIES.get(cat_key, CATEGORIES["tech"])
        account_key = assign_account(cat_key)

        # Per-account, per-category numbering
        acc_idx = sum(1 for r in rows if r["_account"] == account_key) + 1

        order = STYLE_ROTATION.get(cat_key, ["bold-dark", "minimalist", "luxe", "vibrant"])
        if style_filter:
            order = [s for s in order if s in style_filter] or list(style_filter)
        chosen_style = order[cat_seen[cat_key] % len(order)]
        cat_seen[cat_key] += 1

        try:
            pin = make_pin_v2(p, F, style=chosen_style)
        except Exception as e:
            print(f"  ✗ Pin render failed for '{p['title'][:50]}': {e}")
            continue

        # Tag the product so write_pin_folder can persist style/is_hot to meta.json
        p["_style"] = chosen_style
        row = write_pin_folder(p, pin, account_key, acc_idx)
        row["_style"] = chosen_style
        rows.append(row)

        hot_marker = " 🔥" if p.get("_is_hot") else "  "
        print(f"  [{acc_idx:02d}]{hot_marker}{cat['emoji']} {cat_key:6s} "
              f"({chosen_style:11s}) → {p['title'][:55]}")

    if not rows:
        print("✗ Nothing was rendered. Aborting.")
        sys.exit(4)

    # 5) Convenience CSVs (one per account)
    public_fields = [k for k in rows[0].keys() if not k.startswith("_")]
    csv_dir = out_root / "bulk_create_csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    for acc_key in ACCOUNT_CATS:
        acc_rows = [r for r in rows if r["_account"] == acc_key]
        if not acc_rows:
            continue
        path = csv_dir / f"csv_{acc_key}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=public_fields)
            w.writeheader()
            for r in acc_rows:
                w.writerow({k: r[k] for k in public_fields})
        print(f"  ✓ {path.relative_to(out_root)}  ({len(acc_rows)} pins)")

    # 6) Summary
    style_dist = Counter(r["_style"] for r in rows)
    cat_dist = Counter(r["_cat"] for r in rows)
    acc_dist = Counter(r["_account"] for r in rows)
    print()
    print("─" * 64)
    print(f" ✓ Generated {len(rows)} pins")
    print()
    print("  By account:")
    for acc, n in acc_dist.most_common():
        print(f"     • {ACCOUNT_LABEL[acc]:48s} {n:3d}")
    print("  By category:")
    for cat, n in cat_dist.most_common():
        emoji = CATEGORIES[cat]["emoji"]
        print(f"     • {emoji} {cat:8s}                                       {n:3d}")
    print("  By style:")
    for st, n in style_dist.most_common():
        print(f"     • {st:14s}                                  {n:3d}")
    print()
    print(f" Output root:   {out_root}")
    print(f" Per-pin pkgs:  {out_root / 'upload'}")
    print(f" Bulk CSVs:     {out_root / 'bulk_create_csv'}")
    print("─" * 64)

    # If any product images failed to download, surface a clear summary so
    # the user knows which pins might be missing the product photo.
    report_failed_images()


if __name__ == "__main__":
    main()
