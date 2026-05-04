#!/usr/bin/env python3
"""
NEXORA Amazon Product Scraper
=============================
احط لينك المنتج من Amazon - السكريبت ده هيسحب:
  - اسم المنتج
  - السعر الحالي
  - رابط الصورة الرئيسية
  - التقييم وعدد الريفيوز
  - وصف المنتج
وبعدين يولد كود HTML جاهز تحطه في index.html

التشغيل:
  pip install requests beautifulsoup4 lxml
  python amazon_scraper.py
"""

import re
import sys
import json
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlencode, parse_qs

# ============================================================
# الإعدادات - عدّل TAG بتاعك هنا
# ============================================================
AFFILIATE_TAG = "kareemelsay0a-20"

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]

# ============================================================
# دوال مساعدة
# ============================================================

def clean_amazon_url(url: str) -> str:
    """استخرج ASIN من الرابط واعمل رابط أفلييت نظيف"""
    # استخرج ASIN
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if not asin_match:
        asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', url)
    if not asin_match:
        print("[!] مش قادر ألاقي ASIN في الرابط ده")
        return url

    asin = asin_match.group(1)
    clean = f"https://www.amazon.com/dp/{asin}?tag={AFFILIATE_TAG}&linkCode=ogi&th=1&psc=1"
    return clean, asin


def fetch_page(url: str) -> BeautifulSoup | None:
    """اجلب صفحة Amazon مع headers متنوعة"""
    headers = random.choice(HEADERS_LIST)
    # Force US location
    cookies = {"i18n-prefs": "USD", "lc-main": "en_US"}

    try:
        print(f"[*] جاري تحميل الصفحة...")
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=15)
        if resp.status_code != 200:
            print(f"[!] Status code: {resp.status_code}")
            return None
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"[!] خطأ في الاتصال: {e}")
        return None


def extract_title(soup: BeautifulSoup) -> str:
    selectors = [
        ("span", {"id": "productTitle"}),
        ("h1", {"id": "title"}),
        ("span", {"class": "product-title-word-break"}),
    ]
    for tag, attrs in selectors:
        el = soup.find(tag, attrs)
        if el:
            return el.get_text(strip=True)
    return "Unknown Product"


def extract_price(soup: BeautifulSoup) -> str:
    # محاولة 1: السعر الحالي
    price_el = soup.find("span", {"class": "a-price-whole"})
    frac_el = soup.find("span", {"class": "a-price-fraction"})
    if price_el:
        whole = price_el.get_text(strip=True).replace(",", "")
        frac = frac_el.get_text(strip=True) if frac_el else "00"
        return f"${whole}{frac}"

    # محاولة 2: corePriceDisplay
    for span in soup.find_all("span", {"class": "a-offscreen"}):
        txt = span.get_text(strip=True)
        if txt.startswith("$") and len(txt) < 15:
            return txt

    # محاولة 3: basisPrice
    el = soup.find("span", {"id": "priceblock_ourprice"})
    if el:
        return el.get_text(strip=True)

    return "Check Amazon"


def extract_rating(soup: BeautifulSoup) -> tuple[str, str]:
    """Returns (rating_str, review_count)"""
    rating = "N/A"
    count = "0"

    # Rating
    el = soup.find("span", {"data-hook": "rating-out-of-text"})
    if not el:
        el = soup.find("i", {"data-hook": "average-star-rating"})
    if el:
        txt = el.get_text(strip=True)
        m = re.search(r'([\d\.]+)', txt)
        if m:
            rating = m.group(1)

    # Count
    el2 = soup.find("span", {"id": "acrCustomerReviewText"})
    if el2:
        count_txt = el2.get_text(strip=True).replace(",", "").split()[0]
        count = count_txt

    return rating, count


def rating_to_stars(rating_str: str) -> str:
    """حوّل الرقم لنجوم Unicode"""
    try:
        r = float(rating_str)
    except ValueError:
        return "★★★★☆"
    full = int(r)
    half = 1 if (r - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


def extract_main_image(soup: BeautifulSoup) -> str:
    """استخرج أعلى جودة للصورة الرئيسية"""
    # محاولة 1: data في script tag
    scripts = soup.find_all("script", {"type": "text/javascript"})
    for script in scripts:
        if script.string and "ImageBlockATF" in script.string:
            m = re.search(r'"hiRes":"(https://[^"]+)"', script.string)
            if m:
                return m.group(1)
            m = re.search(r'"large":"(https://m\.media-amazon\.com[^"]+)"', script.string)
            if m:
                return m.group(1)

    # محاولة 2: landingImage
    img = soup.find("img", {"id": "landingImage"})
    if img:
        # جرب data-old-hires أولاً (أعلى جودة)
        src = img.get("data-old-hires") or img.get("src", "")
        if src and src.startswith("http"):
            # حوّل للـ SL1500 عشان أعلى جودة
            src = re.sub(r'_[A-Z]{2}\d+_', '_SL1500_', src)
            return src

    # محاولة 3: imgTagWrapperId
    img2 = soup.find("img", {"id": "main-image"})
    if img2:
        return img2.get("src", "")

    return ""


def extract_description(soup: BeautifulSoup) -> list[str]:
    """استخرج أهم نقاط المنتج (bullet points)"""
    bullets = []
    feature_div = soup.find("div", {"id": "feature-bullets"})
    if feature_div:
        items = feature_div.find_all("li")
        for item in items[:5]:  # أول 5 نقاط بس
            txt = item.get_text(strip=True)
            if txt and "Make sure" not in txt:
                bullets.append(txt)
    return bullets


def guess_category(title: str) -> tuple[str, str]:
    """خمّن الكاتيجوري من اسم المنتج"""
    title_lower = title.lower()
    if any(w in title_lower for w in ["pet", "dog", "cat", "collar", "leash", "paw"]):
        return "🐾 Pets Pick", "pets"
    elif any(w in title_lower for w in ["beauty", "skin", "hair", "lip", "serum", "cream", "makeup", "face"]):
        return "✨ Beauty Pick", "beauty"
    elif any(w in title_lower for w in ["phone", "laptop", "usb", "cable", "wireless", "bluetooth", "tech", "gadget", "camera", "headphone", "earphone"]):
        return "⚡ Tech Pick", "tech"
    else:
        return "🏠 Home Pick", "home"


def generate_html_card(product: dict) -> str:
    """ولّد كود HTML بطاقة المنتج الجاهزة للموقع"""
    badge_text, category = guess_category(product["title"])
    stars = rating_to_stars(product["rating"])

    # اختصر العنوان لو طويل
    short_title = product["title"]
    if len(short_title) > 120:
        short_title = short_title[:117] + "..."

    # Bullet points (لو موجودين)
    bullets_html = ""
    if product["bullets"]:
        items = "".join(f"<li>{b}</li>" for b in product["bullets"][:3])
        bullets_html = f'<ul class="product-bullets">{items}</ul>'

    card = f"""
      <!-- PRODUCT: {product['asin']} - {product['title'][:50]} -->
      <div class="product-card">
        <img src="{product['image']}" alt="{short_title}" loading="lazy"/>
        <div class="product-info">
          <span class="product-badge">{badge_text}</span>
          <h3 class="product-title">{short_title}</h3>
          <div class="product-rating">{stars} <span>{product['rating']} ({product['review_count']} reviews)</span></div>
          {bullets_html}
          <div class="product-price"><span class="currency">$</span>{product['price_clean']}</div>
          <a href="{product['affiliate_url']}" class="buy-btn" target="_blank" rel="noopener noreferrer">
            🛒 Buy on Amazon
          </a>
        </div>
      </div>"""
    return card


def scrape_product(url: str) -> dict | None:
    """السكريبت الرئيسي: اسحب كل بيانات المنتج"""
    result = clean_amazon_url(url)
    if isinstance(result, str):
        return None
    affiliate_url, asin = result

    print(f"[*] ASIN: {asin}")
    print(f"[*] Affiliate URL: {affiliate_url}")

    # تحميل الصفحة
    time.sleep(random.uniform(1, 2))  # تأخير بسيط عشان ما يتحجبش
    soup = fetch_page(affiliate_url)
    if not soup:
        print("[!] فشل تحميل الصفحة")
        return None

    # استخراج البيانات
    print("[*] جاري استخراج البيانات...")
    title   = extract_title(soup)
    price   = extract_price(soup)
    rating, review_count = extract_rating(soup)
    image   = extract_main_image(soup)
    bullets = extract_description(soup)

    # تنظيف السعر
    price_clean = price.replace("$", "").replace(",", "").strip()
    if price_clean == "Check Amazon":
        price_clean = "Check Amazon"

    product = {
        "asin":          asin,
        "title":         title,
        "price":         price,
        "price_clean":   price_clean,
        "rating":        rating,
        "review_count":  review_count,
        "image":         image,
        "bullets":       bullets,
        "affiliate_url": affiliate_url,
    }

    return product


def main():
    print("=" * 60)
    print("  NEXORA - Amazon Product Scraper")
    print("=" * 60)

    # اطلب رابط المنتج
    url = input("\n[?] الصق رابط المنتج من Amazon: ").strip()
    if not url:
        print("[!] لازم تحط رابط")
        sys.exit(1)

    # اسحب البيانات
    product = scrape_product(url)
    if not product:
        print("\n[!] فشل سحب البيانات. جرب تاني بعد شوية.")
        sys.exit(1)

    # اعرض النتيجة
    print("\n" + "=" * 60)
    print("  النتيجة:")
    print("=" * 60)
    print(f"  الاسم:      {product['title'][:70]}...")
    print(f"  السعر:      {product['price']}")
    print(f"  التقييم:    {product['rating']} ({product['review_count']} reviews)")
    print(f"  الصورة:     {product['image'][:80]}...")
    print(f"  لينك افليت: {product['affiliate_url']}")
    if product['bullets']:
        print(f"  الـ Features:")
        for b in product['bullets']:
            print(f"    - {b[:80]}")
    print("=" * 60)

    # ولّد HTML
    html_card = generate_html_card(product)

    # احفظ في ملف
    output_filename = f"product_{product['asin']}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("<!-- ==========================================\n")
        f.write("     انسخ الكود ده وحطه في index.html\n")
        f.write("     داخل <div class=\"products-grid\">\n")
        f.write("========================================== -->\n")
        f.write(html_card)
        f.write("\n<!-- ========================================== -->\n")

    print(f"\n[+] تم الحفظ في ملف: {output_filename}")
    print(f"[+] افتح الملف ده وانسخ الكود وحطه في قسم products-grid في index.html")
    print("\n" + "=" * 60)
    print("  كود HTML الجاهز:")
    print("=" * 60)
    print(html_card)
    print("=" * 60)

    # احفظ JSON كمان
    json_file = f"product_{product['asin']}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(product, f, ensure_ascii=False, indent=2)
    print(f"[+] بيانات JSON محفوظة في: {json_file}")


if __name__ == "__main__":
    main()
