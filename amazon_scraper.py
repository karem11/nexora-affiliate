#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXORA Amazon Product Scraper v3 - Fixed Unicode Edition
Scrapes Amazon product data using Playwright and generates HTML cards.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[!] playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[!] beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    sys.exit(1)


def clean_text(text):
    """Remove surrogate characters and clean text for UTF-8 encoding."""
    if not text:
        return ""
    # Remove surrogate characters
    text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    # Remove non-printable characters except newlines
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()


async def scrape_amazon_product(url):
    """Scrape product data from Amazon using Playwright."""
    print(f"[*] Opening Amazon product page...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
        )
        
        page = await context.new_page()
        
        print(f"[*] Navigating to URL...")
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(3)
        
        # Get page content
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        product = {}
        
        # --- Title ---
        title_el = soup.select_one('#productTitle')
        product['title'] = clean_text(title_el.get_text()) if title_el else 'Unknown Product'
        
        # --- Price ---
        price = ''
        price_whole = soup.select_one('.a-price-whole')
        price_frac = soup.select_one('.a-price-fraction')
        if price_whole:
            whole = clean_text(price_whole.get_text()).replace(',', '').replace('.', '')
            frac = clean_text(price_frac.get_text()) if price_frac else '00'
            price = f"${whole}.{frac}"
        if not price:
            price_el = soup.select_one('#priceblock_ourprice, #priceblock_dealprice, .a-offscreen')
            if price_el:
                price = clean_text(price_el.get_text())
        product['price'] = price or 'Check on Amazon'
        
        # --- Rating ---
        rating_el = soup.select_one('#acrPopover, [data-hook="average-star-rating"]')
        if rating_el:
            rating_text = clean_text(rating_el.get('title', '') or rating_el.get_text())
            match = re.search(r'([\d\.]+)', rating_text)
            product['rating'] = match.group(1) if match else '4.5'
        else:
            product['rating'] = '4.5'
        
        # --- Review Count ---
        reviews_el = soup.select_one('#acrCustomerReviewText')
        if reviews_el:
            reviews_text = clean_text(reviews_el.get_text())
            match = re.search(r'([\d,]+)', reviews_text)
            product['reviews'] = match.group(1) if match else '0'
        else:
            product['reviews'] = '0'
        
        # --- Image ---
        image_url = ''
        # Try main image first
        img_el = soup.select_one('#landingImage, #imgBlkFront, #main-image')
        if img_el:
            image_url = img_el.get('src') or img_el.get('data-src') or ''
            # Try high-res data attribute
            data_dynamic = img_el.get('data-a-dynamic-image', '')
            if data_dynamic:
                try:
                    img_data = json.loads(data_dynamic)
                    # Get the largest image
                    best_url = max(img_data.keys(), key=lambda k: img_data[k][0] * img_data[k][1])
                    image_url = best_url
                except Exception:
                    pass
        
        # Fallback: look in scripts for image URLs
        if not image_url or 'data:image' in image_url:
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.get_text() if script.string else ''
                match = re.search(r'"large":"(https://[^"]+\.jpg)"', script_text)
                if match:
                    image_url = match.group(1)
                    break
        
        product['image'] = clean_text(image_url)
        
        # --- Bullet Points ---
        bullets = []
        bullet_els = soup.select('#feature-bullets li span.a-list-item')
        for b in bullet_els[:5]:
            text = clean_text(b.get_text())
            if text and len(text) > 5:
                bullets.append(text[:120])
        product['bullets'] = bullets
        
        # --- ASIN ---
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        product['asin'] = asin_match.group(1) if asin_match else ''
        
        # --- Category (guess from title) ---
        title_lower = product['title'].lower()
        if any(w in title_lower for w in ['rice cooker', 'cooker', 'air fryer', 'blender', 'coffee', 'kitchen', 'instant pot']):
            product['category'] = 'kitchen'
        elif any(w in title_lower for w in ['laptop', 'phone', 'tablet', 'headphone', 'speaker', 'camera', 'watch', 'monitor']):
            product['category'] = 'electronics'
        elif any(w in title_lower for w in ['vitamin', 'supplement', 'protein', 'health', 'fitness', 'gym']):
            product['category'] = 'health'
        elif any(w in title_lower for w in ['book', 'novel', 'guide']):
            product['category'] = 'books'
        else:
            product['category'] = 'featured'
        
        product['url'] = url
        product['scraped_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        await browser.close()
        return product


def generate_html_card(product):
    """Generate HTML product card."""
    stars = ''
    try:
        rating = float(product.get('rating', 0))
        full_stars = int(rating)
        half_star = 1 if (rating - full_stars) >= 0.5 else 0
        stars = ('&#9733;' * full_stars) + ('&#9734;' * half_star)
    except Exception:
        stars = '&#9733;&#9733;&#9733;&#9733;&#9734;'
    
    bullets_html = ''
    for b in product.get('bullets', []):
        safe_b = b.replace('<', '&lt;').replace('>', '&gt;')
        bullets_html += f'<li>{safe_b}</li>\n'
    
    safe_title = product['title'].replace('<', '&lt;').replace('>', '&gt;')
    safe_price = product['price'].replace('<', '&lt;').replace('>', '&gt;')
    
    card = f'''<!-- PRODUCT CARD: {safe_title[:50]} -->
<div class="product-card">
  <div class="product-img-wrap">
    <img src="{product['image']}" alt="{safe_title[:80]}" loading="lazy" />
  </div>
  <div class="product-body">
    <h3 class="product-title">{safe_title[:100]}</h3>
    <div class="product-rating">
      <span class="stars">{stars}</span>
      <span class="reviews">({product['reviews']} reviews)</span>
    </div>
    <ul class="product-bullets">
{bullets_html}    </ul>
  </div>
  <div class="product-footer">
    <span class="product-price">{safe_price}</span>
    <a href="{product['url']}" target="_blank" rel="nofollow noopener" class="btn-buy">View on Amazon</a>
  </div>
</div>'''
    return card


async def main():
    print("="*55)
    print("  NEXORA Amazon Product Scraper v3")
    print("="*55)
    
    url = input("\n[?] Paste Amazon product URL: ").strip()
    if not url:
        print("[!] No URL provided. Exiting.")
        return
    
    # Clean URL - remove tracking params but keep ASIN
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if asin_match:
        asin = asin_match.group(1)
        clean_url = f"https://www.amazon.com/dp/{asin}?tag=kareemelsay0b-20"
        print(f"[+] ASIN detected: {asin}")
        print(f"[+] Affiliate URL: {clean_url}")
    else:
        clean_url = url
        print("[!] Could not detect ASIN, using URL as-is")
    
    try:
        product = await scrape_amazon_product(clean_url)
    except Exception as e:
        print(f"[!] Scraping error: {e}")
        return
    
    # Print results
    print("\n" + "="*55)
    print("  SCRAPED PRODUCT DATA")
    print("="*55)
    print(f"Title:    {product['title'][:70]}")
    print(f"Price:    {product['price']}")
    print(f"Rating:   {product['rating']} ({product['reviews']} reviews)")
    print(f"Image:    {product['image'][:60]}..." if product['image'] else "Image:    Not found")
    print(f"Category: {product['category']}")
    print(f"Bullets:")
    for b in product['bullets']:
        print(f"  - {b[:80]}")
    
    # Save JSON
    out_dir = Path("nexora_products")
    out_dir.mkdir(exist_ok=True)
    
    asin_id = product.get('asin', 'unknown')
    out_json = out_dir / f"{asin_id}.json"
    out_html = out_dir / f"{asin_id}_card.html"
    
    # Save JSON with utf-8 encoding and ignore errors
    with open(out_json, 'w', encoding='utf-8', errors='ignore') as f:
        json.dump(product, f, ensure_ascii=False, indent=2)
    
    # Generate HTML card
    html_card = generate_html_card(product)
    
    # Save full HTML file with utf-8 encoding
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Product Card - {product['title'][:50]}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
    .product-card {{ background: white; border-radius: 12px; padding: 20px; max-width: 400px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
    .product-img-wrap img {{ width: 100%; border-radius: 8px; }}
    .product-title {{ font-size: 16px; font-weight: bold; margin: 10px 0; }}
    .stars {{ color: #f5a623; font-size: 18px; }}
    .product-price {{ font-size: 22px; font-weight: bold; color: #e44d26; }}
    .btn-buy {{ display: inline-block; background: #ff9900; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 10px; }}
    .product-bullets {{ font-size: 13px; padding-left: 18px; }}
    .product-footer {{ margin-top: 15px; display: flex; align-items: center; gap: 15px; }}
  </style>
</head>
<body>
{html_card}
</body>
</html>"""
    
    with open(out_html, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(full_html)
    
    print(f"\n[+] Saved JSON: {out_json}")
    print(f"[+] Saved HTML: {out_html}")
    print(f"\n[+] HTML Card (copy this to index.html -> products-grid):")
    print("="*55)
    print(html_card)
    print("="*55)
    print(f"\n[+] Done! Add the card above inside <div class=\"products-grid\"> in your index.html")
    print(f"[+] Category for this product: {product['category']}")


if __name__ == "__main__":
    asyncio.run(main())

    # Keep window open
    input("\n[*] Press ENTER to exit...")

