# NEXORA

> AI-powered viral product discovery platform.
> *Smart Finds. Better Life.*

**Live:** https://nexora-shop-us.netlify.app

[![Phase 1](https://img.shields.io/badge/Phase%201-Cleanup%20%26%20Compliance-success)](docs/CHANGELOG_v3.0_phase1_9.md)
[![Phase 9](https://img.shields.io/badge/Phase%209-Legal%20%26%20Cookies-success)](docs/CHANGELOG_v3.0_phase1_9.md)
[![Amazon TOS](https://img.shields.io/badge/Amazon%20Associates-compliant-success)](docs/CHANGELOG_v3.0_phase1_9.md)

---

## What is NEXORA?

NEXORA is **not** an Amazon clone. It is a curated, AI-assisted viral product
discovery brand — premium-feeling, SEO-optimized, social-first.

This repo is the source of truth for the live site. The build pipeline is
fully Python; deployment is handled automatically by Netlify when commits land
on `main`.

## Repo layout

```
nexora-affiliate/
├── website/                 ← static site published to Netlify
│   ├── index.html
│   ├── product/             ← 30 product pages (compliant — no prices/ratings/reviews)
│   ├── category/            ← tech / home / beauty / pet
│   ├── cookies.html         ← Cookie Policy (Phase 9)
│   ├── privacy.html         ← Privacy Policy (with cookies + AI disclosure)
│   ├── disclosure.html      ← Affiliate Disclosure
│   ├── terms.html
│   ├── cookie-banner.js     ← Phase 9 cookie consent
│   ├── site.css / pages.css
│   ├── sitemap.xml / robots.txt
│   └── google0e18519c81a40ea2.html
│
├── data/
│   └── products.json        ← v3 source of truth (no prices/ratings — placeholders for AI)
│
├── scripts_v3/
│   ├── 01_clean_products.py        ← v2 → v3 data migration (idempotent)
│   └── 02_phase9_legal_cookies.py  ← injects cookie banner + Cookie Policy
│
├── site_builder_v3/
│   └── builder.py           ← generates website/ from data/products.json
│
├── pinterest/               ← Pinterest pin generator (paused, resumes in Phase 5)
│
├── docs/
│   ├── REBUILD_PLAN_v3.md           ← 10-phase roadmap
│   ├── PROJECT_CONTEXT.md           ← full project memory
│   └── CHANGELOG_v3.0_phase1_9.md
│
├── nexora_market_intelligence_v2.py ← legacy v2 scraper (Amazon trends)
├── netlify.toml             ← deploy config (publish = "website")
├── requirements.txt
└── README.md
```

## Build pipeline (local)

```bash
# 1. Refresh data/products.json from any new product source
python3 scripts_v3/01_clean_products.py

# 2. (Future, Phase 2) AI-enrich titles / hooks / benefits
# python3 ai_engine/content_generator.py

# 3. Build static site
python3 site_builder_v3/builder.py

# 4. Apply Phase 9 patches to legal pages
python3 scripts_v3/02_phase9_legal_cookies.py

# 5. Commit + push → Netlify auto-deploys
git add website data
git commit -m "build: regenerate website"
git push
```

## Compliance (Amazon Associates TOS)

NEXORA does **not** display:
- Static prices, list prices, or discount badges
- Star ratings or review counts
- "X bought in past month" social proof
- `aggregateRating` or `offers.price` in schema.org markup

All current product pricing, ratings, and reviews are shown only on Amazon.com
itself when the user clicks through.

See `docs/CHANGELOG_v3.0_phase1_9.md` for the full list of removed fields.

## 10-Phase roadmap

| # | Phase | Status |
|---|---|---|
| 1 | Cleanup & Amazon Compliance | ✅ Done |
| 2 | AI Content Engine (Gemini + Pollinations) | ⏸ Awaits Gemini key |
| 3 | SEO & Google Optimization | ⏳ Pending |
| 4 | Viral Brand Experience (Nexora Finds, Trending, Score) | ⏳ Pending |
| 5 | Social & Traffic Automation (resume Pinterest) | ⏳ Pending |
| 6 | Conversion Optimization (sticky CTAs, exit popup) | ⏳ Pending |
| 7 | Audience Building (email + push) | ⏳ Pending |
| 8 | Analytics Dashboard | ⏳ Pending |
| 9 | Legal, Trust & Cookie System | ✅ Done |
| 10 | Future-Ready Architecture | ⏳ Pending |

Full roadmap: [`docs/REBUILD_PLAN_v3.md`](docs/REBUILD_PLAN_v3.md)

## Branches

- `main` — production. Auto-deployed to Netlify.
- `legacy-v1-starter` — preserved snapshot of the original v1 starter scaffold.

## License

Proprietary — © 2026 NEXORA.
