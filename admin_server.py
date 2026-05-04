#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXORA Admin Server
Local server that:
1. Serves the admin panel UI
2. Scrapes Amazon product data
3. Reads/writes products.json
4. Updates index.html on GitHub via API

Usage:
  python admin_server.py
  Then open: http://localhost:8000/admin
"""

import asyncio
import json
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[!] Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[!] Run: pip install beautifulsoup4")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────
PORT = 8000
PRODUCTS_FILE = Path("products.json")
INDEX_FILE = Path("index.html")
AFFILIATE_TAG = "kareemelsay0b-20"

CATEGORIES = {
    "kitchen": "Kitchen & Home",
    "electronics": "Electronics",
    "health": "Health & Fitness",
    "beauty": "Beauty",
    "fashion": "Fashion",
    "books": "Books",
    "featured": "Featured Products",
}

# ─── Helpers ──────────────────────────────────────────────
def clean_text(text):
    if not text:
        return ""
    text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def load_products():
    if PRODUCTS_FILE.exists():
        try:
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8", errors="ignore") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def guess_category(title):
    t = title.lower()
    if any(w in t for w in ["rice cooker", "air fryer", "blender", "coffee", "kitchen", "instant pot", "cookware", "oven", "toaster"]):
        return "kitchen"
    if any(w in t for w in ["laptop", "phone", "tablet", "headphone", "speaker", "camera", "watch", "monitor", "keyboard", "mouse", "router"]):
        return "electronics"
    if any(w in t for w in ["vitamin", "supplement", "protein", "health", "fitness", "gym", "yoga", "weight"]):
        return "health"
    if any(w in t for w in ["cream", "serum", "moisturizer", "shampoo", "perfume", "makeup", "skincare"]):
        return "beauty"
    if any(w in t for w in ["book", "novel", "guide", "journal"]):
        return "books"
    return "featured"


# ─── Amazon Scraper ───────────────────────────────────────
async def scrape_product(url):
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
    asin = asin_match.group(1) if asin_match else ""
    affiliate_url = f"https://www.amazon.com/dp/{asin}?tag={AFFILIATE_TAG}" if asin else url

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()
        await page.goto(affiliate_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        content = await page.content()
        await browser.close()

    soup = BeautifulSoup(content, "html.parser")
    product = {}

    # Title
    title_el = soup.select_one("#productTitle")
    product["title"] = clean_text(title_el.get_text()) if title_el else "Unknown Product"

    # Price
    price = ""
    pw = soup.select_one(".a-price-whole")
    pf = soup.select_one(".a-price-fraction")
    if pw:
        whole = clean_text(pw.get_text()).replace(",", "").replace(".", "")
        frac = clean_text(pf.get_text()) if pf else "00"
        price = f"${whole}.{frac}"
    if not price:
        pe = soup.select_one(".a-offscreen")
        if pe:
            price = clean_text(pe.get_text())
    product["price"] = price or "Check on Amazon"

    # Rating
    re_el = soup.select_one("#acrPopover")
    if re_el:
        rt = clean_text(re_el.get("title", "") or re_el.get_text())
        m = re.search(r"([\d\.]+)", rt)
        product["rating"] = m.group(1) if m else "4.5"
    else:
        product["rating"] = "4.5"

    # Reviews
    rv_el = soup.select_one("#acrCustomerReviewText")
    if rv_el:
        m = re.search(r"([\d,]+)", clean_text(rv_el.get_text()))
        product["reviews"] = m.group(1) if m else "0"
    else:
        product["reviews"] = "0"

    # Image
    image_url = ""
    img_el = soup.select_one("#landingImage, #imgBlkFront")
    if img_el:
        dd = img_el.get("data-a-dynamic-image", "")
        if dd:
            try:
                img_data = json.loads(dd)
                image_url = max(img_data.keys(), key=lambda k: img_data[k][0] * img_data[k][1])
            except Exception:
                pass
        if not image_url:
            image_url = img_el.get("src", "") or img_el.get("data-src", "")
    if not image_url:
        for script in soup.find_all("script"):
            st = script.get_text() or ""
            m = re.search(r'"large":"(https://[^"]+\.jpg)"', st)
            if m:
                image_url = m.group(1)
                break
    product["image"] = clean_text(image_url)

    # Bullets
    bullets = []
    for b in soup.select("#feature-bullets li span.a-list-item")[:5]:
        t = clean_text(b.get_text())
        if t and len(t) > 5:
            bullets.append(t[:150])
    product["bullets"] = bullets

    product["asin"] = asin
    product["url"] = affiliate_url
    product["category"] = guess_category(product["title"])
    product["id"] = asin or datetime.now().strftime("%Y%m%d%H%M%S")
    product["added_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    return product


# ─── HTML Generator ───────────────────────────────────────
def generate_card(p):
    try:
        rating = float(p.get("rating", 0))
        full = int(rating)
        half = 1 if (rating - full) >= 0.5 else 0
        empty = 5 - full - half
        stars = "&#9733;" * full + "&#9734;" * half + "&#9734;" * empty
    except Exception:
        stars = "&#9733;&#9733;&#9733;&#9733;&#9734;"

    safe_title = p["title"].replace("<", "&lt;").replace(">", "&gt;")[:100]
    safe_price = p["price"].replace("<", "&lt;").replace(">", "&gt;")

    return f'''<div class="product-card" data-id="{p['id']}" data-category="{p['category']}">
  <div class="product-img-wrap">
    <img src="{p['image']}" alt="{safe_title}" loading="lazy" onerror="this.src='https://via.placeholder.com/300x300?text=No+Image'" />
  </div>
  <div class="product-body">
    <h3 class="product-title">{safe_title}</h3>
    <div class="product-rating">
      <span class="stars" style="color:#f5a623">{stars}</span>
      <span class="reviews" style="color:#888;font-size:13px"> ({p['reviews']} reviews)</span>
    </div>
  </div>
  <div class="product-footer">
    <span class="product-price">{safe_price}</span>
    <a href="{p['url']}" target="_blank" rel="nofollow noopener" class="btn-buy">View on Amazon</a>
  </div>
</div>'''


def rebuild_index_html(products):
    """Rebuild the products section in index.html"""
    if not INDEX_FILE.exists():
        return False

    with open(INDEX_FILE, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    # Group products by category
    by_cat = {}
    for p in products:
        cat = p.get("category", "featured")
        by_cat.setdefault(cat, []).append(p)

    # Build new products sections
    new_sections = ""
    for cat, items in by_cat.items():
        cat_label = CATEGORIES.get(cat, cat.title())
        cards = "\n".join(generate_card(p) for p in items)
        new_sections += f'''
<section class="products-section" id="cat-{cat}">
  <div class="container">
    <h2 class="section-title">{cat_label}</h2>
    <div class="products-grid">
{cards}
    </div>
  </div>
</section>
'''

    # Replace between markers or inject before </main>
    start_marker = "<!-- PRODUCTS-START -->"
    end_marker = "<!-- PRODUCTS-END -->"

    if start_marker in html and end_marker in html:
        start_idx = html.index(start_marker) + len(start_marker)
        end_idx = html.index(end_marker)
        html = html[:start_idx] + "\n" + new_sections + "\n" + html[end_idx:]
    else:
        html = html.replace("</main>", new_sections + "\n</main>")

    with open(INDEX_FILE, "w", encoding="utf-8", errors="ignore") as f:
        f.write(html)
    return True


# ─── HTTP Handler ─────────────────────────────────────────
class AdminHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logs

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/admin", "/admin.html"):
            admin_file = Path("admin.html")
            if admin_file.exists():
                with open(admin_file, "r", encoding="utf-8") as f:
                    self.send_html(f.read())
            else:
                self.send_html("<h1>admin.html not found</h1>", 404)

        elif path == "/api/products":
            self.send_json(load_products())

        elif path == "/api/categories":
            self.send_json(CATEGORIES)

        else:
            self.send_html("<h1>404</h1>", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="ignore")

        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if path == "/api/scrape":
            url = data.get("url", "").strip()
            if not url:
                self.send_json({"error": "No URL provided"}, 400)
                return
            try:
                product = asyncio.run(scrape_product(url))
                self.send_json({"success": True, "product": product})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/api/add_product":
            product = data.get("product", {})
            if not product:
                self.send_json({"error": "No product data"}, 400)
                return
            products = load_products()
            # Update if exists
            existing = next((i for i, p in enumerate(products) if p.get("id") == product.get("id")), None)
            if existing is not None:
                products[existing] = product
            else:
                products.append(product)
            save_products(products)
            rebuild_index_html(products)
            self.send_json({"success": True, "total": len(products)})

        elif path == "/api/delete_product":
            pid = data.get("id", "")
            products = load_products()
            products = [p for p in products if p.get("id") != pid]
            save_products(products)
            rebuild_index_html(products)
            self.send_json({"success": True, "total": len(products)})

        else:
            self.send_json({"error": "Unknown endpoint"}, 404)


# ─── Main ─────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  NEXORA Admin Server")
    print("=" * 55)
    print(f"  URL: http://localhost:{PORT}/admin")
    print(f"  Products file: {PRODUCTS_FILE.absolute()}")
    print(f"  Index file: {INDEX_FILE.absolute()}")
    print("=" * 55)
    print("  Press Ctrl+C to stop")
    print()

    server = HTTPServer(("localhost", PORT), AdminHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")


if __name__ == "__main__":
    main()
