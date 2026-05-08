"""NEXORA v3 — Amazon-compliant site builder (Phase 1).

Reads `data/products.json` (clean v3 format) and generates:
  * website/index.html              → Homepage with category cards + featured products
  * website/category/<key>.html     → Category listing pages
  * website/product/<slug>.html     → Compliant product detail pages
  * website/sitemap.xml             → Updated sitemap
  * website/robots.txt              → SEO basics

Compliance with Amazon Associates TOS:
  ✗ NO static prices, ratings, reviews, discounts, or social proof
  ✗ NO `offers.price` or `aggregateRating` in schema.org JSON-LD
  ✓ Uses viral_title (Phase 2 AI) with fallback to amazon_title
  ✓ Uses AI hero image (Phase 2) with fallback to original image
  ✓ Affiliate disclosure on every page
  ✓ Trust-focused CTAs ("Check Today's Deal", "View on Amazon", etc.)

Usage:
    python site_builder_v3/builder.py
    python site_builder_v3/builder.py --site /path/to/website
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SITE = ROOT / "website"
DEFAULT_DATA = ROOT / "data" / "products.json"

# ──────────────────────────────────────────────────────────────────────────────
# Brand constants
# ──────────────────────────────────────────────────────────────────────────────
SITE_URL = "https://nexora-shop-us.netlify.app"
BRAND = "NEXORA"
TAGLINE = "Smart Finds. Better Life."
LOGO_URL = "https://f.top4top.io/p_3776hn9nu1.png"
EMAIL = "karemali11@gmail.com"
TODAY = datetime.now(timezone.utc).strftime("%B %d, %Y")
TODAY_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%d")

CATEGORIES = {
    "tech": {
        "name": "Electronics",
        "icon": "⚡",
        "color": "#2176ff",
        "label": "Tech",
        "blurb": "Smart gadgets, accessories, and trending tech finds.",
    },
    "home": {
        "name": "Home & Kitchen",
        "icon": "🏠",
        "color": "#ff6b35",
        "label": "Home",
        "blurb": "Home essentials and kitchen upgrades that real people love.",
    },
    "beauty": {
        "name": "Beauty & Self-Care",
        "icon": "💄",
        "color": "#e91e63",
        "label": "Beauty",
        "blurb": "Skincare, haircare, and self-care picks worth trying.",
    },
    "pet": {
        "name": "Pet Supplies",
        "icon": "🐾",
        "color": "#10b981",
        "label": "Pet",
        "blurb": "Toys, treats, and gear that pet parents actually buy.",
    },
}

FEATURED_COUNT = 6     # Featured products on homepage
LATEST_COUNT = 6       # Latest finds strip on homepage
RELATED_COUNT = 3      # Related products on each product page

# CTA rotation pool (matches scripts_v3/01_clean_products.py)
CTA_POOL = [
    "Check Today's Deal",
    "View on Amazon",
    "See Why It's Trending",
    "Check Availability",
]
CTA_SECONDARY_POOL = [
    "People love this",
    "Trending right now",
    "Popular pick this week",
    "Top viral find",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def slugify(text: str, max_len: int = 70) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "product"


def display_title(p: dict) -> str:
    """Use viral_title if Phase 2 has populated it, else fall back to amazon_title."""
    return (p.get("viral_title") or p.get("amazon_title") or "").strip()


def display_hook(p: dict) -> str:
    """Phase 2 will populate hook. For now, an empty string."""
    return (p.get("hook") or "").strip()


def display_image(p: dict) -> str:
    """Use AI hero image (Phase 2) when available, else original Amazon image."""
    return (p.get("ai_hero_image") or p.get("image") or "").strip()


def product_url(p: dict, *, absolute: bool = False) -> str:
    slug = p.get("slug") or slugify(display_title(p))
    rel = f"/product/{slug}.html"
    return f"{SITE_URL}{rel}" if absolute else rel


def category_url(cat: str, *, absolute: bool = False) -> str:
    rel = f"/category/{cat}.html"
    return f"{SITE_URL}{rel}" if absolute else rel


def category_meta(cat: str) -> dict:
    return CATEGORIES.get(cat, {
        "name": cat.title(),
        "icon": "🛍",
        "color": "#888",
        "label": cat.title(),
        "blurb": "",
    })


def get_cta(p: dict, *, primary: bool = True) -> str:
    if primary:
        return (p.get("cta_primary") or CTA_POOL[0]).strip()
    return CTA_SECONDARY_POOL[0]


# ──────────────────────────────────────────────────────────────────────────────
# Schema.org JSON-LD (COMPLIANT — no aggregateRating, no offers)
# ──────────────────────────────────────────────────────────────────────────────
def schema_product(p: dict) -> str:
    """Compliant Product schema — NO offers.price, NO aggregateRating."""
    title = display_title(p)
    obj = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": display_image(p),
        "description": (display_hook(p) or title)[:500],
        "url": product_url(p, absolute=True),
        "brand": {"@type": "Brand", "name": BRAND},
        "category": category_meta(p.get("category", "")).get("name", ""),
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def schema_breadcrumb(items: list[tuple[str, str]]) -> str:
    elements = []
    for i, (name, url) in enumerate(items, start=1):
        full = url if url.startswith("http") else f"{SITE_URL}{url}"
        elements.append({
            "@type": "ListItem",
            "position": i,
            "name": name,
            "item": full,
        })
    obj = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def schema_itemlist(products: list[dict], list_name: str = "Trending Products") -> str:
    items = []
    for i, p in enumerate(products, start=1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "url": product_url(p, absolute=True),
            "name": display_title(p),
        })
    obj = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": list_name,
        "itemListElement": items,
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ──────────────────────────────────────────────────────────────────────────────
# Shared HTML chunks
# ──────────────────────────────────────────────────────────────────────────────
def head_block(
    *,
    title: str,
    description: str,
    canonical: str,
    og_image: str | None = None,
    keywords: str | None = None,
    extra_schema: str = "",
) -> str:
    og_img = og_image or LOGO_URL
    keywords_meta = (
        f'<meta name="keywords" content="{esc(keywords)}" />\n' if keywords else ""
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="robots" content="index,follow,max-image-preview:large" />
<meta name="theme-color" content="#06111f" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}" />
{keywords_meta}<meta name="author" content="{BRAND}" />
<link rel="canonical" href="{esc(canonical)}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="{BRAND}" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(description)}" />
<meta property="og:url" content="{esc(canonical)}" />
<meta property="og:image" content="{esc(og_img)}" />
<meta property="og:locale" content="en_US" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(title)}" />
<meta name="twitter:description" content="{esc(description)}" />
<meta name="twitter:image" content="{esc(og_img)}" />
<link rel="icon" type="image/png" href="{LOGO_URL}" />
<link rel="apple-touch-icon" href="{LOGO_URL}" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="/site.css" />
{extra_schema}
</head>
<body>
"""


HEADER_HTML = f"""\
<!-- Hidden form for Netlify Forms detection (real form is on /contact). -->
<form name="contact" netlify netlify-honeypot="bot-field" hidden>
  <input type="text" name="name" /><input type="email" name="email" />
  <input type="text" name="subject" /><textarea name="message"></textarea>
</form>
<header>
  <div class="container nav-inner">
    <a href="/" class="brand">
      <img src="{LOGO_URL}" alt="{BRAND}" class="brand-logo" />
      <span class="brand-text">
        <span class="brand-name">{BRAND}</span>
        <span class="brand-tag">{TAGLINE}</span>
      </span>
    </a>
    <nav class="nav-links">
      <a href="/">Home</a>
      <a href="/category/tech.html">Tech</a>
      <a href="/category/home.html">Kitchen</a>
      <a href="/category/beauty.html">Beauty</a>
      <a href="/category/pet.html">Pet</a>
      <a href="/about.html">About</a>
      <a href="/contact.html">Contact</a>
    </nav>
  </div>
</header>
<div class="aff-banner">
  <div class="container">
    <p>📢 As an Amazon Associate, {BRAND} earns from qualifying purchases — at no extra cost to you.
    <a href="/disclosure.html">Learn more</a></p>
  </div>
</div>
"""


def footer_html() -> str:
    return f"""\
<footer>
  <div class="container">
    <div class="footer-top">
      <a href="/" class="footer-brand">
        <img src="{LOGO_URL}" alt="{BRAND}" />
        <span>{BRAND}</span>
      </a>
      <div class="footer-links">
        <div>
          <h6>Shop</h6>
          <a href="/category/tech.html">Electronics</a>
          <a href="/category/home.html">Home &amp; Kitchen</a>
          <a href="/category/beauty.html">Beauty</a>
          <a href="/category/pet.html">Pet Supplies</a>
        </div>
        <div>
          <h6>Company</h6>
          <a href="/about.html">About</a>
          <a href="/contact.html">Contact</a>
        </div>
        <div>
          <h6>Legal</h6>
          <a href="/privacy.html">Privacy Policy</a>
          <a href="/cookies.html">Cookie Policy</a>
          <a href="/disclosure.html">Affiliate Disclosure</a>
          <a href="/terms.html">Terms of Service</a>
        </div>
      </div>
    </div>
    <p class="disclosure">📢 {BRAND} is a participant in the Amazon Services LLC Associates Program, an affiliate
       advertising program designed to provide a means for sites to earn advertising fees by advertising and linking to
       Amazon.com. As an Amazon Associate, {BRAND} earns from qualifying purchases. Product availability,
       pricing and details are determined by Amazon at the time of purchase.</p>
    <p class="disclosure copyright">© {datetime.now().year} {BRAND}. All rights reserved.</p>
  </div>
</footer>
<script src="/cookie-banner.js" defer></script>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Components
# ──────────────────────────────────────────────────────────────────────────────
def render_card(p: dict) -> str:
    """Compliant product card — no prices, no ratings, no review counts."""
    cat = category_meta(p.get("category", ""))
    title = display_title(p)
    img = display_image(p)
    badges_html = ""
    badge = (p.get("badge") or "").strip()
    if badge:
        badges_html = f'<div class="badges"><span class="badge hot">{esc(badge)}</span></div>'

    return f"""\
<a class="card" href="{esc(product_url(p))}">
  <div class="card-img">
    <img loading="lazy" src="{esc(img)}" alt="{esc(title)}" />
    {badges_html}
    <span class="card-cat" style="--catc:{cat['color']}">{cat['icon']} {esc(cat['label'])}</span>
  </div>
  <div class="card-body">
    <h3 class="card-title">{esc(title)}</h3>
    <span class="card-cta">{esc(get_cta(p))} →</span>
  </div>
</a>
"""


def render_category_card(key: str, count: int) -> str:
    meta = CATEGORIES[key]
    return f"""\
<a class="cat-card" href="/category/{key}.html" style="--catc:{meta['color']}">
  <div class="cat-icon">{meta['icon']}</div>
  <div class="cat-name">{esc(meta['name'])}</div>
  <div class="cat-count">{count} products</div>
</a>"""


# ──────────────────────────────────────────────────────────────────────────────
# Page renderers
# ──────────────────────────────────────────────────────────────────────────────
def render_index(products: list[dict]) -> str:
    cat_counts = {c: 0 for c in CATEGORIES}
    for p in products:
        c = p.get("category", "")
        if c in cat_counts:
            cat_counts[c] += 1

    cat_cards = "\n".join(render_category_card(k, cat_counts[k]) for k in CATEGORIES)

    # Featured: first N products (Phase 4 will rank by Nexora Score)
    featured = products[:FEATURED_COUNT]
    featured_cards = "\n".join(render_card(p) for p in featured)

    # Latest: next N
    latest = products[FEATURED_COUNT : FEATURED_COUNT + LATEST_COUNT]
    latest_cards = "\n".join(render_card(p) for p in latest) if latest else ""

    # Schema for ItemList of featured products
    item_schema = (
        f'<script type="application/ld+json">{schema_itemlist(featured, "Trending on NEXORA")}</script>'
    )
    breadcrumb_schema = (
        f'<script type="application/ld+json">{schema_breadcrumb([("Home", "/")])}</script>'
    )

    head = head_block(
        title=f"{BRAND} — {TAGLINE}",
        description="Discover viral product finds, trending gadgets, beauty picks, kitchen upgrades, and pet must-haves. Updated daily by NEXORA.",
        canonical=f"{SITE_URL}/",
        keywords="viral products, trending finds, amazon finds, tiktok products, smart gadgets",
        extra_schema=item_schema + "\n" + breadcrumb_schema,
    )

    body = f"""\
{HEADER_HTML}
<main>
  <section class="hero">
    <div class="container">
      <h1 class="hero-title">Smart Finds. Better Life.</h1>
      <p class="hero-sub">Hand-picked viral products, trending tech, beauty, and home gear — all in one curated place.</p>
      <div class="hero-cta">
        <a href="#featured" class="btn-primary">See Today's Picks →</a>
        <a href="/category/tech.html" class="btn-ghost">Browse Categories</a>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="container">
      <h2 class="section-title">Browse by Category</h2>
      <div class="cat-grid">
        {cat_cards}
      </div>
    </div>
  </section>

  <section id="featured" class="section">
    <div class="container">
      <div class="section-head">
        <h2 class="section-title">🔥 Trending Right Now</h2>
        <p class="section-sub">The top viral picks our community is loving this week.</p>
      </div>
      <div class="card-grid">
        {featured_cards}
      </div>
    </div>
  </section>

  {f'''<section class="section">
    <div class="container">
      <div class="section-head">
        <h2 class="section-title">✨ More Finds</h2>
        <p class="section-sub">Fresh discoveries you might've missed.</p>
      </div>
      <div class="card-grid">
        {latest_cards}
      </div>
    </div>
  </section>''' if latest_cards else ""}

  <section class="section section-cta">
    <div class="container center">
      <h2>Get viral product finds in your inbox</h2>
      <p>One short email per week. No spam, ever.</p>
      <a href="/contact.html" class="btn-primary">Coming Soon →</a>
    </div>
  </section>
</main>
{footer_html()}"""

    return head + body


def render_product(p: dict, all_products: list[dict]) -> str:
    title = display_title(p)
    hook = display_hook(p)
    img = display_image(p)
    cat = p.get("category", "")
    cat_meta = category_meta(cat)
    aff_url = p.get("link", "")

    cta1 = get_cta(p, primary=True)
    cta2 = "View on Amazon"

    # Benefits — Phase 2 will populate via Gemini. For now show generic placeholders.
    benefits = p.get("benefits") or []
    benefits_html = ""
    if benefits:
        items = "".join(f"<li>{esc(b)}</li>" for b in benefits)
        benefits_html = f"""\
<section class="prod-benefits">
  <h3>Why It's Trending</h3>
  <ul>{items}</ul>
</section>"""
    else:
        # Generic compliant placeholders shown until Phase 2 generates AI benefits.
        benefits_html = """\
<section class="prod-benefits">
  <h3>Why It's Trending</h3>
  <ul>
    <li>Hand-picked by our team for quality and real-world use</li>
    <li>Loved by an active community of shoppers</li>
    <li>Easy to order — ships fast via Amazon</li>
  </ul>
</section>"""

    # Related products: same category, exclude self
    related = [
        x for x in all_products
        if x.get("category") == cat and x.get("id") != p.get("id")
    ][:RELATED_COUNT]
    related_html = ""
    if related:
        related_html = f"""\
<section class="section">
  <div class="container">
    <h3 class="section-title">More from {esc(cat_meta['name'])}</h3>
    <div class="card-grid related-grid">
      {"".join(render_card(r) for r in related)}
    </div>
  </div>
</section>"""

    # Schema (compliant)
    breadcrumb = schema_breadcrumb([
        ("Home", "/"),
        (cat_meta["name"], category_url(cat)),
        (title, product_url(p)),
    ])
    extra_schema = (
        f'<script type="application/ld+json">{schema_product(p)}</script>\n'
        f'<script type="application/ld+json">{breadcrumb}</script>'
    )

    seo_title = (
        p.get("seo_title")
        or f"{title[:60]} | {BRAND}"
    )
    meta_desc = (
        p.get("meta_description")
        or hook
        or f"{title[:150]} — discover this trending {cat_meta['label'].lower()} pick on {BRAND}."
    )

    head = head_block(
        title=seo_title,
        description=meta_desc,
        canonical=product_url(p, absolute=True),
        og_image=img,
        keywords=", ".join((p.get("hashtags") or [cat_meta["label"], "trending", "viral", "amazon find"])),
        extra_schema=extra_schema,
    )

    body = f"""\
{HEADER_HTML}
<main>
  <article class="container product-page">
    <nav class="crumbs">
      <a href="/">Home</a> ›
      <a href="/category/{cat}.html">{esc(cat_meta['name'])}</a> ›
      <span>{esc(title[:50])}{"…" if len(title) > 50 else ""}</span>
    </nav>

    <div class="prod-grid">
      <div class="prod-img-wrap">
        <img class="prod-img" src="{esc(img)}" alt="{esc(title)}" />
        <span class="prod-cat-chip" style="--catc:{cat_meta['color']}">
          {cat_meta['icon']} {esc(cat_meta['label'])}
        </span>
      </div>

      <div class="prod-info">
        <span class="trending-badge">🔥 Trending Right Now</span>
        <h1 class="prod-title">{esc(title)}</h1>
        {f'<p class="prod-hook">{esc(hook)}</p>' if hook else ''}

        <a class="cta-primary" href="{esc(aff_url)}"
           target="_blank" rel="nofollow sponsored noopener"
           data-cta-track="primary">
          {esc(cta1)} →
        </a>
        <a class="cta-secondary" href="{esc(aff_url)}"
           target="_blank" rel="nofollow sponsored noopener"
           data-cta-track="secondary">
          {esc(cta2)}
        </a>

        <p class="cta-trust">📢 Affiliate link — we may earn a commission at no extra cost to you.</p>
      </div>
    </div>

    {benefits_html}

    <div class="prod-disclosure">
      <p><strong>Disclosure:</strong> {BRAND} is a participant in the Amazon Services LLC Associates Program.
      As an Amazon Associate, we earn from qualifying purchases. Product availability, pricing, and details are
      determined by Amazon at the time of purchase. <a href="/disclosure.html">Read full disclosure</a>.</p>
    </div>
  </article>

  {related_html}

  <!-- Sticky CTA bar (Phase 6 will enhance) -->
  <a class="sticky-cta" href="{esc(aff_url)}"
     target="_blank" rel="nofollow sponsored noopener"
     data-cta-track="sticky">
    {esc(cta1)} →
  </a>
</main>
{footer_html()}"""

    return head + body


def render_category(cat_key: str, products: list[dict]) -> str:
    meta = CATEGORIES[cat_key]
    cat_products = [p for p in products if p.get("category") == cat_key]
    cards = "\n".join(render_card(p) for p in cat_products)

    breadcrumb = schema_breadcrumb([
        ("Home", "/"),
        (meta["name"], category_url(cat_key)),
    ])
    item_list = schema_itemlist(cat_products, f"{meta['name']} — {BRAND}")
    extra_schema = (
        f'<script type="application/ld+json">{breadcrumb}</script>\n'
        f'<script type="application/ld+json">{item_list}</script>'
    )

    head = head_block(
        title=f"{meta['name']} — Trending Picks | {BRAND}",
        description=meta["blurb"],
        canonical=category_url(cat_key, absolute=True),
        keywords=f"{meta['label'].lower()}, viral products, trending, amazon finds",
        extra_schema=extra_schema,
    )

    body = f"""\
{HEADER_HTML}
<main>
  <section class="cat-hero" style="--catc:{meta['color']}">
    <div class="container">
      <span class="cat-emoji">{meta['icon']}</span>
      <h1>{esc(meta['name'])}</h1>
      <p>{esc(meta['blurb'])}</p>
    </div>
  </section>

  <section class="section">
    <div class="container">
      <h2 class="section-title">{len(cat_products)} Trending {esc(meta['label'])} Picks</h2>
      <div class="card-grid">
        {cards}
      </div>
    </div>
  </section>
</main>
{footer_html()}"""

    return head + body


# ──────────────────────────────────────────────────────────────────────────────
# Sitemap & robots
# ──────────────────────────────────────────────────────────────────────────────
def render_sitemap(products: list[dict]) -> str:
    urls = [
        ("/", "1.0", "daily"),
        ("/about.html", "0.5", "monthly"),
        ("/contact.html", "0.5", "monthly"),
        ("/privacy.html", "0.3", "yearly"),
        ("/terms.html", "0.3", "yearly"),
        ("/disclosure.html", "0.5", "yearly"),
    ]
    for cat in CATEGORIES:
        urls.append((category_url(cat), "0.8", "weekly"))
    for p in products:
        urls.append((product_url(p), "0.7", "weekly"))

    items = "".join(
        f"  <url><loc>{SITE_URL}{u}</loc>"
        f"<lastmod>{TODAY_ISO}</lastmod>"
        f"<changefreq>{cf}</changefreq>"
        f"<priority>{pr}</priority></url>\n"
        for u, pr, cf in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}"
        "</urlset>\n"
    )


def render_robots() -> str:
    return f"""\
User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""


# ──────────────────────────────────────────────────────────────────────────────
# Main build
# ──────────────────────────────────────────────────────────────────────────────
def build(site_dir: Path, data_file: Path) -> None:
    if not data_file.exists():
        print(f"ERROR: data file not found: {data_file}", file=sys.stderr)
        print("Run: python scripts_v3/01_clean_products.py", file=sys.stderr)
        sys.exit(1)

    products = json.loads(data_file.read_text(encoding="utf-8"))
    print(f"Loaded {len(products)} products from {data_file}")

    site_dir.mkdir(parents=True, exist_ok=True)
    # Wipe old product/ and category/ pages — old v2 slugs may differ from v3
    # and could leave non-compliant orphans behind.
    for sub in ("product", "category"):
        d = site_dir / sub
        if d.exists():
            for f in d.glob("*.html"):
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    # Index
    (site_dir / "index.html").write_text(render_index(products), encoding="utf-8")
    print(f"  ✓ index.html")

    # Category pages
    for cat in CATEGORIES:
        out = site_dir / "category" / f"{cat}.html"
        out.write_text(render_category(cat, products), encoding="utf-8")
        print(f"  ✓ category/{cat}.html")

    # Product pages
    for p in products:
        slug = p.get("slug") or slugify(display_title(p))
        out = site_dir / "product" / f"{slug}.html"
        out.write_text(render_product(p, products), encoding="utf-8")
    print(f"  ✓ product/*.html ({len(products)} pages)")

    # Sitemap & robots
    (site_dir / "sitemap.xml").write_text(render_sitemap(products), encoding="utf-8")
    print(f"  ✓ sitemap.xml")
    (site_dir / "robots.txt").write_text(render_robots(), encoding="utf-8")
    print(f"  ✓ robots.txt")

    # Compliance scan
    print("\nRunning compliance scan...")
    forbidden_patterns = [
        (r'\$\d+\.\d{2}', "static price like $X.XX"),
        (r'\d+%\s*off', "discount percentage"),
        (r'★+', "star rating display"),
        (r'\([\d,]+\s+reviews?\)', "review count"),
        (r'bought in (?:the\s+)?past month', "Amazon social proof"),
        (r'aggregateRating', "schema.org aggregateRating"),
        (r'"price"\s*:\s*"', "schema.org offers.price"),
    ]
    issues = 0
    for html_file in site_dir.rglob("*.html"):
        try:
            txt = html_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat, label in forbidden_patterns:
            if re.search(pat, txt):
                # Skip rule for legal pages where dollar examples / disclosure text may legitimately appear
                if html_file.name in {"privacy.html", "terms.html", "disclosure.html"}:
                    continue
                print(f"  ⚠  {html_file.relative_to(site_dir)}: matched '{label}'")
                issues += 1

    if issues == 0:
        print("  ✅ No forbidden patterns detected in generated pages.")
    else:
        print(f"  ⚠  {issues} potential compliance issue(s) found — review above.")

    print(f"\n✅ v3 build complete in {site_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()

    build(args.site.resolve(), args.data.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
