"""Generate one sample pin per style for comparison.
Usage: python _make_style_samples.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nexora_pinterest_generator import (
    load_products, fonts, make_pin, DEFAULT_PRODUCTS_JS, OUTPUT_DIR
)

SAMPLES_DIR = OUTPUT_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

products = load_products(DEFAULT_PRODUCTS_JS)
F = fonts()

# Pick 4 products across categories — one per pin style for variety
# (bold-dark on tech, minimalist on home, luxe on beauty, vibrant on pet)
chosen = {
    "bold-dark":   ("tech",   "01_tech"),
    "minimalist":  ("home",   "02_home"),
    "luxe":        ("beauty", "03_beauty"),
    "vibrant":     ("pet",    "04_pet"),
}

# Find one product per category
by_cat = {}
for p in products:
    by_cat.setdefault(p["category"], []).append(p)

for style, (cat, prefix) in chosen.items():
    if cat not in by_cat:
        continue
    p = by_cat[cat][0]
    out = SAMPLES_DIR / f"sample_{style}_{cat}.png"
    pin = make_pin(p, F, style=style)
    pin.save(out, "PNG", optimize=True)
    print(f"✓ {out}")

print()
print("Done — see output/samples/")
