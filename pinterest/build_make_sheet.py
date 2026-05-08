#!/usr/bin/env python3
"""
NEXORA — Make.com Sheet Builder
================================================================
Reads the per-pin folder tree produced by `nexora_pinterest_v2.py`
(output_v2/upload/), uploads each pin.png to ImgBB to get a public
image URL, and writes a CSV that you import into Google Sheets.
That sheet then becomes the input for Make.com automations
(Pinterest, Facebook, Instagram, etc).

USAGE
-----
1. Get a free ImgBB API key at https://api.imgbb.com/ (sign up,
   then go to "About" → "API key"). It's free with unlimited
   storage.

2. Run:
       export IMGBB_API_KEY="your_key_here"
       python build_make_sheet.py

   Or pass the key directly:
       python build_make_sheet.py --imgbb-key your_key_here

3. The script writes:
       output_v2/make_sheet.csv          ← import to Google Sheets
       output_v2/make_sheet_uploads.json ← cache (so re-runs skip
                                            already-uploaded pins)

4. In Google Sheets:
       File → Import → Upload → make_sheet.csv → "Replace current
       sheet" or "Insert new sheet"

5. Connect Make.com to the sheet (see PINTEREST_AUTOMATION_GUIDE).

OPTIONS
-------
   --root DIR          where output_v2/upload/ lives (default: ./)
   --imgbb-key KEY     ImgBB API key (or env var IMGBB_API_KEY)
   --refresh           re-upload images (ignore cache)
   --dry-run           build CSV without uploading (debug)
   --output FILE       custom output CSV path

The CSV columns match the Google Sheet template that ships with
the Make.com blueprint.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

UPLOAD_ROOT = Path("output_v2/upload")
CACHE_FILE  = Path("output_v2/make_sheet_uploads.json")
CSV_FILE    = Path("output_v2/make_sheet.csv")

IMGBB_ENDPOINT = "https://api.imgbb.com/1/upload"

# These are the columns that Make.com expects to find in the sheet.
# Order matters — keep in sync with the imported blueprint.
CSV_COLUMNS = [
    "id",                      # unique row ID, e.g. "tech-01"
    "account_key",             # account1_morning | account2_night
    "category",                # tech | home | beauty | pet
    "style",                   # bold-dark | vibrant | minimalist | luxe | magazine | headline | splash
    "is_hot",                  # TRUE | FALSE
    "image_url",               # ImgBB hosted URL of pin.png
    "image_thumb_url",         # ImgBB thumbnail (for sheet preview)
    "title",                   # Pinterest title
    "description",             # Pinterest description
    "destination_url",         # NEXORA product page URL
    "board_name",              # Pinterest board name
    "publish_at",              # YYYY-MM-DD HH:MM (UTC) — empty = ASAP
    "status",                  # ready | scheduled | posted | error
    "posted_pinterest_at",     # filled by Make.com after success
    "pinterest_pin_id",        # filled by Make.com after success
    "posted_facebook_at",      # for future FB scenario
    "posted_instagram_at",     # for future IG scenario
    "posted_youtube_at",       # for future YT scenario
    "video_url",               # for YT/TT scenarios (you fill this)
    "notes",                   # any error / notes
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def read_text(p: Path) -> str:
    """Read text file, return empty string if missing."""
    try:
        return p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def parse_pin_folder(folder: Path) -> dict | None:
    """Extract metadata from a single pin folder. Uses meta.json if present
    (newer pins), else falls back to reading individual *.txt files."""
    pin_png = folder / "pin.png"
    if not pin_png.exists():
        return None

    # Path: output_v2/upload/<account_key>/<category>/<NN_slug>/
    parts = folder.parts
    try:
        account_key = parts[-3]   # account1_morning | account2_night
        category    = parts[-2]   # tech | home | beauty | pet
        folder_name = parts[-1]   # 01_voice-remote-...
    except IndexError:
        return None

    m = re.match(r"^(\d+)_(.+)$", folder_name)
    seq = m.group(1) if m else "00"

    # Prefer meta.json (structured)
    meta_path = folder / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return {
                "id":              meta.get("id") or f"{category}-{seq}",
                "account_key":     meta.get("account_key", account_key),
                "category":        meta.get("category", category),
                "style":           meta.get("style", ""),
                "is_hot":          "TRUE" if meta.get("is_hot") else "FALSE",
                "title":           meta.get("title", read_text(folder / "title.txt")),
                "description":     meta.get("description", read_text(folder / "description.txt")),
                "destination_url": meta.get("destination_url", read_text(folder / "link.txt")),
                "board_name":      meta.get("board", read_text(folder / "board.txt")),
                "_image_path":     str(pin_png),
            }
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: read individual files (older pin folders)
    return {
        "id":              f"{category}-{seq}",
        "account_key":     account_key,
        "category":        category,
        "style":           "",  # only populated when meta.json exists
        "is_hot":          "FALSE",  # determined later via Hot 6 URL match
        "title":           read_text(folder / "title.txt"),
        "description":     read_text(folder / "description.txt"),
        "destination_url": read_text(folder / "link.txt"),
        "board_name":      read_text(folder / "board.txt"),
        "_image_path":     str(pin_png),
    }


def collect_pins(upload_root: Path) -> list[dict]:
    """Walk output_v2/upload/ and return one dict per pin folder."""
    pins: list[dict] = []
    for account_dir in sorted(upload_root.iterdir()):
        if not account_dir.is_dir():
            continue
        for category_dir in sorted(account_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            for pin_folder in sorted(category_dir.iterdir()):
                if not pin_folder.is_dir():
                    continue
                row = parse_pin_folder(pin_folder)
                if row:
                    pins.append(row)
    return pins


def upload_to_imgbb(image_path: str, api_key: str, retries: int = 3) -> tuple[str, str]:
    """Upload an image to ImgBB. Returns (full_url, thumb_url).
    Raises RuntimeError on failure."""
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")

    name = Path(image_path).stem
    payload = urllib.parse.urlencode({
        "key":   api_key,
        "image": b64,
        "name":  f"nexora_{name}",
    }).encode("ascii")

    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                IMGBB_ENDPOINT,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                if not data.get("success"):
                    msg = data.get("error", {}).get("message", "(no message)")
                    raise RuntimeError(f"ImgBB rejected upload: {msg}")
                full = data["data"]["url"]
                thumb = data["data"].get("thumb", {}).get("url", full)
                return full, thumb
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                err_data = json.loads(err_body)
                msg = err_data.get("error", {}).get("message") or err_body[:200]
            except (json.JSONDecodeError, AttributeError):
                msg = f"HTTP {e.code}"
            last_err = f"{msg} (status {e.code})"
            if attempt < retries:
                time.sleep(2 ** attempt)
        except (urllib.error.URLError, RuntimeError, KeyError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Upload failed after {retries} attempts: {last_err}")


def load_cache(path: Path) -> dict[str, dict]:
    """Cache: {pin_id: {image_url, thumb_url, uploaded_at}}"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def make_default_publish_schedule(pins: list[dict]) -> dict[str, str]:
    """Return {pin_id: publish_at_iso} so Make.com has timestamps to start with.

    Strategy:
    • Account 1 (morning):  posts daily at 07:00, 09:00, 11:00, 13:00 US-East
    • Account 2 (night):    posts daily at 19:00, 21:00, 23:00 US-East
    • One pin per slot, no overlapping
    • Starts tomorrow (UTC)

    Note: these are *suggested* timestamps. You can edit them in
    the sheet directly. Format is ISO so Make can parse them."""
    schedule: dict[str, str] = {}

    # 7 AM ET == 11:00 UTC (during daylight saving). We'll use UTC throughout.
    SLOTS_BY_ACCOUNT = {
        "account1_morning": [11, 13, 15, 17],  # 7am-1pm ET
        "account2_night":   [23,  1,  3],       # 7pm-11pm ET (next day in UTC)
    }

    # Group pins by account
    by_account: dict[str, list[dict]] = {}
    for p in pins:
        by_account.setdefault(p["account_key"], []).append(p)

    base_day = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)

    for account, account_pins in by_account.items():
        slots = SLOTS_BY_ACCOUNT.get(account, [11])
        for i, p in enumerate(account_pins):
            day_offset = i // len(slots)
            slot_hour  = slots[i % len(slots)]
            slot_day   = base_day + timedelta(days=day_offset)
            # account2's late slots wrap into next day
            if account == "account2_night" and slot_hour < 12:
                slot_day += timedelta(days=1)
            ts = slot_day.replace(hour=slot_hour)
            schedule[p["id"]] = ts.strftime("%Y-%m-%d %H:%M:%S")

    return schedule


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="Path containing output_v2/upload/")
    ap.add_argument("--imgbb-key",
                    default=os.environ.get("IMGBB_API_KEY", ""),
                    help="ImgBB API key (or set IMGBB_API_KEY env var)")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-upload all images even if cached")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build CSV without uploading to ImgBB")
    ap.add_argument("--output", default=None, help="Output CSV path")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    upload_root = root / UPLOAD_ROOT
    cache_path  = root / CACHE_FILE
    csv_path    = Path(args.output).resolve() if args.output else (root / CSV_FILE)

    if not upload_root.is_dir():
        print(f"✗ Upload tree not found: {upload_root}")
        print("  Did you run nexora_pinterest_v2.py first?")
        return 2

    print("=" * 64)
    print(" NEXORA → Make.com Sheet Builder")
    print("=" * 64)
    print(f" Source:  {upload_root}")
    print(f" Output:  {csv_path}")
    print(f" Cache:   {cache_path}")
    print()

    # Validate ImgBB key (unless dry-run)
    if not args.dry_run and not args.imgbb_key:
        print("✗ Missing ImgBB API key.")
        print("  Get one free at https://api.imgbb.com/ then run:")
        print("      export IMGBB_API_KEY=your_key_here")
        print("      python build_make_sheet.py")
        return 3

    # Collect pins
    pins = collect_pins(upload_root)
    if not pins:
        print(f"✗ No pin folders found in {upload_root}")
        return 4

    print(f"✓ Found {len(pins)} pin folders")

    # Determine Hot 6 by reading the live homepage's ItemList markup.
    # Falls back to silent FALSE if site is unreachable.
    hot_urls: set[str] = set()
    try:
        sys.path.insert(0, str(root / "pinterest"))
        sys.path.insert(0, str(root))
        from nexora_pinterest_v2 import discover_hot_urls
        hot_urls = discover_hot_urls("https://nexora-shop-us.netlify.app")
        print(f"✓ Hot 6 detection: {len(hot_urls)} URLs flagged")
    except Exception as e:
        print(f"⚠ Hot 6 detection skipped: {e}")
        print("  (all pins will have is_hot=FALSE; you can edit the sheet manually)")

    if hot_urls:
        for p in pins:
            if p.get("destination_url", "").rstrip("/") in {u.rstrip("/") for u in hot_urls}:
                p["is_hot"] = "TRUE"

    print()

    # Upload images (with cache)
    cache = load_cache(cache_path)
    uploads_done = 0
    uploads_skipped = 0
    failures: list[tuple[str, str]] = []

    for i, p in enumerate(pins, 1):
        pid = p["id"]
        cached = cache.get(pid) if not args.refresh else None

        if cached and cached.get("image_url") and Path(p["_image_path"]).exists():
            p["image_url"]       = cached["image_url"]
            p["image_thumb_url"] = cached.get("thumb_url", cached["image_url"])
            uploads_skipped += 1
            continue

        if args.dry_run:
            p["image_url"]       = f"DRY_RUN://{pid}"
            p["image_thumb_url"] = f"DRY_RUN://{pid}"
            continue

        print(f"  [{i:02d}/{len(pins)}] Uploading {pid} ({Path(p['_image_path']).name}) ...", end="", flush=True)
        try:
            url, thumb = upload_to_imgbb(p["_image_path"], args.imgbb_key)
            p["image_url"]       = url
            p["image_thumb_url"] = thumb
            cache[pid] = {
                "image_url":   url,
                "thumb_url":   thumb,
                "uploaded_at": datetime.utcnow().isoformat() + "Z",
            }
            save_cache(cache_path, cache)
            uploads_done += 1
            print(" ✓")
        except Exception as e:
            failures.append((pid, str(e)))
            p["image_url"]       = ""
            p["image_thumb_url"] = ""
            print(f" ✗ {e}")

    print()
    print(f" ✓ Uploaded:  {uploads_done}")
    print(f" ⭢ Skipped:   {uploads_skipped} (cached)")
    if failures:
        print(f" ✗ Failed:    {len(failures)}")
        for pid, err in failures[:5]:
            print(f"    • {pid}: {err}")

    # Add schedule
    schedule = make_default_publish_schedule(pins)
    for p in pins:
        p["publish_at"] = schedule.get(p["id"], "")
        p["status"]     = "ready"
        # Initialize empty future-fill columns
        for col in (
            "posted_pinterest_at", "pinterest_pin_id",
            "posted_facebook_at", "posted_instagram_at", "posted_youtube_at",
            "video_url", "notes",
        ):
            p.setdefault(col, "")

    # Write CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for p in pins:
            writer.writerow(p)

    print()
    print(f" ✓ CSV written: {csv_path}")
    print(f"   {len(pins)} rows × {len(CSV_COLUMNS)} columns")
    print()
    print(" NEXT STEPS:")
    print(" 1. Open Google Sheets → File → Import → Upload")
    print(f"    Upload: {csv_path}")
    print("    Choose: Replace current sheet (or Insert new)")
    print()
    print(" 2. In Make.com, import the Pinterest blueprint and connect")
    print("    your sheet + Pinterest accounts. See:")
    print("    PINTEREST_AUTOMATION_GUIDE.md")
    print()
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
