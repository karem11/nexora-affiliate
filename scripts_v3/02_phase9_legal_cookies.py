"""
Phase 9 — Legal, Trust & Cookie System

What this does:
1. Creates /website/cookies.html (Cookie Policy page) — new
2. Updates /website/privacy.html
   - Expands section 5 (Cookies) to describe consent banner + localStorage
   - Adds section about AI-generated content
   - Adds Cookie Policy footer link
   - Injects cookie-banner.js
3. Updates /website/disclosure.html
   - Removes references to ratings / review counts / prices (no longer shown)
   - Reframes "Pricing and Availability" → "Product Information"
   - Adds Cookie Policy footer link
   - Injects cookie-banner.js
4. Updates terms.html, about.html, contact.html, contact-success.html
   - Adds Cookie Policy footer link
   - Injects cookie-banner.js

Builder (site_builder_v3/builder.py) injects banner into homepage + product +
category pages separately.
"""
from __future__ import annotations
import re
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "website"

COOKIE_SCRIPT_TAG = '<script src="cookie-banner.js" defer></script>'
COOKIE_FOOTER_LINK = '                <a href="cookies.html">Cookie Policy</a>'


def inject_cookie_script(html: str) -> str:
    """Add <script src="cookie-banner.js" defer></script> before </body>."""
    if "cookie-banner.js" in html:
        return html
    return html.replace("</body>", f"    {COOKIE_SCRIPT_TAG}\n</body>", 1)


def add_cookies_footer_link(html: str) -> str:
    """Insert Cookie Policy link after Privacy Policy in footer."""
    if "cookies.html" in html and "Cookie Policy" in html:
        # Already present
        return html
    pattern = re.compile(r'(<a href="privacy\.html">Privacy Policy</a>)')
    if not pattern.search(html):
        return html
    return pattern.sub(
        r'\1\n' + COOKIE_FOOTER_LINK,
        html,
        count=1,
    )


def update_disclosure_remove_ratings_prices(html: str) -> str:
    """Remove v2 leftover references to ratings, review counts, and prices."""
    # Section 5: replace bullet about "Real Amazon ratings and review counts"
    # with a brand-safe alternative.
    html = html.replace(
        '<li>Real Amazon ratings and review counts;</li>',
        '<li>Topical relevance and category match;</li>',
    )
    html = html.replace(
        '<li>Verified purchase data;</li>',
        '<li>Active community engagement signals;</li>',
    )
    # Section 7: replace whole section about pricing accuracy with a generic
    # "Product Information" section that is true for v3.
    old_sec7 = (
        '                <h2>7. Pricing and Availability</h2>\n'
        '                <p>Product prices, ratings, review counts, and availability shown on NEXORA are accurate as of the date\n'
        '                    and time we last refreshed the data. <strong>Amazon\'s prices and availability change frequently\n'
        '                        — sometimes by the minute</strong>. Please verify the current price on Amazon.com before\n'
        '                    purchasing.</p>\n'
        '                <p>We update product data regularly, but we cannot guarantee real-time accuracy. Amazon is the\n'
        '                    authoritative source for current pricing.</p>'
    )
    new_sec7 = (
        '                <h2>7. Product Information</h2>\n'
        '                <p>NEXORA does <strong>not display prices, star ratings, or review counts</strong> on this site.\n'
        '                    All current pricing, availability, ratings, and reviews are shown on Amazon.com. Please review\n'
        '                    those details on the product page on Amazon before purchasing.</p>\n'
        '                <p>We feature products based on our own editorial selection, trend signals, and community engagement.\n'
        '                    Amazon is the authoritative source for all pricing and inventory information.</p>'
    )
    html = html.replace(old_sec7, new_sec7)

    # Footer disclosure: remove "Product prices and availability are accurate" line.
    html = html.replace(
        'As an Amazon Associate, we earn from qualifying purchases. Product prices and\n'
        '                availability are accurate as of the date/time indicated and are subject to change.',
        'As an Amazon Associate, NEXORA earns from qualifying purchases. Product availability,\n'
        '                pricing and details are determined by Amazon at the time of purchase.',
    )
    return html


def update_privacy_expand_cookies_and_ai(html: str) -> str:
    """Expand cookies section + add AI disclosure section."""
    # Replace simplified cookies section with the new one that documents the
    # consent banner and the localStorage key we use.
    old_cookies = (
        '                <h2>5. Cookies</h2>\n'
        '                <p>We use the following cookies on our Site:</p>\n'
        '                <ul>\n'
        '                    <li><strong>Strictly necessary cookies:</strong> required for basic site functionality.</li>\n'
        '                    <li><strong>Analytics cookies (optional, future):</strong> if we add Google Analytics or similar\n'
        '                        services in the future, we will update this policy and provide a clear cookie banner.</li>\n'
        '                    <li><strong>Affiliate tracking cookies:</strong> Amazon and its affiliate network set cookies when\n'
        '                        you click product links. These cookies are managed by Amazon, not by NEXORA.</li>\n'
        '                </ul>\n'
        '                <p>You can disable cookies through your browser settings. Disabling cookies may affect the functionality\n'
        '                    of some parts of the Site.</p>'
    )
    new_cookies = (
        '                <h2>5. Cookies and Local Storage</h2>\n'
        '                <p>NEXORA uses cookies and browser <code>localStorage</code> in a minimal, privacy-respecting way.\n'
        '                    For full details please read our <a href="cookies.html">Cookie Policy</a>.</p>\n'
        '                <p>Specifically:</p>\n'
        '                <ul>\n'
        '                    <li><strong>Cookie consent (localStorage):</strong> when you click "Accept" on the cookie banner,\n'
        '                        we save a small flag (<code>nexora_cookie_consent</code>) in your browser so we don\'t show\n'
        '                        the banner again. This flag stays on your device only — we never receive it.</li>\n'
        '                    <li><strong>Strictly necessary cookies:</strong> may be set by our hosting provider (Netlify) for\n'
        '                        basic site security and performance.</li>\n'
        '                    <li><strong>Analytics (future):</strong> if we add a privacy-respecting analytics tool such as\n'
        '                        Plausible or GA4, we will update this Privacy Policy and the Cookie Policy first.</li>\n'
        '                    <li><strong>Affiliate tracking cookies (Amazon):</strong> when you click a product link to Amazon,\n'
        '                        Amazon sets its own cookies on amazon.com. Those cookies are governed by Amazon\'s privacy\n'
        '                        policy, not NEXORA\'s.</li>\n'
        '                </ul>\n'
        '                <p>You can disable cookies and clear local storage at any time from your browser settings.\n'
        '                    Disabling them may affect parts of the Site.</p>\n'
        '\n'
        '                <h2>5b. AI-Generated Content</h2>\n'
        '                <p>Some product titles, summaries, hooks, benefits, and lifestyle images on NEXORA are generated or\n'
        '                    enhanced using artificial intelligence (e.g., Google Gemini for text, Pollinations / similar\n'
        '                    models for images). AI-generated content is reviewed and curated by our team, but may contain\n'
        '                    inaccuracies. <strong>Amazon\'s product page is always the authoritative source</strong> for\n'
        '                    product specifications, pricing, ratings, and availability.</p>\n'
        '                <p>We do not feed any of your personal data into AI services. The AI models we use only see public\n'
        '                    product metadata (e.g., the product name and category) when generating marketing copy.</p>'
    )
    html = html.replace(old_cookies, new_cookies)
    return html


COOKIES_PAGE = """<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta name="robots" content="index,follow" />
    <title>Cookie Policy | NEXORA</title>
    <meta name="description"
        content="NEXORA Cookie Policy — what cookies and local storage we use, why we use them, and how to manage them." />
    <link rel="canonical" href="https://nexora-shop-us.netlify.app/cookies.html" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="Cookie Policy | NEXORA" />
    <meta property="og:description" content="What cookies NEXORA uses and how to manage them." />
    <meta property="og:url" content="https://nexora-shop-us.netlify.app/cookies.html" />
    <meta property="og:image" content="https://f.top4top.io/p_3776hn9nu1.png" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="pages.css">
</head>

<body>
    <header>
        <div class="container">
            <div class="nav-inner">
                <a href="index.html" class="brand">
                    <img src="https://f.top4top.io/p_3776hn9nu1.png" alt="NEXORA" class="brand-logo" />
                    <div class="brand-text">
                        <h1>NEXORA</h1>
                        <p>Smart Finds. Better Life.</p>
                    </div>
                </a>
                <div class="nav-links">
                    <a href="index.html">Home</a>
                    <a href="category/tech.html">Tech</a>
                    <a href="category/home.html">Home &amp; Kitchen</a>
                    <a href="category/beauty.html">Beauty</a>
                    <a href="category/pet.html">Pet</a>
                    <a href="about.html">About</a>
                    <a href="contact.html">Contact</a>
                </div>
            </div>
        </div>
    </header>

    <section class="page-hero">
        <div class="container">
            <div class="breadcrumb"><a href="index.html">Home</a> &nbsp;&rsaquo;&nbsp; Cookie Policy</div>
            <h1>Cookie Policy</h1>
            <p>What cookies and local storage we use, and why</p>
        </div>
    </section>

    <main>
        <div class="container">
            <div class="content">
                <div class="updated"><strong>Last updated:</strong> November 2026</div>

                <div class="callout">
                    <p><strong>&#128571; Quick summary:</strong> NEXORA uses a tiny amount of browser storage to remember
                        your cookie consent and to make Amazon affiliate links work. We do not use advertising cookies,
                        we do not sell your data, and we do not run third-party trackers on this site.</p>
                </div>

                <h2>1. What Are Cookies?</h2>
                <p>Cookies are small text files that a website stores in your browser. <strong>Local storage</strong>
                    is a similar mechanism that lets a website save small pieces of data on your device. Both are
                    standard web technologies.</p>

                <h2>2. Cookies and Storage NEXORA Uses</h2>
                <p>NEXORA uses the following items, and only the following items:</p>
                <ul>
                    <li><strong><code>nexora_cookie_consent</code> (localStorage)</strong> &mdash; saves the fact that
                        you clicked "Accept" on our cookie banner so we don't show the banner again. Contains only a
                        boolean flag and a timestamp. Never leaves your device.</li>
                    <li><strong>Netlify operational cookies</strong> &mdash; our hosting provider (Netlify) may set
                        small cookies for basic site security, anti-abuse, and performance. These are not analytics
                        cookies. Details: <a href="https://www.netlify.com/privacy/" rel="nofollow noopener"
                            target="_blank">netlify.com/privacy</a>.</li>
                </ul>
                <p>That's it. We do not run Google Analytics, we do not run Facebook Pixel, we do not run any third-party
                    advertising or remarketing tools on NEXORA.</p>

                <h2>3. Cookies Set by Amazon (Off-Site)</h2>
                <p>NEXORA links to <strong>Amazon.com</strong> via the Amazon Associates Program. When you click a
                    product link and land on Amazon, <em>Amazon</em> sets its own cookies on amazon.com. Those cookies
                    are governed by Amazon's privacy notice, not by NEXORA.</p>
                <p>Reference:
                    <a href="https://www.amazon.com/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ"
                        rel="nofollow noopener" target="_blank">Amazon Privacy Notice</a>.
                </p>

                <h2>4. Future Analytics</h2>
                <p>If we add an analytics tool in the future, we will choose a privacy-respecting one (such as
                    <a href="https://plausible.io/" rel="nofollow noopener" target="_blank">Plausible</a>),
                    update this Cookie Policy and our <a href="privacy.html">Privacy Policy</a>, and update the cookie
                    banner so you can opt in or out before any data is collected.</p>

                <h2>5. How to Manage or Disable Cookies</h2>
                <p>You can manage cookies and clear local storage from your browser at any time:</p>
                <ul>
                    <li><strong>Chrome:</strong> Settings &rarr; Privacy and security &rarr; Cookies and other site data.</li>
                    <li><strong>Firefox:</strong> Settings &rarr; Privacy &amp; Security &rarr; Cookies and Site Data.</li>
                    <li><strong>Safari:</strong> Preferences &rarr; Privacy &rarr; Manage Website Data.</li>
                    <li><strong>Edge:</strong> Settings &rarr; Cookies and site permissions &rarr; Manage and delete cookies.</li>
                </ul>
                <p>If you clear the <code>nexora_cookie_consent</code> entry, our cookie banner will appear again on
                    your next visit so you can re-confirm your preference.</p>

                <h2>6. Your Consent</h2>
                <p>By clicking "Accept" on the cookie banner, you consent to the small operational cookies and
                    localStorage entry described above. If you do not click Accept, we will keep showing the banner
                    on each visit and we will not save the consent flag.</p>

                <h2>7. Changes to This Cookie Policy</h2>
                <p>If we change which cookies we use, we will update this page, update the "Last updated" date, and
                    re-show the cookie banner so you can review and re-consent.</p>

                <h2>8. Questions</h2>
                <p>Reach out any time:</p>
                <ul>
                    <li><strong>Email:</strong> <a href="mailto:karemali11@gmail.com">karemali11@gmail.com</a></li>
                    <li><strong>Contact form:</strong> <a href="contact.html">Contact page</a></li>
                </ul>

                <p style="margin-top:18px">See also: <a href="privacy.html">Privacy Policy</a> &middot;
                    <a href="disclosure.html">Affiliate Disclosure</a> &middot; <a href="terms.html">Terms of Service</a>.</p>
            </div>
        </div>
    </main>

    <footer>
        <div class="container">
            <div class="footer-brand">
                <img src="https://f.top4top.io/p_3776hn9nu1.png" alt="NEXORA" class="brand-logo" />
                <div class="brand-text">
                    <h1>NEXORA</h1>
                    <p>Smart Finds. Better Life.</p>
                </div>
            </div>
            <div class="footer-links">
                <a href="index.html">Home</a>
                <a href="category/tech.html">Tech</a>
                <a href="category/home.html">Home &amp; Kitchen</a>
                <a href="category/beauty.html">Beauty</a>
                <a href="category/pet.html">Pet</a>
                <a href="about.html">About</a>
                <a href="contact.html">Contact</a>
                <a href="privacy.html">Privacy Policy</a>
                <a href="cookies.html">Cookie Policy</a>
                <a href="disclosure.html">Affiliate Disclosure</a>
                <a href="terms.html">Terms of Service</a>
            </div>
            <p class="disclosure">&#128226; NEXORA is a participant in the Amazon Services LLC Associates Program, an affiliate
                advertising program designed to provide a means for sites to earn advertising fees by advertising and
                linking to Amazon.com. As an Amazon Associate, NEXORA earns from qualifying purchases. Product
                availability, pricing, and details are determined by Amazon at the time of purchase.</p>
            <p class="disclosure" style="margin-top:12px">&copy; 2026 NEXORA. All rights reserved.</p>
        </div>
    </footer>
    <script src="cookie-banner.js" defer></script>
</body>

</html>
"""


def main() -> int:
    pages_to_patch = [
        "privacy.html",
        "terms.html",
        "disclosure.html",
        "about.html",
        "contact.html",
        "contact-success.html",
    ]

    # 1. Write cookies.html
    cookies_path = WEBSITE / "cookies.html"
    cookies_path.write_text(COOKIES_PAGE, encoding="utf-8")
    print(f"  + wrote {cookies_path.relative_to(WEBSITE.parent)}")

    # 2. Patch existing legal pages
    for name in pages_to_patch:
        path = WEBSITE / name
        if not path.exists():
            print(f"  ! skipped {name} (not found)")
            continue
        html = path.read_text(encoding="utf-8")
        before = html

        if name == "privacy.html":
            html = update_privacy_expand_cookies_and_ai(html)
        if name == "disclosure.html":
            html = update_disclosure_remove_ratings_prices(html)

        html = add_cookies_footer_link(html)
        html = inject_cookie_script(html)

        if html != before:
            path.write_text(html, encoding="utf-8")
            print(f"  ~ updated {name}")
        else:
            print(f"  = no change {name}")

    print("\nPhase 9 (legal + cookie) static-page updates complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
