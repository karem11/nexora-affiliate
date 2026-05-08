#!/usr/bin/env python3
"""
Phase 1 / Step 1.2 — Clean products.js for Amazon Associates compliance.

INPUT:  /home/ubuntu/nexora/website/products.js  (current v2.x with prices/ratings)
OUTPUT:
  - /home/ubuntu/nexora/data/products.json       (clean source of truth for v3)
  - /home/ubuntu/nexora/website/products.js      (updated, no forbidden fields)

REMOVES from each product:
  - price, listPrice, discount
  - rating, reviewCount, socialProof
  - copied Amazon descriptions (set placeholder)

KEEPS:
  - title, image, link, category, badge

ADDS placeholder fields for Phase 2 (AI content):
  - viral_title (empty until Gemini generates)
  - hook (empty)
  - benefits (empty list)
  - ai_image (None, will use original image until Pollinations generates)
  - cta_primary (default: "Check Today's Deal")
  - nexora_score: { virality, usefulness, value }  (placeholder 0)
  - id (slug-based)
  - asin (extracted from Amazon URL)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/nexora")
SRC = ROOT / "website" / "products.js"
OUT_JSON = ROOT / "data" / "products.json"
OUT_JS = ROOT / "website" / "products.js"

# CTA rotation pool - assigned deterministically by index
CTA_POOL = [
    "Check Today's Deal",
    "View on Amazon",
    "See Why It's Trending",
    "Check Availability",
]


def parse_products_js(text: str) -> list[dict]:
    """Extract the products array from the JS file (it's basically JSON inside)."""
    # Match: const products = [ ... ];
    m = re.search(r"const\s+products\s*=\s*(\[[\s\S]*?\]);?\s*$", text)
    if not m:
        # Try without trailing semicolon match
        m = re.search(r"const\s+products\s*=\s*(\[[\s\S]*\])", text)
    if not m:
        raise RuntimeError("Could not find 'const products = [...]' in source file")
    arr_text = m.group(1)
    return json.loads(arr_text)


def slugify(text: str, max_len: int = 70) -> str:
    """Make a URL-friendly slug from the product title.
    Matches site_builder_v3/builder.py.slugify() exactly so pages and data agree.
    """
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "product"


def extract_asin(amazon_url: str) -> str | None:
    """Pull the ASIN from an Amazon /dp/<ASIN> URL."""
    m = re.search(r"/dp/([A-Z0-9]{10})", amazon_url)
    return m.group(1) if m else None


# Forbidden fields (Amazon Associates TOS violations)
FORBIDDEN_FIELDS = {
    "price",
    "listPrice",
    "discount",
    "rating",
    "reviewCount",
    "socialProof",
}


def clean_product(p: dict, idx: int) -> dict:
    """Strip forbidden fields and add v3 structure.

    Idempotent: works on both v2.x source (title/description) and v3 source
    (amazon_title/viral_title) so the script can be safely re-run.
    """
    # Accept either v2 ("title") or v3 ("amazon_title") format
    title = (p.get("amazon_title") or p.get("title") or "").strip()
    image = (p.get("image") or "").strip()
    link = (p.get("link") or "").strip()
    category = (p.get("category") or "").strip()
    badge = (p.get("badge") or "").strip()

    asin = extract_asin(link)
    slug = slugify(title)
    pid = asin or slug[:20]

    # Internal-only price tier (used for Value Score calculation later, NEVER displayed).
    # We extract from the OLD price field if present, then drop the field.
    raw_price = p.get("price", "")
    price_tier = None
    if raw_price:
        try:
            num = float(re.sub(r"[^0-9.]", "", raw_price))
            if num < 15:
                price_tier = "low"
            elif num < 50:
                price_tier = "mid"
            else:
                price_tier = "high"
        except ValueError:
            pass

    cta_primary = CTA_POOL[idx % len(CTA_POOL)]

    cleaned = {
        "id": pid,
        "asin": asin,
        "slug": slug,
        # Original Amazon title - kept temporarily until Phase 2 generates a viral version.
        # Site builder MUST NOT display this verbatim once viral_title is populated.
        "amazon_title": title,
        # Phase 2 will populate these via Gemini API:
        "viral_title": "",
        "hook": "",
        "benefits": [],
        "seo_title": "",
        "meta_description": "",
        "pinterest_title": "",
        "pinterest_description": "",
        "tiktok_caption": "",
        "instagram_caption": "",
        "hashtags": [],
        # Images
        "image": image,  # Original Amazon image (allowed under affiliate use)
        "ai_hero_image": None,  # Phase 2: Pollinations generated
        "ai_lifestyle_images": [],  # Phase 2
        # Affiliate
        "link": link,
        "asin_marketplace": "US",
        # Categorization
        "category": category,
        "badge": badge,
        # Phase 4: Nexora Score (placeholder - will be computed later)
        "nexora_score": {
            "virality": 0,
            "usefulness": 0,
            "value": 0,
            "overall": 0,
        },
        # CTA
        "cta_primary": cta_primary,
        # Internal-only — for Value Score calculation. NEVER rendered.
        "_price_tier": price_tier,
        # Compliance flag
        "compliant": True,
    }

    # Sanity check: no forbidden fields leaked
    for f in FORBIDDEN_FIELDS:
        assert f not in cleaned, f"Forbidden field '{f}' leaked into cleaned product"

    return cleaned


def write_products_js(products: list[dict], out: Path) -> None:
    """Write back as products.js (still used by current website until v3 builder is ready)."""
    body = json.dumps(products, indent=2, ensure_ascii=False)
    js = (
        "// NEXORA v3 — Amazon-compliant product data.\n"
        "// Generated by scripts_v3/01_clean_products.py — DO NOT EDIT BY HAND.\n"
        "// Source of truth: /data/products.json\n"
        "// Forbidden fields removed: price, listPrice, discount, rating, reviewCount, socialProof.\n"
        "const products = " + body + ";\n"
    )
    out.write_text(js, encoding="utf-8")


def write_products_json(products: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source not found: {SRC}", file=sys.stderr)
        return 1

    raw = SRC.read_text(encoding="utf-8")
    products = parse_products_js(raw)
    print(f"Loaded {len(products)} products from {SRC}")

    cleaned = [clean_product(p, i) for i, p in enumerate(products)]

    # Write outputs
    write_products_json(cleaned, OUT_JSON)
    write_products_js(cleaned, OUT_JS)

    print(f"  → wrote {OUT_JSON}  ({len(cleaned)} products)")
    print(f"  → wrote {OUT_JS}  ({len(cleaned)} products)")

    # Compliance report
    print("\nCompliance report:")
    print(f"  ✅ Removed forbidden fields: {sorted(FORBIDDEN_FIELDS)}")
    print(f"  ✅ Added v3 placeholders: viral_title, hook, benefits, ai_hero_image, cta_primary, nexora_score")
    print(f"  ⚠ amazon_title still present (will be replaced by viral_title in Phase 2)")
    print(f"  ⚠ image still uses Amazon CDN (allowed under affiliate use; AI image in Phase 2)")

    # Categories breakdown
    from collections import Counter
    cats = Counter(p["category"] for p in cleaned)
    print("\nCategories:")
    for cat, count in cats.most_common():
        print(f"  {cat or '(none)':10s} → {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
