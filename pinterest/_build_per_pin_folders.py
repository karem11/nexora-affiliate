"""Reorganize the master CSV + pin images into per-pin folders.

For each pin, creates a self-contained folder containing:
  pin.png          — the image
  info.txt         — full human-readable summary (title + desc + link + board + account)
  title.txt        — title only (quick copy-paste)
  description.txt  — description only, formatted with line breaks
  link.txt         — affiliate link only

Folder layout:
  output/upload/
    account1_morning/
      tech/
        01_voice-remote-control.../
          pin.png
          info.txt
          title.txt
          description.txt
          link.txt
      home/
        06_owala-disney-princess.../
          ...
    account2_night/
      beauty/...
      pet/...
"""
import csv
import shutil
from pathlib import Path

ROOT      = Path(__file__).parent
CSV_PATH  = ROOT / "output" / "nexora_pins.csv"
PINS_DIR  = ROOT / "output" / "pins"
DEST_ROOT = ROOT / "output" / "upload"

ACCOUNTS = {
    "account1_morning": {"tech", "home"},
    "account2_night":   {"beauty", "pet"},
}
ACCOUNT_LABEL = {
    "account1_morning": "Account 1 — Morning (7-10 AM US)",
    "account2_night":   "Account 2 — Night (8-11 PM US)",
}


def slugify_for_dir(image_path: str) -> str:
    """tech/01_voice-remote-control.png → 01_voice-remote-control"""
    name = Path(image_path).name
    return name.rsplit(".", 1)[0]


def format_description(desc: str) -> str:
    """Take the single-line CSV description and split it into readable lines.

    The description is built like:
      ✨ Title 💰 Now $price — discount. ⭐ 4.3 stars (N reviews). 🔥 social. Curated by NEXORA…
      As an Amazon Associate… #tags #tags
    We split on the emoji separators AND at "Curated by", "As an Amazon"
    and the hashtag block so each part is on its own line.
    """
    EMOJIS = ["✨", "💰", "⭐", "🔥"]

    rest = desc
    parts = []
    for em in EMOJIS:
        idx = rest.find(em)
        if idx > 0:
            parts.append(rest[:idx].rstrip())
            rest = rest[idx:]
    parts.append(rest)
    parts = [p.strip() for p in parts if p.strip()]

    # The last part starting with 🔥 likely contains "🔥 …. Curated by … As an Amazon … #tags".
    # Split it on the 'Curated by', 'As an Amazon', and '#' boundaries.
    last = parts[-1]
    if last.startswith("🔥"):
        rest = last
        sub_parts = []
        # Pull out the "🔥 ..." up to the next sentence-ending followed by 'Curated' or 'As an'
        for marker in ("Curated by", "As an Amazon"):
            idx = rest.find(marker)
            if idx > 0:
                sub_parts.append(rest[:idx].rstrip(" ."))
                rest = rest[idx:]
        sub_parts.append(rest)
        sub_parts = [s.strip() for s in sub_parts if s.strip()]

        # Split off hashtags from the very last segment
        cleaned = []
        for s in sub_parts:
            if "#" in s and not s.startswith("#"):
                main, _, tags = s.partition("#")
                main = main.strip()
                if main:
                    cleaned.append(main)
                cleaned.append("")  # blank line before hashtags
                cleaned.append("#" + tags.strip())
            else:
                cleaned.append(s)
        parts = parts[:-1] + cleaned

    return "\n".join(parts)


def render_info(row: dict, account_key: str, cat: str) -> str:
    return f"""\
================================================================
NEXORA Pinterest Pin
================================================================

ACCOUNT  : {ACCOUNT_LABEL[account_key]}
CATEGORY : {cat.upper()}
BOARD    : {row['Board']}

----------------------------------------------------------------
TITLE  (paste into Pinterest "Title" field)
----------------------------------------------------------------
{row['Title']}

----------------------------------------------------------------
DESCRIPTION  (paste into Pinterest "Description" field)
----------------------------------------------------------------
{format_description(row['Pin description'])}

----------------------------------------------------------------
DESTINATION LINK  (paste into Pinterest "Destination URL" field)
----------------------------------------------------------------
{row['Link']}

----------------------------------------------------------------
KEYWORDS / TAGS  (Pinterest no longer requires these but they help)
----------------------------------------------------------------
{row['Keywords']}

================================================================
HOW TO USE THIS FOLDER
================================================================
1. Drag pin.png into Pinterest's "Create Pin" image area.
2. Open title.txt → copy → paste into "Title".
3. Open description.txt → copy → paste into "Description".
4. Open link.txt → copy → paste into "Destination URL".
5. Select board: {row['Board']}
6. Click "Publish" or "Schedule".
================================================================
"""


def main():
    if DEST_ROOT.exists():
        shutil.rmtree(DEST_ROOT)
    DEST_ROOT.mkdir(parents=True)

    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    counts = {k: 0 for k in ACCOUNTS}
    for row in rows:
        image_path = row["Image file"]      # tech/01_…png
        cat = image_path.split("/")[0]
        account_key = next((k for k, cats in ACCOUNTS.items() if cat in cats), None)
        if account_key is None:
            print(f"  [skip] {image_path} — unknown category")
            continue

        slug   = slugify_for_dir(image_path)
        folder = DEST_ROOT / account_key / cat / slug
        folder.mkdir(parents=True, exist_ok=True)

        # Copy image
        src_img = PINS_DIR / image_path
        if not src_img.exists():
            print(f"  [warn] missing image {src_img}")
            continue
        shutil.copy(src_img, folder / "pin.png")

        # info.txt
        (folder / "info.txt").write_text(render_info(row, account_key, cat), encoding="utf-8")

        # quick-copy files
        (folder / "title.txt").write_text(row["Title"], encoding="utf-8")
        (folder / "description.txt").write_text(
            format_description(row["Pin description"]), encoding="utf-8"
        )
        (folder / "link.txt").write_text(row["Link"], encoding="utf-8")
        (folder / "board.txt").write_text(row["Board"], encoding="utf-8")

        counts[account_key] += 1
        print(f"  ✓ {account_key}/{cat}/{slug}")

    print()
    print("Summary:")
    for k, n in counts.items():
        print(f"  • {k}: {n} pins")
    print(f"\nOutput root: {DEST_ROOT}")


if __name__ == "__main__":
    main()
