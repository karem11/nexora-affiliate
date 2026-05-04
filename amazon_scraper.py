#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXORA Amazon Product Scraper v2 - Playwright Edition
======================================================
السكريبت ده بيفتح Chrome حقيقي ويسحب بيانات المنتج من Amazon تلقائياً:
  - اسم المنتج
  - السعر الحالي
  - الصورة الرئيسية بأعلى جودة
  - التقييم وعدد الريفيوز
  - أهم مميزات المنتج
  - بيولّد كود HTML جاهز تحطه في الموقع

التشغيل:
  pip install playwright
  playwright install chromium
  python amazon_scraper.py
"""

import re
import sys
import json
import time
import random
import asyncio
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("[!] Playwright مش مثبّت. شغّل الأمر ده:")
    print("    pip install playwright && playwright install chromium")
    sys.exit(1)

# ============================================================
# الإعدادات
# ============================================================
AFFILIATE_TAG = "kareemelsay0a-20"
HEADLESS = False   # False = بيفتح نافذة Chrome تشوفها, True = بيشتغل في الخلفية


# ============================================================
# دوال مساعدة
# ============================================================

def extract_asin(url: str) -> str | None:
    """استخرج ASIN من أي رابط Amazon"""
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    if not m:
        m = re.search(r'/gp/product/([A-Z0-9]{10})', url)
    if not m:
        m = re.search(r'[?&]asin=([A-Z0-9]{10})', url)
    return m.group(1) if m else None


def build_affiliate_url(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}?tag={AFFILIATE_TAG}&linkCode=ogi&th=1&psc=1"


def rating_to_stars(rating: str) -> str:
    try:
        r = float(rating)
    except (ValueError, TypeError):
        return "\u2605\u2605\u2605\u2605\u2606"
    full  = int(r)
    half  = 1 if (r - full) >= 0.5 else 0
    empty = 5 - full - half
    return "\u2605" * full + ("\u00bd" if half else "") + "\u2606" * empty


def guess_category(title: str) -> tuple:
    t = title.lower()
    if any(w in t for w in ["pet","dog","cat","collar","leash","paw","bird","fish","aquarium"]):
        return "\ud83d\udc3e Pets", "pets"
    if any(w in t for w in ["beauty","skin","hair","lip","serum","cream","makeup","face","moisturizer","perfume","fragrance"]):
        return "\u2728 Beauty", "beauty"
    if any(w in t for w in ["phone","laptop","usb","cable","wireless","bluetooth","speaker","headphone","earphone","earbuds","monitor","keyboard","mouse","camera","tablet","charger","battery","alexa","echo","kindle","gaming","router"]):
        return "\u26a1 Tech", "tech"
    return "\ud83c\udfe0 Home", "home"


# ============================================================
# السكريبت الرئيسي
# ============================================================

async def scrape_amazon(url: str) -> dict | None:
    asin = extract_asin(url)
    if not asin:
        print("[!] مش قادر ألاقي ASIN في الرابط ده")
        print("    تأكد إن الرابط من Amazon وفيه /dp/XXXXXXXXXX")
        return None

    affiliate_url = build_affiliate_url(asin)
    print(f"[*] ASIN: {asin}")
    print(f"[*] URL:  {affiliate_url}")
    print("[*] جاري فتح المتصفح...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--lang=en-US",
            ]
        )

        ctx = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )

        # تعطيل علامات الأتمتة
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        page = await ctx.new_page()

        # ضبط cookies عشان يظهر بالدولار الأمريكي
        await ctx.add_cookies([
            {"name": "i18n-prefs", "value": "USD",   "domain": ".amazon.com", "path": "/"},
            {"name": "lc-main",   "value": "en_US", "domain": ".amazon.com", "path": "/"},
        ])

        print("[*] جاري تحميل صفحة المنتج...")
        try:
            await page.goto(affiliate_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 3500))
        except PlaywrightTimeout:
            print("[!] انتهت مدة الانتظار. جرب تاني أو تأكد من الاتصال.")
            await browser.close()
            return None

        # ---- استخراج الاسم ----
        title = ""
        for sel in ["#productTitle", "h1#title span", "span.product-title-word-break"]:
            el = page.locator(sel).first
            if await el.count():
                title = (await el.inner_text()).strip()
                break
        print(f"[+] الاسم: {title[:70]}...")

        # ---- استخراج السعر ----
        price = ""
        for sel in [
            ".a-price.a-text-price.a-size-medium .a-offscreen",
            "#apex_desktop .a-price .a-offscreen",
            "#corePrice_desktop .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price-whole",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count():
                    raw = (await el.inner_text()).strip()
                    if "$" in raw or raw.replace(",","").replace(".","").isdigit():
                        price = raw.replace("\n","").strip()
                        break
            except Exception:
                continue
        print(f"[+] السعر: {price}")

        # ---- استخراج التقييم ----
        rating = ""
        review_count = ""
        try:
            r_el = page.locator("#acrPopover").first
            if await r_el.count():
                title_attr = await r_el.get_attribute("title")
                if title_attr:
                    m = re.search(r"([\d\.]+)", title_attr)
                    if m:
                        rating = m.group(1)
        except Exception:
            pass

        try:
            cnt_el = page.locator("#acrCustomerReviewText").first
            if await cnt_el.count():
                review_count = (await cnt_el.inner_text()).strip().replace(",","").split()[0]
        except Exception:
            pass
        print(f"[+] التقييم: {rating} ({review_count} reviews)")

        # ---- استخراج الصورة بأعلى جودة ----
        image_url = ""
        try:
            # محاولة 1: من JS data (أعلى جودة)
            img_data = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script[type="text/javascript"]');
                    for (const s of scripts) {
                        if (s.innerText && s.innerText.includes('ImageBlockATF')) {
                            const m = s.innerText.match(/"hiRes":"(https:[^"]+)"/);
                            if (m) return m[1];
                            const m2 = s.innerText.match(/"large":"(https:\/\/m\.media-amazon[^"]+)"/);
                            if (m2) return m2[1];
                        }
                    }
                    return null;
                }
            """)
            if img_data:
                image_url = img_data
        except Exception:
            pass

        # محاولة 2: من landingImage
        if not image_url:
            try:
                img_el = page.locator("#landingImage").first
                if await img_el.count():
                    src = await img_el.get_attribute("data-old-hires")
                    if not src:
                        src = await img_el.get_attribute("src")
                    if src:
                        # رفع الجودة لـ SL1500
                        image_url = re.sub(r'_[A-Z]{2}\d+_', '_SL1500_', src)
            except Exception:
                pass

        # محاولة 3: أول صورة في قسم الصور
        if not image_url:
            try:
                img_el = page.locator("#imgTagWrapperId img").first
                if await img_el.count():
                    image_url = await img_el.get_attribute("src") or ""
            except Exception:
                pass

        print(f"[+] الصورة: {image_url[:80]}...")

        # ---- استخراج مميزات المنتج ----
        bullets = []
        try:
            items = await page.locator("#feature-bullets li span.a-list-item").all_inner_texts()
            for b in items[:5]:
                b = b.strip()
                if b and "Make sure" not in b and len(b) > 10:
                    bullets.append(b)
        except Exception:
            pass

        await browser.close()

    # ---- تجميع البيانات ----
    price_clean = re.sub(r'[^\d\.]', '', price) if price else "Check Amazon"

    product = {
        "asin":          asin,
        "title":         title,
        "price":         price,
        "price_clean":   price_clean,
        "rating":        rating,
        "review_count":  review_count,
        "image":         image_url,
        "bullets":       bullets,
        "affiliate_url": affiliate_url,
    }
    return product


def generate_html_card(p: dict) -> str:
    """ولّد كارد HTML بالـ classes الصح للموقع"""
    badge_cat, _ = guess_category(p["title"])
    stars        = rating_to_stars(p["rating"])
    short_title  = p["title"][:120] + ("..." if len(p["title"]) > 120 else "")
    price_display = f"${p['price_clean']}" if p['price_clean'] != "Check Amazon" else "Check Amazon"

    # badge type
    badge_class = "hot"
    badge_label = "\ud83d\udd25 Hot"

    card = f"""      <!-- PRODUCT: {p['asin']} -->
      <div class="product-card">
        <div class="product-img-wrap">
          <img src="{p['image']}" alt="{short_title}" loading="lazy"/>
          <span class="product-badge {badge_class}">{badge_label}</span>
        </div>
        <div class="product-body">
          <span class="product-cat">{badge_cat}</span>
          <h3 class="product-title">{short_title}</h3>
          <div class="product-stars">
            <span class="stars">{stars}</span>
            <span class="rating-count">{p['rating']} ({p['review_count']} reviews)</span>
          </div>
        </div>
        <div class="product-footer">
          <div>
            <div class="product-price">{price_display}</div>
            <div class="price-note">Free Prime Shipping</div>
          </div>
          <a href="{p['affiliate_url']}" class="btn-amazon" target="_blank" rel="noopener noreferrer">\ud83d\uded2 Buy Now</a>
        </div>
      </div>"""
    return card


async def main():
    print("\n" + "="*60)
    print("  NEXORA - Amazon Scraper v2 (Playwright)")
    print("="*60)
    print("  الصق رابط المنتج من Amazon (رابط الأفلييت أو العادي)")
    print("  مثال: https://www.amazon.com/dp/B0FXNXR46R...")
    print("="*60)

    url = input("\n[?] رابط المنتج: ").strip()
    if not url:
        print("[!] لازم تحط رابط")
        sys.exit(1)

    product = await scrape_amazon(url)
    if not product:
        print("\n[!] فشل السحب. جرب تاني.")
        sys.exit(1)

    print("\n" + "="*60)
    print("  النتيجة:")
    print("="*60)
    print(f"  الاسم:      {product['title'][:65]}...")
    print(f"  السعر:      {product['price']}")
    print(f"  التقييم:    {product['rating']} ({product['review_count']} reviews)")
    print(f"  الصورة:     {product['image'][:70]}...")
    if product['bullets']:
        print(f"  المميزات:")
        for b in product['bullets']:
            print(f"    - {b[:80]}")
    print("="*60)

    # توليد كود HTML
    html_card = generate_html_card(product)

    # حفظ في ملف HTML
    out_html = Path(f"product_{product['asin']}.html")
    out_html.write_text(
        f"""<!-- ================================================
     انسخ الكود ده وحطه في index.html
     داخل: <div class="products-grid">
================================================ -->\n"""
        + html_card + "\n<!-- ================================================ -->\n",
        encoding="utf-8"
    )

    # حفظ JSON
    out_json = Path(f"product_{product['asin']}.json")
    out_json.write_text(json.dumps(product, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[+] تم الحفظ في: {out_html}")
    print(f"[+] بيانات JSON:  {out_json}")
    print("\n" + "="*60)
    print("  كود HTML الجاهز (انسخه وحطه في index.html):")
    print("="*60)
    print(html_card)
    print("="*60)
    print("\n[+] خطوات إضافة المنتج للموقع:")
    print("  1. افتح github.com/karem11/nexora-affiliate")
    print("  2. افتح index.html > أيقونة القلم")
    print('  3. دوّر على: <div class="products-grid">')
    print("  4. ألصق الكارد جوّاه")
    print("  5. اضغط Commit changes")
    print("  6. الموقع يتحدث خلال 30 ثانية!")


if __name__ == "__main__":
    asyncio.run(main())
