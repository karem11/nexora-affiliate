# Make.com Blueprints

These JSON files are ready-to-import scenarios for Make.com.
Each one automates posting from your Google Sheet to a specific platform.

## How to import

1. Open https://make.com → Scenarios → "Create a new scenario"
2. In the empty canvas, click ⋯ (three dots) at the bottom
3. Choose "Import Blueprint"
4. Upload one of the JSON files below
5. Reconnect the modules (Google Sheet ID, Pinterest accounts, etc.)

See `../PINTEREST_AUTOMATION_GUIDE.md` for a full step-by-step walkthrough.

## Available blueprints

| File | Status | Purpose |
|------|--------|---------|
| `blueprint_pinterest_auto_poster.json` | ✅ Ready | Posts pins to 2 Pinterest Business accounts on schedule (1 hour) |
| `blueprint_facebook_auto_poster.json`  | 🚧 Phase 7C | (will be added once Pinterest is verified working) |
| `blueprint_instagram_auto_poster.json` | 🚧 Phase 7C | (will be added once Pinterest is verified working) |
| `blueprint_youtube_auto_uploader.json` | 🚧 Phase 7D | (will be added once you have promo videos) |
| `blueprint_tiktok_via_buffer.json`     | 🚧 Phase 7E | (deferred — requires Buffer/Zapier middle layer) |

## Important placeholders to replace after import

When you import a blueprint, look for these strings and replace them:

- `REPLACE_WITH_YOUR_SHEET_ID` → the Google Sheet ID from your URL
- `REPLACE_WITH_BOARD_ID_ACCOUNT1` → after connecting Pinterest, pick from dropdown
- `REPLACE_WITH_BOARD_ID_ACCOUNT2` → after connecting Pinterest, pick from dropdown

Make.com will mark unresolved placeholders with a ⚠ icon on the affected modules.
