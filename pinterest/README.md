# NEXORA Pinterest Pin Generator

This package contains:

```
nexora-pinterest/
├── output/
│   ├── pins/
│   │   ├── tech/    (8 pins — Bold Dark · Vibrant · Minimalist · Luxe)
│   │   ├── home/    (7 pins — Minimalist · Vibrant · Bold · Luxe)
│   │   ├── beauty/  (8 pins — Luxe · Minimalist · Vibrant · Bold)
│   │   └── pet/     (7 pins — Vibrant · Bold · Minimalist · Luxe)
│   └── nexora_pins.csv          (30 rows, ready for Pinterest Bulk Create)
├── PINTEREST_SETUP_GUIDE.md     (Arabic + English step-by-step)
├── nexora_pinterest_generator.py (regenerate any time as products.js changes)
├── fonts/                        (Inter typeface, required by generator)
├── nexora_logo.png
└── requirements.txt
```

## Quick start

1. **Read** `PINTEREST_SETUP_GUIDE.md` end to end (5–10 min).
2. **Create** a free Pinterest Business account.
3. **Upload** the 30 PNGs from `output/pins/` + `output/nexora_pins.csv` via Pinterest Bulk Create.
4. **Schedule** them across 14 days (Pinterest does this automatically when you select "Spread evenly").
5. **Watch** organic traffic come in over 2–8 weeks.

## Re-running the generator

The generator reads the live `products.js` from the website project. Whenever
you update products (new items, new prices, new discounts), you can refresh the
pin set with:

```bash
cd nexora-pinterest
pip install -r requirements.txt
python nexora_pinterest_generator.py --style mix
```

Available styles: `bold-dark`, `minimalist`, `luxe`, `vibrant`, `mix` (default).

`mix` rotates through all four styles per category — the recommended setting for
Pinterest reach (Pinterest's algorithm penalises visually identical batches).

## Pin specs

- **Resolution:** 1000 × 1500 (2:3, Pinterest-recommended)
- **Format:** PNG, optimized
- **Branding:** NEXORA logo + tagline + footer URL on every pin
- **Affiliate:** every link uses tag `kareemelsay0a-20`

— NEXORA · Smart Finds. Better Life.
