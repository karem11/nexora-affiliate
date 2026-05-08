"""
NEXORA Market Intelligence v2 - Enhanced
=========================================

Enhancements over v1:
  1. Real Google Trends via pytrends (not Selenium scraping).
  2. Profit Calculator - estimated monthly commission per opportunity.
  3. Trend Direction - rising / falling / stable from interest_over_time.
  4. Competition Checker - Amazon results count + saturation tier.
  5. Deep Amazon Analysis - price, rating, reviews, BSR, brand, prime, image.
  6. SQLite cache (TTL), ThreadPoolExecutor concurrency, retry/backoff.
  7. Multi-factor weighted scoring.
  8. Export to CSV / Excel / JSON.
  9. CLI mode (--no-gui) for headless / scheduled runs.
 10. Filter / sort + detail modal in GUI.
 11. Structured logging with file + console handlers.
 12. User-Agent rotation for Amazon scraping.
 13. Related-queries expansion via pytrends.

Run:
    GUI:  python nexora_market_intelligence_v2.py
    CLI:  python nexora_market_intelligence_v2.py --no-gui --sources google,amazon \
              --top 30 --export results.xlsx --deep
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import requests
from bs4 import BeautifulSoup

# ---------- Compat shim: pytrends 4.9.x calls urllib3 Retry(method_whitelist=...)
# which was removed in urllib3>=2.0. Patch it to accept the deprecated kwarg as an
# alias for allowed_methods. See pytrends issue #591.
try:
    import urllib3.util.retry as _retry_mod  # type: ignore

    _retry_orig_init = _retry_mod.Retry.__init__

    def _retry_patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        if "method_whitelist" in kwargs and "allowed_methods" not in kwargs:
            kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
        else:
            kwargs.pop("method_whitelist", None)
        _retry_orig_init(self, *args, **kwargs)

    _retry_mod.Retry.__init__ = _retry_patched_init  # type: ignore[assignment]
except Exception:
    pass

# ---------- Optional dependencies (graceful fallback) ----------
try:
    from pytrends.request import TrendReq  # type: ignore
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False

try:
    import pandas as pd  # type: ignore
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options  # type: ignore
    from selenium.webdriver.chrome.service import Service  # type: ignore
    from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


# ============================================================
# CONFIG
# ============================================================
APP_DIR = Path.home() / ".nexora"
APP_DIR.mkdir(exist_ok=True)
CACHE_DB = APP_DIR / "cache.sqlite3"
LOG_FILE = APP_DIR / "nexora.log"

CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours (default)
PYTRENDS_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h for Google Trends (heavy rate limit)

CATEGORIES = ["tech", "home", "beauty", "pet"]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tech": [
        "laptop", "phone", "tablet", "headphone", "speaker", "wireless", "smart",
        "gaming", "charger", "bluetooth", "earbuds", "mouse", "keyboard", "monitor",
        "webcam", "router", "ssd", "usb", "hdmi", "tech", "gadget", "electronic",
        "tv", "watch", "drone", "camera", "console", "airpods", "iphone", "android",
        "robot vacuum", "smartwatch",
    ],
    "home": [
        "kitchen", "organizer", "storage", "furniture", "decor", "cleaning",
        "cookware", "appliance", "blender", "air fryer", "vacuum", "lamp",
        "bedding", "curtain", "rug", "shelf", "home", "desk", "office", "garden",
        "outdoor", "bathroom", "bedroom", "laundry", "gym equipment",
        "fitness equipment", "exercise",
    ],
    "beauty": [
        "skincare", "makeup", "hair", "serum", "moisturizer", "beauty", "cosmetic",
        "fragrance", "shampoo", "cream", "lipstick", "mascara", "perfume",
        "nail", "lash", "wax", "sunscreen", "balm", "lotion", "deodorant",
    ],
    "pet": [
        "dog", "cat", "pet", "grooming", "collar", "leash",
        "aquarium", "puppy", "kitten", "treat", "litter",
    ],
}

# Amazon Associates approximate commission rates (US, 2024)
COMMISSION_RATES: dict[str, float] = {
    "tech": 0.025,    # Electronics ~2.5%
    "home": 0.030,    # Home & Kitchen ~3%
    "beauty": 0.060,  # Beauty / Luxury Beauty 4-10%, conservative 6%
    "pet": 0.040,     # Pet Supplies ~4%
    "other": 0.030,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

AMAZON_MOVERS_PATHS = {
    "tech": "/gp/movers-and-shakers/electronics",
    "home": "/gp/movers-and-shakers/home-garden",
    "beauty": "/gp/movers-and-shakers/beauty",
    "pet": "/gp/movers-and-shakers/pet-supplies",
}

# Amazon marketplaces — domain + currency + pytrends geo
MARKETPLACES: dict[str, dict[str, str]] = {
    "us": {"domain": "amazon.com",    "currency": "USD", "geo": "US", "name": "Amazon US"},
    "uk": {"domain": "amazon.co.uk",  "currency": "GBP", "geo": "GB", "name": "Amazon UK"},
    "de": {"domain": "amazon.de",     "currency": "EUR", "geo": "DE", "name": "Amazon Germany"},
    "fr": {"domain": "amazon.fr",     "currency": "EUR", "geo": "FR", "name": "Amazon France"},
    "it": {"domain": "amazon.it",     "currency": "EUR", "geo": "IT", "name": "Amazon Italy"},
    "es": {"domain": "amazon.es",     "currency": "EUR", "geo": "ES", "name": "Amazon Spain"},
}

CONFIG_FILE = APP_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "marketplace": "us",
    "affiliate_tags": {mp: "" for mp in MARKETPLACES},
    "top_per_category": 5,
    "products_js_path": "",  # local path to website's products.js
}


def load_config() -> dict[str, Any]:
    """Load ~/.nexora/config.json, merged with defaults."""
    cfg: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg["marketplace"] = user.get("marketplace", cfg["marketplace"])
            cfg["top_per_category"] = int(user.get("top_per_category", cfg["top_per_category"]))
            cfg["affiliate_tags"].update(user.get("affiliate_tags", {}))
            cfg["products_js_path"] = user.get(
                "products_js_path", cfg["products_js_path"]
            )
        except Exception as exc:
            log_msg = f"config load failed: {exc}"
            print(log_msg, file=sys.stderr)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def affiliate_url(
    asin: str = "",
    keyword: str = "",
    marketplace: str = "us",
    tag: str = "",
) -> str:
    """Build an Amazon URL (deep-link if ASIN, else search) with affiliate tag."""
    mp = MARKETPLACES.get(marketplace, MARKETPLACES["us"])
    domain = mp["domain"]
    if asin:
        url = f"https://www.{domain}/dp/{asin}"
    elif keyword:
        url = f"https://www.{domain}/s?k={requests.utils.quote(keyword)}"
    else:
        return ""
    if tag:
        sep = "&" if "?" in url else "?"
        url += f"{sep}tag={tag}"
    return url


# ============================================================
# LOGGING
# ============================================================
def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("nexora")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO if not verbose else logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


log = setup_logging()


# ============================================================
# RETRY DECORATOR
# ============================================================
def retry(
    attempts: int = 3,
    initial_delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
):
    """Simple exponential-backoff retry decorator."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exc: BaseException | None = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    log.warning("retry %s/%s for %s failed: %s", i + 1, attempts, fn.__name__, exc)
                    if i < attempts - 1:
                        time.sleep(delay)
                        delay *= backoff
            assert last_exc is not None
            raise last_exc
        return wrapper
    return deco


# ============================================================
# CACHE (SQLite, TTL)
# ============================================================
class Cache:
    """Thread-safe SQLite key-value cache with TTL."""

    def __init__(self, path: Path = CACHE_DB, ttl: int = CACHE_TTL_SECONDS) -> None:
        self.path = path
        self.ttl = ttl
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )

    def get(self, key: str, ttl: int | None = None) -> Any | None:
        """Read a value. If `ttl` is given, override the default TTL for this read."""
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, created_at = row
        effective_ttl = ttl if ttl is not None else self.ttl
        if time.time() - created_at > effective_ttl:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, created_at) VALUES (?, ?, ?)",
                (key, payload, time.time()),
            )

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM cache")

    def clear_prefix(self, prefix: str) -> int:
        """Delete cache entries whose key starts with the given prefix."""
        with self._lock, sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                "DELETE FROM cache WHERE key LIKE ?", (prefix + "%",)
            )
            return cur.rowcount or 0


cache = Cache()


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class TrendInfo:
    """Trend direction for a keyword."""
    direction: str = "unknown"  # rising / falling / stable / unknown
    change_pct: float = 0.0      # percent change recent vs previous window
    avg_recent: float = 0.0
    avg_previous: float = 0.0
    sparkline: str = ""           # emoji sparkline


@dataclass
class AmazonDetail:
    """Deep details about an Amazon product."""
    asin: str = ""
    title: str = ""
    price: float | None = None
    list_price: float | None = None  # strikethrough / "was" price
    currency: str = "USD"
    rating: float | None = None
    review_count: int | None = None
    bsr: int | None = None
    bsr_category: str = ""
    brand: str = ""
    prime: bool = False
    image_url: str = ""
    availability: str = ""
    variations_count: int = 0
    url: str = ""


@dataclass
class ProfitEstimate:
    """Expected monthly commission."""
    price: float = 0.0
    estimated_monthly_sales: int = 0
    commission_rate: float = 0.0
    commission_per_sale: float = 0.0
    estimated_monthly_commission: float = 0.0
    confidence: str = "low"  # low / medium / high


@dataclass
class CompetitionInfo:
    """Competition saturation info."""
    results_count: int = 0
    tier: str = "unknown"  # low / medium / high / saturated / unknown
    sponsored_count: int = 0


@dataclass
class Opportunity:
    """One market opportunity (a keyword or a product)."""
    keyword: str = ""
    title: str = ""
    asin: str = ""
    source: str = ""
    category: str = "other"
    type: str = ""              # rising / viral / visual_trend / movers ...
    traffic: int = 0
    url: str = ""

    # enriched
    trend: TrendInfo = field(default_factory=TrendInfo)
    amazon: AmazonDetail | None = None
    profit: ProfitEstimate | None = None
    competition: CompetitionInfo | None = None

    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)

    def label(self) -> str:
        return self.keyword or self.title or self.asin or "unknown"

    def to_flat_dict(self, marketplace: str = "us", tag: str = "") -> dict[str, Any]:
        """Flatten nested dataclasses for CSV/Excel export.

        If `tag` is provided, includes affiliate_url for the given marketplace.
        """
        d: dict[str, Any] = {
            "label": self.label(),
            "keyword": self.keyword,
            "title": self.title,
            "asin": self.asin,
            "source": self.source,
            "category": self.category,
            "type": self.type,
            "traffic": self.traffic,
            "url": self.url,
            "affiliate_url": affiliate_url(self.asin, self.keyword, marketplace, tag),
            "score": self.score,
            "trend_direction": self.trend.direction,
            "trend_change_pct": self.trend.change_pct,
        }
        if self.amazon:
            d.update({
                "price": self.amazon.price,
                "rating": self.amazon.rating,
                "review_count": self.amazon.review_count,
                "bsr": self.amazon.bsr,
                "brand": self.amazon.brand,
                "prime": self.amazon.prime,
                "image_url": self.amazon.image_url,
            })
        if self.profit:
            d.update({
                "estimated_monthly_sales": self.profit.estimated_monthly_sales,
                "commission_rate": self.profit.commission_rate,
                "estimated_monthly_commission_usd": self.profit.estimated_monthly_commission,
            })
        if self.competition:
            d.update({
                "competition_results_count": self.competition.results_count,
                "competition_tier": self.competition.tier,
            })
        return d


# ============================================================
# UTILITIES
# ============================================================
def random_ua() -> str:
    return random.choice(USER_AGENTS)


def http_headers() -> dict[str, str]:
    return {
        "User-Agent": random_ua(),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def categorize(keyword: str = "", title: str = "") -> str:
    text = f"{keyword} {title}".lower()
    scores: dict[str, int] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        count = sum(1 for k in kws if k in text)
        if count:
            scores[cat] = count
    return max(scores, key=lambda k: scores[k]) if scores else "other"


def sparkline_for(change_pct: float) -> str:
    if change_pct > 20:
        return "🚀📈"
    if change_pct > 5:
        return "📈"
    if change_pct < -20:
        return "📉⚠️"
    if change_pct < -5:
        return "📉"
    return "➡️"


# ============================================================
# Cache <-> dataclass helpers
# ============================================================
def _opp_from_cached(d: dict[str, Any]) -> Opportunity:
    """Rebuild an Opportunity from a cached flat dict.

    Cached dicts may contain serialized nested dataclasses (trend, amazon,
    profit, competition) — we either rebuild them as their proper dataclass
    types or drop them in favor of defaults so downstream code never sees a
    plain dict where it expects a TrendInfo / CompetitionInfo / etc.
    """
    if not isinstance(d, dict):
        return Opportunity()
    base_fields = {
        "keyword", "title", "asin", "source", "category", "type",
        "traffic", "url", "score",
    }
    base = {k: v for k, v in d.items() if k in base_fields}
    opp = Opportunity(**base)
    t = d.get("trend")
    if isinstance(t, dict):
        try:
            opp.trend = TrendInfo(**t)
        except Exception:
            opp.trend = TrendInfo()
    a = d.get("amazon")
    if isinstance(a, dict):
        try:
            opp.amazon = AmazonDetail(**a)
        except Exception:
            opp.amazon = None
    p = d.get("profit")
    if isinstance(p, dict):
        try:
            opp.profit = ProfitEstimate(**p)
        except Exception:
            opp.profit = None
    c = d.get("competition")
    if isinstance(c, dict):
        try:
            opp.competition = CompetitionInfo(**c)
        except Exception:
            opp.competition = None
    sb = d.get("score_breakdown")
    if isinstance(sb, dict):
        opp.score_breakdown = sb
    return opp


# ============================================================
# GOOGLE TRENDS (pytrends)
# ============================================================
class GoogleTrendsSource:
    """Real Google Trends data via pytrends.

    Pytrends/Google rate-limit aggressively, so all API calls are serialized
    through a class-level lock with a randomized human-like delay between
    calls. After repeated 429s, a circuit breaker disables Google for the
    rest of the session and Amazon Movers / source-direction takes over.

    Strategy:
      • Every call: jittered sleep between MIN_INTERVAL and MAX_INTERVAL
      • On 429: exponential cool-down (30s → 60s → 120s → 240s, capped)
      • After CIRCUIT_LIMIT consecutive failures: disable for the session
      • Cascading 429s in the same minute are collapsed into one log line
    """

    _api_lock = threading.Lock()
    _last_call_at: float = 0.0

    # Human-like jitter — wider range looks less bot-like to Google.
    _MIN_INTERVAL: float = 4.0   # seconds
    _MAX_INTERVAL: float = 8.0   # seconds

    # Circuit breaker
    _failure_count: int = 0
    _CIRCUIT_LIMIT: int = 5
    _disabled_until: float = 0.0  # timestamp; while now() < this, we skip Google
    _COOLDOWN_BASE: float = 30.0  # seconds for first cool-down
    _COOLDOWN_MAX: float = 240.0

    # Log spam suppression
    _last_failure_logged_at: float = 0.0
    _suppressed_failures: int = 0
    _LOG_SUPPRESSION_WINDOW: float = 60.0  # collapse failures within this window

    def __init__(self, hl: str = "en-US", tz: int = 360, geo: str = "US") -> None:
        self.hl = hl
        self.tz = tz
        self.geo = geo
        self._client: TrendReq | None = None

    @classmethod
    def _throttle(cls) -> None:
        """Sleep enough to look human between consecutive Google calls."""
        now = time.time()
        delta = now - cls._last_call_at
        target = random.uniform(cls._MIN_INTERVAL, cls._MAX_INTERVAL)
        if delta < target:
            time.sleep(target - delta)
        cls._last_call_at = time.time()

    @classmethod
    def _is_circuit_open(cls) -> bool:
        """Returns True if we should skip Google calls (cool-down or session-disabled)."""
        return time.time() < cls._disabled_until

    @classmethod
    def _note_failure(cls, label: str, exc: Exception) -> None:
        """Track a Google failure: log smartly + arm exponential cool-down."""
        cls._failure_count += 1
        msg = str(exc)
        is_429 = "429" in msg or "Too Many Requests" in msg

        # Exponential cool-down on 429
        if is_429:
            # 30, 60, 120, 240 (cap)
            backoff = min(
                cls._COOLDOWN_BASE * (2 ** (cls._failure_count - 1)),
                cls._COOLDOWN_MAX,
            )
            cls._disabled_until = time.time() + backoff
        # Circuit breaker: too many failures → disable for rest of session
        if cls._failure_count >= cls._CIRCUIT_LIMIT:
            cls._disabled_until = time.time() + 60 * 60  # 1 hour effectively
            log.warning(
                "🚦 Google Trends circuit-broken after %d failures — using "
                "TikTok/Pinterest/Amazon for the rest of this run.",
                cls._failure_count,
            )
            return

        # Log spam suppression
        now = time.time()
        if now - cls._last_failure_logged_at < cls._LOG_SUPPRESSION_WINDOW:
            cls._suppressed_failures += 1
            return
        if cls._suppressed_failures > 0:
            log.warning(
                "Google Trends: %d more failures suppressed (rate-limited)",
                cls._suppressed_failures,
            )
            cls._suppressed_failures = 0
        if is_429:
            backoff = min(
                cls._COOLDOWN_BASE * (2 ** (cls._failure_count - 1)),
                cls._COOLDOWN_MAX,
            )
            log.warning(
                "Google Trends rate-limited (%s) — cooling down %.0fs",
                label, backoff,
            )
        else:
            log.warning("Google Trends call failed (%s): %s", label, exc)
        cls._last_failure_logged_at = now

    @classmethod
    def _note_success(cls) -> None:
        """Reset the failure counter on a successful call."""
        if cls._failure_count > 0:
            cls._failure_count = max(0, cls._failure_count - 1)
        cls._suppressed_failures = 0

    def _client_or_none(self) -> TrendReq | None:
        if not PYTRENDS_AVAILABLE:
            return None
        if self._client is None:
            try:
                # retries=0 to avoid pytrends hammering Google internally;
                # our @retry decorator + throttle handle backoff at a higher level.
                self._client = TrendReq(hl=self.hl, tz=self.tz, retries=0, timeout=(10, 25))
            except Exception as exc:
                log.warning("pytrends init failed: %s", exc)
                self._client = None
        return self._client

    # Fallback seed keywords — used when Google's trending_searches endpoint is down
    # (returns 404 sporadically). We expand each seed via related_rising to surface
    # real, currently-rising queries — much better than a static list.
    DEFAULT_SEEDS: list[str] = [
        "wireless earbuds", "smart watch", "robot vacuum", "air fryer",
        "skincare routine", "hair serum", "gaming mouse", "dog food",
    ]

    def trending_searches(self, country: str = "united_states", limit: int = 15) -> list[Opportunity]:
        client = self._client_or_none()
        if client is None:
            log.info("pytrends unavailable; using seeded fallback for trending")
            return []
        cache_key = f"trending:{country}:{limit}"
        cached = cache.get(cache_key, ttl=PYTRENDS_CACHE_TTL_SECONDS)
        if cached:
            return [self._dict_to_opp(d) for d in cached]

        if self._is_circuit_open():
            return []

        opps: list[Opportunity] = []
        # 1) Try the official pytrends endpoint
        try:
            with self._api_lock:
                self._throttle()
                df = client.trending_searches(pn=country)
            for kw in df.iloc[:limit, 0].tolist():
                opps.append(Opportunity(
                    keyword=str(kw).strip(),
                    source="Google Trends",
                    type="rising",
                    traffic=60000,
                ))
            self._note_success()
        except Exception as exc:
            self._note_failure("trending_searches", exc)

        # 2) Fallback: derive trending from related_rising on curated seeds
        if not opps and not self._is_circuit_open():
            log.info("Using seeded related-rising as trending discovery")
            for seed in self.DEFAULT_SEEDS:
                if len(opps) >= limit:
                    break
                if self._is_circuit_open():
                    break
                rising = self.related_rising(seed, limit=3)
                opps.extend(rising)
            opps = opps[:limit]

        if opps:
            cache.set(cache_key, [asdict(o) for o in opps])
        return opps

    def keyword_trend(self, keyword: str, lookback_days: int = 90) -> TrendInfo:
        """Return trend direction by comparing avg(last 30d) vs avg(prev 30d)."""
        client = self._client_or_none()
        if client is None or not keyword:
            return TrendInfo()
        cache_key = f"trend:{keyword.lower()}:{lookback_days}"
        cached = cache.get(cache_key, ttl=PYTRENDS_CACHE_TTL_SECONDS)
        if cached:
            return TrendInfo(**cached)
        if self._is_circuit_open():
            return TrendInfo()
        try:
            timeframe = "today 3-m" if lookback_days <= 90 else "today 12-m"
            with self._api_lock:
                self._throttle()
                client.build_payload([keyword], timeframe=timeframe, geo=self.geo)
                df = client.interest_over_time()
            self._note_success()
        except Exception as exc:
            self._note_failure(f"interest_over_time:{keyword}", exc)
            return TrendInfo()
        if df is None or df.empty or keyword not in df.columns:
            return TrendInfo()
        series = df[keyword].astype(float)
        if len(series) < 4:
            return TrendInfo()
        # split last 30d vs previous 30d
        cutoff = max(1, len(series) // 2)
        recent = float(series.iloc[-cutoff:].mean())
        previous = float(series.iloc[:-cutoff].mean()) or 0.001
        change_pct = float(((recent - previous) / previous) * 100.0)
        if change_pct > 10:
            direction = "rising"
        elif change_pct < -10:
            direction = "falling"
        else:
            direction = "stable"
        info = TrendInfo(
            direction=direction,
            change_pct=round(change_pct, 1),
            avg_recent=round(recent, 2),
            avg_previous=round(previous, 2),
            sparkline=sparkline_for(change_pct),
        )
        cache.set(cache_key, asdict(info))
        return info

    def related_rising(self, seed: str, limit: int = 5) -> list[Opportunity]:
        """Fetch rising related queries for a seed keyword."""
        client = self._client_or_none()
        if client is None or not seed:
            return []
        cache_key = f"related:{seed.lower()}:{limit}"
        cached = cache.get(cache_key, ttl=PYTRENDS_CACHE_TTL_SECONDS)
        if cached:
            return [self._dict_to_opp(d) for d in cached]
        if self._is_circuit_open():
            return []
        try:
            with self._api_lock:
                self._throttle()
                client.build_payload([seed], timeframe="today 3-m", geo=self.geo)
                related = client.related_queries() or {}
            self._note_success()
        except Exception as exc:
            self._note_failure(f"related_queries:{seed}", exc)
            return []
        result: list[Opportunity] = []
        node = related.get(seed) or {}
        rising_df = node.get("rising")
        if rising_df is None or rising_df.empty:
            return []
        for _, row in rising_df.head(limit).iterrows():
            kw = str(row.get("query", "")).strip()
            value = int(row.get("value", 0)) if row.get("value") is not None else 0
            if not kw:
                continue
            result.append(Opportunity(
                keyword=kw,
                source="Google Trends Related",
                type="rising",
                traffic=max(20000, value * 100),
            ))
        cache.set(cache_key, [asdict(o) for o in result])
        return result

    @staticmethod
    def _dict_to_opp(d: dict[str, Any]) -> Opportunity:
        # Reconstruct Opportunity from cached flat dict
        return _opp_from_cached(d)


# ============================================================
# PINTEREST / TIKTOK (lightweight; can be extended)
# ============================================================
def get_pinterest_trends() -> list[Opportunity]:
    raw = [
        ("aesthetic room decor", 70000),
        ("minimalist desk setup", 65000),
        ("pet organization ideas", 55000),
        ("skincare routine 2026", 80000),
        ("home gym equipment", 68000),
        ("kitchen organization hacks", 72000),
    ]
    return [
        Opportunity(keyword=k, source="Pinterest", type="visual_trend", traffic=t)
        for k, t in raw
    ]


def get_tiktok_trends() -> list[Opportunity]:
    raw = [
        ("tiktok made me buy it", 150000),
        ("amazon finds under 50", 130000),
        ("pet products must have", 110000),
        ("beauty hacks", 120000),
        ("kitchen must haves", 105000),
        ("tech accessories", 95000),
    ]
    return [
        Opportunity(keyword=k, source="TikTok", type="viral", traffic=t)
        for k, t in raw
    ]


# ============================================================
# AMAZON ANALYZER
# ============================================================
class AmazonAnalyzer:
    """Deep Amazon product analysis + competition + movers + ASIN lookup.

    Supports multiple marketplaces (US/UK/DE/FR/IT/ES) via the `marketplace`
    parameter, which determines the domain (amazon.com, amazon.co.uk, etc.).
    """

    def __init__(
        self,
        use_selenium: bool = False,
        headless: bool = True,
        marketplace: str = "us",
    ) -> None:
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.headless = headless
        self.marketplace = marketplace if marketplace in MARKETPLACES else "us"
        self.domain = MARKETPLACES[self.marketplace]["domain"]
        self.currency = MARKETPLACES[self.marketplace]["currency"]
        self._driver: Any = None
        self._session = requests.Session()
        # Force Amazon to serve USD/GBP/EUR (etc.) regardless of geolocation.
        # Without these cookies, Amazon may serve EGP / SAR / AED / etc. for
        # users in those regions even when accessing amazon.com / amazon.co.uk.
        self._set_currency_cookies()

    def _set_currency_cookies(self) -> None:
        """Pin Amazon's currency + locale via cookies on this session."""
        lc = "en_US" if self.currency == "USD" else "en_GB"
        try:
            for dom in (self.domain, f"www.{self.domain}", f".{self.domain}"):
                self._session.cookies.set("i18n-prefs", self.currency, domain=dom)
                self._session.cookies.set("lc-main", lc, domain=dom)
                # Some EU domains use lc-acbXX cookies
                self._session.cookies.set("lc-acbuk", lc, domain=dom)
                self._session.cookies.set("lc-acbde", lc, domain=dom)
        except Exception:
            pass

    @staticmethod
    def _with_currency_params(url: str, currency: str) -> str:
        """Append ?language=en_US&currency=USD to an Amazon URL."""
        sep = "&" if "?" in url else "?"
        lang = "en_US" if currency == "USD" else "en_GB"
        return f"{url}{sep}language={lang}&currency={currency}"

    # ---------- Selenium driver lifecycle ----------
    def start_driver(self) -> bool:
        if not self.use_selenium:
            return False
        if self._driver is not None:
            return True
        try:
            opts = Options()
            if self.headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--window-size=1280,900")
            opts.add_argument(f"--user-agent={random_ua()}")
            opts.add_experimental_option("excludeSwitches", ["enable-logging"])
            self._driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=opts,
            )
            return True
        except Exception as exc:
            log.error("selenium start failed: %s", exc)
            self.use_selenium = False
            return False

    def close_driver(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ---------- HTTP fetch with UA rotation ----------
    @retry(attempts=3, initial_delay=1.5, exceptions=(requests.RequestException,))
    def _http_get(self, url: str) -> str:
        resp = self._session.get(url, headers=http_headers(), timeout=15)
        resp.raise_for_status()
        return resp.text

    def _selenium_get(self, url: str) -> str | None:
        if not self.start_driver():
            return None
        try:
            self._driver.get(url)
            time.sleep(2.5)
            return self._driver.page_source
        except Exception as exc:
            log.warning("selenium get %s failed: %s", url, exc)
            return None

    # Amazon throttling: shared across instances, with random jitter so the
    # request pattern doesn't look bot-like.
    _amazon_lock = threading.Lock()
    _last_amazon_at: float = 0.0
    _AMAZON_MIN_INTERVAL: float = 1.0
    _AMAZON_MAX_INTERVAL: float = 3.0

    @classmethod
    def _amazon_throttle(cls) -> None:
        """Polite, jittered pause before each Amazon request."""
        with cls._amazon_lock:
            now = time.time()
            delta = now - cls._last_amazon_at
            target = random.uniform(
                cls._AMAZON_MIN_INTERVAL, cls._AMAZON_MAX_INTERVAL
            )
            if delta < target:
                time.sleep(target - delta)
            cls._last_amazon_at = time.time()

    def _fetch(self, url: str) -> str | None:
        """Try requests first, fallback to selenium. Throttled for politeness."""
        self._amazon_throttle()
        try:
            html = self._http_get(url)
            if html and "captcha" not in html.lower()[:5000]:
                return html
        except Exception as exc:
            log.warning("http get failed for %s: %s", url, exc)
        return self._selenium_get(url)

    # ---------- Movers & Shakers ----------
    def movers(self, category: str, path: str, limit: int = 8) -> list[Opportunity]:
        cache_key = f"movers:{self.marketplace}:{category}"
        cached = cache.get(cache_key)
        if cached:
            return [_opp_from_cached(d) for d in cached]
        url = f"https://www.{self.domain}{path}"
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("div[data-asin]")[:limit]
        out: list[Opportunity] = []
        for item in items:
            asin = (item.get("data-asin") or "").strip()
            if not asin or len(asin) != 10:
                continue
            title_el = item.select_one(
                "span.a-size-small, "
                "div._p13n-zg-list-grid-desktop_truncationStyles_p13n-sc-css-line-clamp-1__2q2cc a span, "
                "div.p13n-sc-truncated, "
                "a span"
            )
            title = title_el.get_text(strip=True) if title_el else f"Product {asin}"
            out.append(Opportunity(
                title=title,
                asin=asin,
                source="Amazon Movers",
                category=category,
                type="rising",
                traffic=35000,
                url=f"https://www.{self.domain}/dp/{asin}",
            ))
        cache.set(cache_key, [asdict(o) for o in out])
        return out

    # ---------- ASIN lookup (for keyword → product conversion) ----------
    def find_top_asin(self, keyword: str) -> str | None:
        """Search Amazon for a keyword; return ASIN of the first non-sponsored result.

        Used to convert keyword opportunities (from Google Trends / Pinterest /
        TikTok) into real linkable products with affiliate URLs.
        """
        if not keyword:
            return None
        cache_key = f"top_asin:{self.marketplace}:{keyword.lower()}"
        cached = cache.get(cache_key)
        if cached:
            return cached if isinstance(cached, str) else None
        url = f"https://www.{self.domain}/s?k={requests.utils.quote(keyword)}"
        html = self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select("div[data-asin][data-component-type='s-search-result']"):
            asin = (item.get("data-asin") or "").strip()
            if not asin or len(asin) != 10:
                continue
            # Skip sponsored
            txt = item.get_text(" ", strip=True).lower()
            if "sponsored" in txt[:200]:
                continue
            cache.set(cache_key, asin)
            return asin
        # Fallback: first ASIN even if sponsored (better than nothing)
        for item in soup.select("div[data-asin]"):
            asin = (item.get("data-asin") or "").strip()
            if asin and len(asin) == 10:
                cache.set(cache_key, asin)
                return asin
        return None

    # ---------- Competition (search results count) ----------
    def competition(self, keyword: str) -> CompetitionInfo:
        cache_key = f"competition:{self.marketplace}:{keyword.lower()}"
        cached = cache.get(cache_key)
        if cached:
            return CompetitionInfo(**cached)
        url = f"https://www.{self.domain}/s?k={requests.utils.quote(keyword)}"
        html = self._fetch(url)
        if not html:
            return CompetitionInfo()
        soup = BeautifulSoup(html, "lxml")

        # try multiple selectors that Amazon uses for results-count
        count = 0
        candidates = [
            "span.a-color-state.a-text-bold",
            "div.a-section.a-spacing-small.a-spacing-top-small > span",
            "h2.a-spacing-medium > span",
            "div.s-desktop-toolbar > div > div > div > span",
        ]
        for sel in candidates:
            for el in soup.select(sel):
                text = el.get_text(" ", strip=True)
                m = re.search(r"of\s+(?:over\s+)?([\d,]+)\s+results", text, re.I)
                if m:
                    count = int(m.group(1).replace(",", ""))
                    break
                m2 = re.search(r"([\d,]+)\s+results?\s+for", text, re.I)
                if m2:
                    count = int(m2.group(1).replace(",", ""))
                    break
            if count:
                break

        sponsored = len(soup.select(
            "span.s-sponsored-label-info-icon, span:-soup-contains('Sponsored')"
        ))

        if count <= 0:
            tier = "unknown"
        elif count < 1000:
            tier = "low"
        elif count < 10000:
            tier = "medium"
        elif count < 50000:
            tier = "high"
        else:
            tier = "saturated"

        info = CompetitionInfo(results_count=count, tier=tier, sponsored_count=sponsored)
        cache.set(cache_key, asdict(info))
        return info

    # ---------- Deep product detail ----------
    # NOTE: cache key version bumped to v2 to invalidate buggy price caches
    # from older versions (where prices could come from FBT/sponsored widgets).
    PRODUCT_CACHE_VERSION = "v3"

    def product_detail(self, asin: str) -> AmazonDetail | None:
        if not asin:
            return None
        cache_key = (
            f"product:{self.PRODUCT_CACHE_VERSION}:{self.marketplace}:{asin}"
        )
        cached = cache.get(cache_key)
        if cached:
            try:
                # Drop unknown keys from older cache schemas
                fields = {f.name for f in AmazonDetail.__dataclass_fields__.values()}
                clean = {k: v for k, v in cached.items() if k in fields}
                return AmazonDetail(**clean)
            except Exception as exc:
                log.warning("stale product cache for %s: %s", asin, exc)
        # Force Amazon to serve in the marketplace's native currency, even if
        # the request is coming from a country with a different local currency
        # (e.g. user in Egypt seeing EGP on amazon.com).
        url = self._with_currency_params(
            f"https://www.{self.domain}/dp/{asin}",
            self.currency,
        )
        html = self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else ""

        price, price_currency = self._extract_price_and_currency(soup)
        list_price, _ = self._extract_list_price_and_currency(soup)
        # Sanity: if list_price < price, swap them
        if (price is not None and list_price is not None
                and list_price < price):
            price, list_price = list_price, price
        rating = self._extract_rating(soup)
        review_count = self._extract_review_count(soup)
        bsr, bsr_cat = self._extract_bsr(soup)
        brand = self._extract_brand(soup)
        prime = self._extract_prime(soup)
        image_url = self._extract_image(soup)
        availability = self._extract_availability(soup)
        variations_count = len(soup.select("li.swatchAvailable, li.swatchSelect, li.swatchUnavailable"))

        # Pick the currency. Trust the actual scraped currency over the
        # marketplace default, because Amazon may serve a non-default currency
        # based on the user's geolocation despite our cookies.
        marketplace_currency = MARKETPLACES.get(
            self.marketplace, MARKETPLACES["us"]
        )["currency"]
        currency = price_currency or marketplace_currency

        # If the scraped currency disagrees with the marketplace currency
        # (e.g. user is in Egypt and Amazon served EGP despite our overrides),
        # we DROP the price rather than show a wrong number. The user can
        # still see the product, but no misleading "$730" for a $9 remote.
        if (
            price is not None
            and price_currency
            and price_currency != marketplace_currency
        ):
            log.warning(
                "Amazon served %s instead of %s for ASIN %s — dropping price "
                "to avoid wrong values. Set Chrome / VPN to a %s region for "
                "correct prices.",
                price_currency, marketplace_currency, asin,
                marketplace_currency,
            )
            price = None
            list_price = None
            currency = marketplace_currency

        detail = AmazonDetail(
            asin=asin,
            title=title,
            price=price,
            list_price=list_price,
            currency=currency,
            rating=rating,
            review_count=review_count,
            bsr=bsr,
            bsr_category=bsr_cat,
            brand=brand,
            prime=prime,
            image_url=image_url,
            availability=availability,
            variations_count=variations_count,
            url=url,
        )
        cache.set(cache_key, asdict(detail))
        return detail

    # ---------- Field extractors ----------
    @staticmethod
    def _to_float(text: str) -> float | None:
        m = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    # Containers we trust as "this product's own price area" (in priority order)
    _PRICE_CONTAINERS = (
        "#corePrice_feature_div",
        "#corePriceDisplay_desktop_feature_div",
        "#apex_desktop",
        "#apex_desktop_newAccordionRow",
        "#booksHeaderSection",
        "#price",
        "#price_feature_div",
        "#buybox",
    )

    # Map of common currency markers found in Amazon offscreen price text.
    # Order matters: longer markers (3-letter codes) checked before symbols.
    _CURRENCY_MARKERS: tuple[tuple[str, str], ...] = (
        ("EGP", "EGP"), ("SAR", "SAR"), ("AED", "AED"),
        ("USD", "USD"), ("GBP", "GBP"), ("EUR", "EUR"),
        ("CAD", "CAD"), ("AUD", "AUD"), ("INR", "INR"),
        ("JPY", "JPY"), ("CNY", "CNY"), ("MXN", "MXN"),
        ("BRL", "BRL"), ("PLN", "PLN"), ("SEK", "SEK"),
        ("TRY", "TRY"), ("ر.س", "SAR"), ("د.إ", "AED"),
        ("ج.م", "EGP"),
        ("£", "GBP"), ("€", "EUR"), ("¥", "JPY"),
        ("₹", "INR"), ("₺", "TRY"), ("₪", "ILS"),
        ("zł", "PLN"), ("kr", "SEK"), ("R$", "BRL"),
        ("$", "USD"),  # last fallback: bare $ → USD
    )

    @staticmethod
    def _detect_currency(text: str) -> str | None:
        """Read a price string and return its currency code (or None)."""
        if not text:
            return None
        t = text.strip()
        for marker, code in AmazonAnalyzer._CURRENCY_MARKERS:
            if marker in t:
                return code
        return None

    @staticmethod
    def _price_and_currency_from_text(text: str) -> tuple[float | None, str | None]:
        """Parse an Amazon price string like '$8.99' / 'EGP1,873.01' / '€12,99'."""
        if not text:
            return None, None
        currency = AmazonAnalyzer._detect_currency(text)
        # Strip non-numeric/separator characters first
        cleaned = re.sub(r"[^\d.,]", "", text)
        if not cleaned:
            return None, currency
        # Heuristic for European decimal format (e.g. "12,99")
        if "," in cleaned and "." not in cleaned:
            # If only one comma and 1-2 digits after → decimal comma
            if cleaned.count(",") == 1 and len(cleaned.split(",")[-1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            v = float(cleaned)
        except ValueError:
            return None, currency
        if v <= 0:
            return None, currency
        return round(v, 2), currency

    @staticmethod
    def _price_from_node(node: Any) -> tuple[float | None, str | None]:
        """Pull a (price, currency) out of a small Amazon node, ignoring
        strikethrough/list prices and aria-hidden duplicates."""
        if node is None:
            return None, None
        candidates = node.select("span.a-price")
        for c in candidates:
            color = (c.get("data-a-color") or "").lower()
            classes = " ".join(c.get("class") or [])
            if "a-text-price" in classes:
                continue
            if color == "secondary":
                continue
            offscreen = c.select_one("span.a-offscreen")
            if not offscreen:
                continue
            txt = offscreen.get_text(strip=True)
            v, cur = AmazonAnalyzer._price_and_currency_from_text(txt)
            if v is not None:
                return v, cur
        return None, None

    def _extract_price_and_currency(
        self, soup: BeautifulSoup
    ) -> tuple[float | None, str | None]:
        # 1) Trusted buy-box / core-price containers
        for cont_sel in self._PRICE_CONTAINERS:
            cont = soup.select_one(cont_sel)
            if not cont:
                continue
            v, cur = self._price_from_node(cont)
            if v is not None:
                return v, cur

        # 2) Legacy single-element selectors
        for sel in [
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            "span#price_inside_buybox",
            "#newBuyBoxPrice",
        ]:
            el = soup.select_one(sel)
            if el:
                v, cur = self._price_and_currency_from_text(
                    el.get_text(strip=True)
                )
                if v is not None:
                    return v, cur

        # 3) Last-resort fallback (filtered to avoid FBT / sponsored)
        BAD_ANCESTORS = {
            "sims-fbt", "fbt-feature", "valuePick_feature_div",
            "similarities_feature_div", "comparisonContainerHTML",
            "HLCXComparisonWidget_feature_div",
            "sponsoredProducts2_feature_div",
            "sp_detail", "sp_detail_thematic", "ds-related-purchases",
        }
        for c in soup.select("span.a-price"):
            classes = " ".join(c.get("class") or [])
            color = (c.get("data-a-color") or "").lower()
            if "a-text-price" in classes or color == "secondary":
                continue
            anc = c
            bad = False
            for _ in range(10):
                anc = anc.parent
                if anc is None:
                    break
                anc_id = (anc.get("id") or "") if hasattr(anc, "get") else ""
                anc_class = " ".join(
                    anc.get("class") or []
                ) if hasattr(anc, "get") else ""
                if anc_id in BAD_ANCESTORS or any(
                    b in anc_class for b in BAD_ANCESTORS
                ):
                    bad = True
                    break
            if bad:
                continue
            offscreen = c.select_one("span.a-offscreen")
            if not offscreen:
                continue
            v, cur = self._price_and_currency_from_text(
                offscreen.get_text(strip=True)
            )
            if v is not None:
                return v, cur
        return None, None

    def _extract_list_price_and_currency(
        self, soup: BeautifulSoup
    ) -> tuple[float | None, str | None]:
        for cont_sel in self._PRICE_CONTAINERS:
            cont = soup.select_one(cont_sel)
            if not cont:
                continue
            for c in cont.select("span.a-price"):
                color = (c.get("data-a-color") or "").lower()
                classes = " ".join(c.get("class") or [])
                is_list = (
                    color == "secondary"
                    or "a-text-price" in classes
                )
                if not is_list:
                    continue
                offscreen = c.select_one("span.a-offscreen")
                if not offscreen:
                    continue
                v, cur = self._price_and_currency_from_text(
                    offscreen.get_text(strip=True)
                )
                if v is not None:
                    return v, cur
        return None, None

    # Backward-compat thin wrappers
    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        v, _ = self._extract_price_and_currency(soup)
        return v

    def _extract_list_price(self, soup: BeautifulSoup) -> float | None:
        v, _ = self._extract_list_price_and_currency(soup)
        return v

    def _extract_rating(self, soup: BeautifulSoup) -> float | None:
        for sel in ["span.a-icon-alt", "i.a-icon-star span"]:
            el = soup.select_one(sel)
            if el and "out of" in el.get_text().lower():
                v = self._to_float(el.get_text())
                if v is not None and 0 <= v <= 5:
                    return v
        return None

    def _extract_review_count(self, soup: BeautifulSoup) -> int | None:
        el = soup.select_one("#acrCustomerReviewText")
        if el:
            v = self._to_float(el.get_text())
            return int(v) if v is not None else None
        return None

    def _extract_bsr(self, soup: BeautifulSoup) -> tuple[int | None, str]:
        text = soup.get_text(" ", strip=True)
        m = re.search(r"#([\d,]+)\s+in\s+([A-Za-z &,'-]+)", text)
        if m:
            try:
                rank = int(m.group(1).replace(",", ""))
                return rank, m.group(2).strip()
            except ValueError:
                return None, ""
        return None, ""

    def _extract_brand(self, soup: BeautifulSoup) -> str:
        el = soup.select_one("#bylineInfo")
        if el:
            txt = el.get_text(strip=True)
            txt = re.sub(r"^(Visit the |Brand: )", "", txt, flags=re.I)
            txt = re.sub(r"\s*Store$", "", txt, flags=re.I)
            return txt
        return ""

    def _extract_prime(self, soup: BeautifulSoup) -> bool:
        return bool(soup.select_one("i.a-icon-prime, span.a-icon-prime"))

    def _extract_image(self, soup: BeautifulSoup) -> str:
        el = soup.select_one("#landingImage, #imgBlkFront, img#main-image")
        if not el:
            return ""
        return (el.get("data-old-hires") or el.get("src") or "").strip()

    def _extract_availability(self, soup: BeautifulSoup) -> str:
        el = soup.select_one("#availability span")
        return el.get_text(strip=True) if el else ""


# ============================================================
# ANALYZERS (profit, sales-from-bsr)
# ============================================================
def estimate_sales_from_bsr(bsr: int | None, category: str = "other") -> int:
    """Heuristic: monthly units sold from BSR. Real numbers vary widely by category."""
    if not bsr or bsr <= 0:
        return 0
    # Logarithmic decay; multiplier roughly tuned per category
    cat_multipliers = {"tech": 1.0, "home": 1.1, "beauty": 1.2, "pet": 1.0, "other": 1.0}
    mult = cat_multipliers.get(category, 1.0)
    if bsr <= 100:
        base = 5000
    elif bsr <= 500:
        base = 2500
    elif bsr <= 1_000:
        base = 1500
    elif bsr <= 5_000:
        base = 500
    elif bsr <= 10_000:
        base = 200
    elif bsr <= 50_000:
        base = 60
    elif bsr <= 100_000:
        base = 20
    else:
        base = 5
    return int(base * mult)


def calculate_profit(detail: AmazonDetail | None, category: str) -> ProfitEstimate | None:
    if not detail or detail.price is None:
        return None
    rate = COMMISSION_RATES.get(category, COMMISSION_RATES["other"])
    sales = estimate_sales_from_bsr(detail.bsr, category)
    commission_per_sale = round(detail.price * rate, 2)
    monthly = round(commission_per_sale * sales, 2)
    if detail.bsr and detail.bsr <= 5_000:
        confidence = "medium"
    elif detail.bsr and detail.bsr <= 50_000:
        confidence = "low"
    else:
        confidence = "low"
    return ProfitEstimate(
        price=detail.price,
        estimated_monthly_sales=sales,
        commission_rate=rate,
        commission_per_sale=commission_per_sale,
        estimated_monthly_commission=monthly,
        confidence=confidence,
    )


# ============================================================
# MULTI-FACTOR SCORING
# ============================================================
def score_opportunity(opp: Opportunity) -> tuple[int, dict[str, int]]:
    """Weighted 0-100 score with breakdown."""
    breakdown: dict[str, int] = {}

    # Traffic (15)
    t = opp.traffic
    if t >= 100_000:
        breakdown["traffic"] = 15
    elif t >= 60_000:
        breakdown["traffic"] = 12
    elif t >= 30_000:
        breakdown["traffic"] = 9
    elif t >= 10_000:
        breakdown["traffic"] = 6
    else:
        breakdown["traffic"] = 3

    # Source quality (10)
    src = opp.source
    breakdown["source"] = {
        "TikTok": 10,
        "Pinterest": 9,
        "Amazon Movers": 9,
        "Google Trends": 8,
        "Google Trends Related": 8,
    }.get(src, 5)

    # Trend direction (20) — defensive: rebuild if cached as a dict
    if isinstance(opp.trend, dict):
        try:
            opp.trend = TrendInfo(**opp.trend)
        except Exception:
            opp.trend = TrendInfo()
    direction = opp.trend.direction if opp.trend else "unknown"
    change = abs(opp.trend.change_pct) if opp.trend else 0
    if direction == "rising":
        breakdown["trend"] = 16 + min(4, int(change / 25))
    elif direction == "stable":
        breakdown["trend"] = 12
    elif direction == "falling":
        breakdown["trend"] = max(2, 8 - int(change / 25))
    else:
        # Default boost for sources whose `type` is rising/viral when no real trend data
        if opp.type in ("rising", "viral"):
            breakdown["trend"] = 14
        else:
            breakdown["trend"] = 10

    # Competition (20) — defensive: rebuild if cached as a dict
    if isinstance(opp.competition, dict):
        try:
            opp.competition = CompetitionInfo(**opp.competition)
        except Exception:
            opp.competition = None
    if opp.competition and opp.competition.tier != "unknown":
        breakdown["competition"] = {
            "low": 20, "medium": 16, "high": 10, "saturated": 4,
        }.get(opp.competition.tier, 10)
    else:
        breakdown["competition"] = 10

    # Profit potential (25) — defensive: rebuild if cached as a dict
    if isinstance(opp.profit, dict):
        try:
            opp.profit = ProfitEstimate(**opp.profit)
        except Exception:
            opp.profit = None
    if opp.profit and opp.profit.estimated_monthly_commission:
        m = opp.profit.estimated_monthly_commission
        if m >= 5000:
            breakdown["profit"] = 25
        elif m >= 2000:
            breakdown["profit"] = 22
        elif m >= 500:
            breakdown["profit"] = 18
        elif m >= 100:
            breakdown["profit"] = 12
        elif m > 0:
            breakdown["profit"] = 6
        else:
            breakdown["profit"] = 2
    else:
        breakdown["profit"] = 8  # neutral when unknown

    # Recency / engagement (10)
    breakdown["recency"] = 10

    total = min(100, sum(breakdown.values()))
    return total, breakdown


# ============================================================
# ORCHESTRATOR
# ============================================================
class MarketIntelligence:
    def __init__(
        self,
        use_selenium: bool = True,
        headless: bool = True,
        deep: bool = True,
        max_workers: int = 6,
        marketplace: str = "us",
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.deep = deep
        self.max_workers = max_workers
        self.marketplace = marketplace if marketplace in MARKETPLACES else "us"
        self.log_callback = log_callback or (lambda m: log.info(m))
        self.amazon = AmazonAnalyzer(
            use_selenium=self.use_selenium,
            headless=headless,
            marketplace=self.marketplace,
        )
        geo = MARKETPLACES[self.marketplace]["geo"]
        self.gtrends = GoogleTrendsSource(geo=geo)

    def _log(self, msg: str) -> None:
        try:
            self.log_callback(msg)
        except Exception:
            pass

    def gather(self, sources: Iterable[str]) -> list[Opportunity]:
        sources = set(sources)
        all_opps: list[Opportunity] = []
        # Per-source counters so we can show a clear summary at the end.
        counts: dict[str, int] = {
            "Pinterest": 0, "TikTok": 0, "Google": 0, "Amazon": 0,
        }

        if "pinterest" in sources:
            self._log("📌 [بدء] Pinterest...")
            items = get_pinterest_trends()
            all_opps.extend(items)
            counts["Pinterest"] = len(items)
            self._log(f"  ✓ Pinterest: {len(items)} ترند")
        if "tiktok" in sources:
            self._log("🎵 [بدء] TikTok...")
            items = get_tiktok_trends()
            all_opps.extend(items)
            counts["TikTok"] = len(items)
            self._log(f"  ✓ TikTok: {len(items)} ترند")

        if "google" in sources:
            self._log("🔎 [بدء] Google Trends (pytrends)...")
            trending = self.gtrends.trending_searches()
            counts["Google"] += len(trending)
            all_opps.extend(trending)
            # related-rising expansion for top 3
            related_total = 0
            for seed_opp in trending[:3]:
                rel = self.gtrends.related_rising(seed_opp.keyword, limit=3)
                if rel:
                    related_total += len(rel)
                    all_opps.extend(rel)
            counts["Google"] += related_total
            if counts["Google"] > 0:
                self._log(
                    f"  ✓ Google: {len(trending)} ترند "
                    f"+ {related_total} كلمة صاعدة"
                )
            else:
                self._log(
                    "  ⚠ Google: لم يرجّع أي كلمات (rate-limit). "
                    "هنكمل من باقي المصادر."
                )

        if "amazon" in sources:
            mp_name = MARKETPLACES[self.marketplace]["name"]
            self._log(f"📦 [بدء] {mp_name} - الأكثر صعوداً...")
            amazon_total = 0
            for cat, path in AMAZON_MOVERS_PATHS.items():
                items = self.amazon.movers(cat, path)
                cat_name = CATEGORY_THEMES.get(
                    cat, CATEGORY_THEMES["other"]
                )["name"]
                self._log(f"    • {len(items)} منتج من {cat_name}")
                all_opps.extend(items)
                amazon_total += len(items)
            counts["Amazon"] = amazon_total
            self._log(f"  ✓ Amazon: {amazon_total} منتج (مجموع كل الأقسام)")

        # categorize
        for o in all_opps:
            if o.category == "other":
                o.category = categorize(o.keyword, o.title)

        # Source summary — clear & visual
        total = sum(counts.values())
        self._log("\n📊 ملخص جلب البيانات من المصادر:")
        for src in ("Pinterest", "TikTok", "Google", "Amazon"):
            if src in [s.title() for s in sources] or src.lower() in sources:
                n = counts[src]
                icon = "✅" if n > 0 else "❌"
                self._log(f"   {icon} {src}: {n} فرصة")
        self._log("   ─────────────")
        self._log(f"   📦 الإجمالي: {total} فرصة\n")
        return all_opps

    def enrich(self, opps: list[Opportunity]) -> list[Opportunity]:
        """Attach trend, competition, deep amazon, profit. Concurrent."""
        if not opps:
            return opps
        self._log(f"🧠 جاري تحليل {len(opps)} فرصة (بالتوازي)...")

        def enrich_one(o: Opportunity) -> Opportunity:
            try:
                # Trend direction (only for keyword-based, not pure ASIN cards)
                if o.keyword and PYTRENDS_AVAILABLE:
                    o.trend = self.gtrends.keyword_trend(o.keyword)
                # Fallback: if Google didn't give us a direction, infer one
                # from the source. Amazon Movers / TikTok / Pinterest trends
                # are all rising by definition.
                if (
                    (not o.trend or not o.trend.direction)
                    and o.type in ("rising", "viral", "visual_trend")
                ):
                    o.trend = TrendInfo(
                        direction="rising",
                        change_pct=0.0,
                        sparkline=sparkline_for(15.0),
                    )
                if self.deep:
                    if o.keyword:
                        o.competition = self.amazon.competition(o.keyword)
                    if o.asin:
                        o.amazon = self.amazon.product_detail(o.asin)
                        if o.amazon and o.amazon.title and not o.title:
                            o.title = o.amazon.title
                        o.profit = calculate_profit(o.amazon, o.category)
            except Exception as exc:
                log.warning("enrich failed for %s: %s", o.label(), exc)
            return o

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {ex.submit(enrich_one, o): o for o in opps}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:
                    log.warning("worker failed: %s", exc)

        # final scoring
        for o in opps:
            o.score, o.score_breakdown = score_opportunity(o)
        opps.sort(key=lambda x: x.score, reverse=True)
        return opps

    def lookup_asins(self, opps: list[Opportunity], top_n: int = 30) -> None:
        """For top-scored keyword opportunities without an ASIN, look up the top
        Amazon search result and deep-analyze it. This converts keyword-only
        opportunities (Google/Pinterest/TikTok) into linkable affiliate products.
        """
        if not self.deep or not opps:
            return
        # pick top-scored keyword opps without ASIN
        candidates = [
            o for o in sorted(opps, key=lambda x: x.score, reverse=True)
            if o.keyword and not o.asin
        ][:top_n]
        if not candidates:
            return
        self._log(f"🔗 جاري البحث عن ASIN لأفضل {len(candidates)} فرصة (تحويل الكلمات لمنتجات)...")

        def lookup_one(o: Opportunity) -> None:
            try:
                asin = self.amazon.find_top_asin(o.keyword)
                if not asin:
                    return
                o.asin = asin
                if not o.url:
                    o.url = f"https://www.{self.amazon.domain}/dp/{asin}"
                detail = self.amazon.product_detail(asin)
                if detail:
                    o.amazon = detail
                    if detail.title and not o.title:
                        o.title = detail.title
                    o.profit = calculate_profit(detail, o.category)
            except Exception as exc:
                log.warning("asin lookup failed for %s: %s", o.keyword, exc)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, 4)) as ex:
            list(ex.map(lookup_one, candidates))

        # re-score after enrichment
        for o in opps:
            o.score, o.score_breakdown = score_opportunity(o)
        opps.sort(key=lambda x: x.score, reverse=True)

    def run(self, sources: Iterable[str]) -> list[Opportunity]:
        try:
            opps = self.gather(sources)
            opps = self.enrich(opps)
            self.lookup_asins(opps, top_n=30)
            return opps
        finally:
            self.amazon.close_driver()
            # Flush any suppressed Google Trends warnings at the end of the run
            cls = GoogleTrendsSource
            if cls._suppressed_failures > 0:
                log.warning(
                    "Google Trends: %d additional rate-limit failures "
                    "during this run (suppressed to reduce log spam).",
                    cls._suppressed_failures,
                )
                cls._suppressed_failures = 0


# ============================================================
# TOP PICKS — balanced curation across categories
# ============================================================
def top_picks(
    opps: list[Opportunity],
    n_per_cat: int = 5,
    total: int = 20,
    categories: list[str] | None = None,
) -> list[Opportunity]:
    """Return a curated, balanced selection of the best opportunities.

    Strategy:
      1. Group by category.
      2. Take top `n_per_cat` from each preferred category.
      3. If we have fewer than `total`, fill remaining slots with the next
         best opportunities from any category.
    """
    cats = categories or list(CATEGORIES)
    grouped: dict[str, list[Opportunity]] = {c: [] for c in cats}
    for o in sorted(opps, key=lambda x: x.score, reverse=True):
        if o.category in grouped:
            grouped[o.category].append(o)

    picks: list[Opportunity] = []
    for cat in cats:
        picks.extend(grouped[cat][:n_per_cat])

    # Fill remaining slots with next best across all categories
    if len(picks) < total:
        already = {id(o) for o in picks}
        remaining = sorted(
            (o for o in opps if id(o) not in already),
            key=lambda x: x.score,
            reverse=True,
        )
        picks.extend(remaining[: total - len(picks)])

    return picks[:total]


def picks_grouped_by_category(
    picks: list[Opportunity],
    categories: list[str] | None = None,
) -> dict[str, list[Opportunity]]:
    """Group top picks into ordered dict by category for display."""
    cats = categories or list(CATEGORIES)
    out: dict[str, list[Opportunity]] = {c: [] for c in cats}
    extras: list[Opportunity] = []
    for o in picks:
        if o.category in out:
            out[o.category].append(o)
        else:
            extras.append(o)
    if extras:
        out["other"] = extras
    return out


# ============================================================
# EXPORT
# ============================================================
def export_json(
    opps: list[Opportunity],
    path: Path,
    marketplace: str = "us",
    tag: str = "",
) -> None:
    data = [asdict(o) for o in opps]
    # also inject affiliate URL alongside raw asdict
    for raw, opp in zip(data, opps):
        raw["affiliate_url"] = affiliate_url(opp.asin, opp.keyword, marketplace, tag)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def export_csv(
    opps: list[Opportunity],
    path: Path,
    marketplace: str = "us",
    tag: str = "",
) -> None:
    if not PANDAS_AVAILABLE:
        log.warning("pandas not installed; falling back to json")
        export_json(opps, path.with_suffix(".json"), marketplace, tag)
        return
    df = pd.DataFrame([o.to_flat_dict(marketplace, tag) for o in opps])
    df.to_csv(path, index=False, encoding="utf-8")


def export_excel(
    opps: list[Opportunity],
    path: Path,
    marketplace: str = "us",
    tag: str = "",
) -> None:
    if not PANDAS_AVAILABLE:
        log.warning("pandas not installed; falling back to json")
        export_json(opps, path.with_suffix(".json"), marketplace, tag)
        return
    df = pd.DataFrame([o.to_flat_dict(marketplace, tag) for o in opps])
    df.to_excel(path, index=False, engine="openpyxl")


def export(
    opps: list[Opportunity],
    path: str | Path,
    marketplace: str = "us",
    tag: str = "",
) -> Path:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        export_csv(opps, p, marketplace, tag)
    elif suffix in (".xlsx", ".xls"):
        export_excel(opps, p, marketplace, tag)
    else:
        if suffix != ".json":
            p = p.with_suffix(".json")
        export_json(opps, p, marketplace, tag)
    log.info("exported %d opportunities to %s", len(opps), p)
    return p


# ============================================================
# WEBSITE INTEGRATION — products.js read/write
# ============================================================
# The site's products.js is a JS file that exports a const array. We parse it
# tolerantly (strip the `const products = ` prefix and trailing `;`), so we can
# read the existing array, add new entries, dedupe, and write it back.

PRODUCTS_JS_HEADER = "const products = "
PRODUCTS_JS_FOOTER = ";\n"


def load_products_js(path: str | Path) -> list[dict[str, Any]]:
    """Read the local products.js and return its array (or [] if missing)."""
    p = Path(path)
    if not p.exists():
        return []
    raw = p.read_text(encoding="utf-8")
    # Strip a leading `const products = ` (or `let`/`var products = `)
    text = raw.strip()
    for prefix in (
        "const products =",
        "let products =",
        "var products =",
        "export const products =",
        "export default",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    if text.endswith(";"):
        text = text[:-1].rstrip()
    try:
        data = json.loads(text)
    except Exception as exc:
        log.warning("products.js parse failed: %s", exc)
        return []
    return data if isinstance(data, list) else []


def save_products_js(path: str | Path, products: list[dict[str, Any]]) -> Path:
    """Write the array back as `const products = [...];`."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(products, indent=2, ensure_ascii=False)
    p.write_text(PRODUCTS_JS_HEADER + body + PRODUCTS_JS_FOOTER, encoding="utf-8")
    return p


def _format_price_for_site(price: float | None, currency: str = "USD") -> str:
    """products.js stores price as a string like "$15.88" or "EGP1,873.01"."""
    if price is None:
        return ""
    symbol_map = {
        "USD": "$", "GBP": "£", "EUR": "€",
        "JPY": "¥", "INR": "₹", "TRY": "₺",
        "ILS": "₪", "BRL": "R$",
    }
    if currency in symbol_map:
        sym = symbol_map[currency]
    else:
        # 3-letter codes (EGP, SAR, AED, …) — render as prefix + space
        sym = f"{currency}"
    if price == int(price):
        body = f"{int(price)}"
    else:
        body = f"{price:,.2f}" if price >= 1000 else f"{price:.2f}"
    return f"{sym}{body}"


def opportunity_to_product(
    o: Opportunity,
    marketplace: str = "us",
    tag: str = "",
) -> dict[str, Any]:
    """Convert an Opportunity into a products.js entry (matches website schema)."""
    # affiliate URL (deep-link if ASIN, else search)
    link = affiliate_url(o.asin, o.keyword, marketplace, tag)

    title = (o.title or (o.amazon.title if o.amazon else "")
             or o.keyword or o.asin or "Product")
    image = o.amazon.image_url if o.amazon else ""
    description = (o.amazon.title if o.amazon else "") or title

    rating = ""
    review_count = ""
    price = ""
    list_price = ""
    discount = ""
    if o.amazon:
        if o.amazon.rating:
            rating = f"{o.amazon.rating}"
        if o.amazon.review_count:
            review_count = f"{o.amazon.review_count:,}"
        currency = o.amazon.currency or MARKETPLACES.get(
            marketplace, MARKETPLACES["us"]
        )["currency"]
        price = _format_price_for_site(o.amazon.price, currency)
        if o.amazon.list_price and o.amazon.price:
            list_price = _format_price_for_site(o.amazon.list_price, currency)
            try:
                pct = (
                    (o.amazon.list_price - o.amazon.price)
                    / o.amazon.list_price * 100
                )
                if pct >= 1:
                    discount = f"{int(round(pct))}%"
            except Exception:
                pass

    social_proof = ""
    if o.profit and o.profit.estimated_monthly_sales:
        s = o.profit.estimated_monthly_sales
        if s >= 1000:
            social_proof = f"{s // 1000}K+ bought in past month"
        else:
            social_proof = f"{s}+ bought in past month"

    badge = ""
    if o.trend and o.trend.direction == "rising":
        badge = "🔥 Trending"

    item: dict[str, Any] = {
        "title": title,
        "image": image,
        "description": description[:240],
        "link": link,
        "category": o.category if o.category in CATEGORY_THEMES else "other",
        "rating": rating,
        "reviewCount": review_count,
        "socialProof": social_proof,
        "price": price,
        "badge": badge,
    }
    if list_price:
        item["listPrice"] = list_price
    if discount:
        item["discount"] = discount
    return item


def _product_dedupe_key(p: dict[str, Any]) -> str:
    """Best-effort identifier: ASIN from link if possible, else link."""
    link = (p.get("link") or "").strip()
    # try to extract /dp/ASIN
    import re
    m = re.search(r"/dp/([A-Z0-9]{10})", link)
    if m:
        return f"asin:{m.group(1)}"
    return f"link:{link}"


def merge_products_into_site(
    existing: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Append new_items into existing, deduplicating by ASIN/link.

    Returns: (merged_list, num_added, num_updated)
    """
    by_key: dict[str, dict[str, Any]] = {}
    for p in existing:
        by_key[_product_dedupe_key(p)] = p

    added = 0
    updated = 0
    for n in new_items:
        k = _product_dedupe_key(n)
        if k in by_key:
            # update existing entry with new (refreshed) data
            by_key[k].update(n)
            updated += 1
        else:
            by_key[k] = n
            added += 1

    return list(by_key.values()), added, updated


# ============================================================
# GUI (enhanced tkinter)
# ============================================================
# Per-category visual identity for the TOP PICKS panel
# Internal codes (tech/home/beauty/pet) stay English to match products.js schema.
# Display names are Arabic.
CATEGORY_THEMES: dict[str, dict[str, str]] = {
    "tech":   {"emoji": "📱", "color": "#2196F3", "name": "إلكترونيات",      "name_en": "TECH"},
    "home":   {"emoji": "🏠", "color": "#4CAF50", "name": "المنزل والمطبخ",  "name_en": "HOME"},
    "beauty": {"emoji": "💄", "color": "#E91E63", "name": "الجمال",          "name_en": "BEAUTY"},
    "pet":    {"emoji": "🐾", "color": "#FF9800", "name": "الحيوانات الأليفة", "name_en": "PET"},
    "other":  {"emoji": "⚡", "color": "#9E9E9E", "name": "متنوعات",          "name_en": "OTHER"},
}

TREND_LABELS: dict[str, str] = {
    "rising":  "صاعد 🚀",
    "falling": "هابط 📉",
    "stable":  "ثابت ➡️",
    "unknown": "غير معروف",
}

COMPETITION_LABELS: dict[str, str] = {
    "low":       "منافسة قليلة",
    "medium":    "منافسة متوسطة",
    "high":      "منافسة عالية",
    "saturated": "السوق مشبع",
    "unknown":   "غير محدد",
}

CONFIDENCE_LABELS: dict[str, str] = {
    "high":   "عالية",
    "medium": "متوسطة",
    "low":    "منخفضة",
}


def run_gui(initial_sources: list[str] | None = None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk  # noqa: F401

    initial_sources = initial_sources or ["google", "pinterest", "tiktok", "amazon"]

    # Mapping of source codes to Arabic display names
    SOURCE_LABELS = {
        "google": "Google",
        "pinterest": "Pinterest",
        "tiktok": "TikTok",
        "amazon": "Amazon",
    }

    class App:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title("نكسورا — أداة استكشاف فرص أمازون v2.6")
            self.root.geometry("1500x950")
            self.root.configure(bg="#0d1b2a")
            self.opportunities: list[Opportunity] = []
            self.filtered: list[Opportunity] = []
            self.picks: list[Opportunity] = []
            self.config = load_config()
            self._build_ui()

        # ---------- UI ----------
        def _build_ui(self) -> None:
            # ===== HEADER =====
            hdr = tk.Frame(self.root, bg="#1a2e42", pady=14)
            hdr.pack(fill="x")
            tk.Label(hdr, text="🎯 نكسورا",
                     bg="#1a2e42", fg="#e8a020",
                     font=("Segoe UI", 22, "bold")).pack(side="left", padx=20)
            tk.Label(hdr, text="أداة استكشاف فرص أمازون  •  v2.6",
                     bg="#1a2e42", fg="#a0b4c8",
                     font=("Segoe UI", 10, "italic")).pack(side="left")

            # marketplace selector + settings on the right
            tk.Button(hdr, text="⚙ الإعدادات", bg="#3a4f66", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=self.open_settings).pack(side="right", padx=10, ipady=4, ipadx=10)

            tk.Label(hdr, text="السوق:", bg="#1a2e42", fg="#a0b4c8",
                     font=("Segoe UI", 9)).pack(side="right", padx=(8, 4))
            self.mp_var = tk.StringVar(value=self.config["marketplace"])
            mp_box = ttk.Combobox(hdr, textvariable=self.mp_var,
                                  values=list(MARKETPLACES.keys()),
                                  width=5, state="readonly")
            mp_box.pack(side="right", padx=4)
            mp_box.bind("<<ComboboxSelected>>", lambda *_: self._on_marketplace_change())

            # ===== CONTROLS =====
            ctrl = tk.Frame(self.root, bg="#0d2235", pady=12)
            ctrl.pack(fill="x", padx=20, pady=10)
            tk.Label(ctrl, text="📊 المصادر:", bg="#0d2235", fg="#e8a020",
                     font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)

            self.src = {
                "google": tk.BooleanVar(value="google" in initial_sources),
                "pinterest": tk.BooleanVar(value="pinterest" in initial_sources),
                "tiktok": tk.BooleanVar(value="tiktok" in initial_sources),
                "amazon": tk.BooleanVar(value="amazon" in initial_sources),
            }
            for name, var in self.src.items():
                tk.Checkbutton(ctrl, text=SOURCE_LABELS.get(name, name), variable=var,
                               bg="#0d2235", fg="#fff", selectcolor="#1a2e42",
                               font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)

            self.deep_var = tk.BooleanVar(value=True)
            tk.Checkbutton(ctrl, text="تحليل عميق", variable=self.deep_var,
                           bg="#0d2235", fg="#7ec8a0", selectcolor="#1a2e42",
                           font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)

            self.headless_var = tk.BooleanVar(value=True)
            tk.Checkbutton(ctrl, text="بدون متصفح ظاهر", variable=self.headless_var,
                           bg="#0d2235", fg="#7ec8a0", selectcolor="#1a2e42",
                           font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)

            tk.Button(ctrl, text="🚀 بدء التحليل", bg="#e8a020", fg="#000",
                      font=("Segoe UI", 12, "bold"), relief="flat", cursor="hand2",
                      command=self.start).pack(side="right", padx=8, ipady=8, ipadx=18)
            tk.Button(ctrl, text="💾 تصدير الكل", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=self.export_dialog).pack(side="right", padx=4, ipady=6, ipadx=10)
            tk.Button(ctrl, text="🧹 مسح الذاكرة", bg="#5a6c7d", fg="#fff",
                      font=("Segoe UI", 9), relief="flat", cursor="hand2",
                      command=self.clear_cache).pack(side="right", padx=4, ipady=6, ipadx=10)

            # ===== MAIN SPLIT =====
            main = tk.Frame(self.root, bg="#0d1b2a")
            main.pack(fill="both", expand=True, padx=20, pady=(0, 10))

            # Left = Live Log (narrower)
            left = tk.Frame(main, bg="#0d1b2a", width=380)
            left.pack(side="left", fill="both", padx=(0, 10))
            left.pack_propagate(False)
            tk.Label(left, text="📊 سجل التحليل المباشر", bg="#0d1b2a", fg="#e8a020",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
            self.log_box = scrolledtext.ScrolledText(
                left, bg="#0a1520", fg="#7ec8a0", font=("Consolas", 9), relief="flat"
            )
            self.log_box.pack(fill="both", expand=True)

            # Right = Notebook with Top Picks + All Opportunities tabs
            right = tk.Frame(main, bg="#0d1b2a")
            right.pack(side="left", fill="both", expand=True)

            style = ttk.Style()
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure("TNotebook", background="#0d1b2a", borderwidth=0)
            style.configure("TNotebook.Tab", background="#1a2e42", foreground="#a0b4c8",
                            padding=(20, 10), font=("Segoe UI", 10, "bold"))
            style.map("TNotebook.Tab",
                      background=[("selected", "#e8a020")],
                      foreground=[("selected", "#0d1b2a")])

            self.nb = ttk.Notebook(right)
            self.nb.pack(fill="both", expand=True)

            self.top_picks_tab = tk.Frame(self.nb, bg="#0d1b2a")
            self.all_opps_tab = tk.Frame(self.nb, bg="#0d1b2a")
            self.site_tab = tk.Frame(self.nb, bg="#0d1b2a")
            self.nb.add(self.top_picks_tab, text="🏆  أفضل ٢٠ منتج  ")
            self.nb.add(self.all_opps_tab, text="📋  كل الفرص  ")
            self.nb.add(self.site_tab, text="🌐  منتجات الموقع  ")

            self._build_top_picks_tab()
            self._build_all_opps_tab()
            self._build_site_tab()

            # ===== STATUS BAR =====
            self.status = tk.StringVar(value="جاهز • اضغط 'بدء التحليل' للبدء")
            tk.Label(self.root, textvariable=self.status, bg="#0a0a0a", fg="#888",
                     font=("Segoe UI", 9), anchor="w", pady=7
                     ).pack(fill="x", side="bottom", padx=14)

        def _build_top_picks_tab(self) -> None:
            """Build the gold-themed TOP 20 PICKS tab."""
            # Banner with marketplace + tag info + export button
            banner = tk.Frame(self.top_picks_tab, bg="#1a1208", pady=12)
            banner.pack(fill="x")

            tk.Label(banner, text="💎 أفضل ٢٠ منتج",
                     bg="#1a1208", fg="#ffd166",
                     font=("Segoe UI", 18, "bold")).pack(side="left", padx=16)
            tk.Label(banner, text="مختارة لتسويق العمولة على أمازون",
                     bg="#1a1208", fg="#a0b4c8",
                     font=("Segoe UI", 9, "italic")).pack(side="left", padx=4)

            tk.Button(banner, text="💾 تصدير الـ ٢٠ منتج", bg="#ffd166", fg="#1a1208",
                      font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                      command=self.export_top_picks).pack(side="right", padx=6, ipady=5, ipadx=12)
            tk.Button(banner, text="📤 إضافة كل الـ ٢٠ للموقع",
                      bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                      command=self.add_all_picks_to_site
                      ).pack(side="right", padx=6, ipady=5, ipadx=12)

            self.picks_status = tk.StringVar(value="ابدأ التحليل لظهور أفضل المنتجات.")
            tk.Label(banner, textvariable=self.picks_status,
                     bg="#1a1208", fg="#e8a020",
                     font=("Segoe UI", 9, "bold")).pack(side="right", padx=10)

            # Scrollable canvas for picks cards
            container = tk.Frame(self.top_picks_tab, bg="#0d1b2a")
            container.pack(fill="both", expand=True)
            self.picks_canvas = tk.Canvas(container, bg="#0d1b2a", highlightthickness=0)
            picks_scroll = tk.Scrollbar(container, orient="vertical",
                                        command=self.picks_canvas.yview)
            self.picks_inner = tk.Frame(self.picks_canvas, bg="#0d1b2a")
            self.picks_inner.bind(
                "<Configure>",
                lambda e: self.picks_canvas.configure(scrollregion=self.picks_canvas.bbox("all")),
            )
            self.picks_canvas.create_window((0, 0), window=self.picks_inner, anchor="nw")
            self.picks_canvas.configure(yscrollcommand=picks_scroll.set)
            self.picks_canvas.pack(side="left", fill="both", expand=True)
            picks_scroll.pack(side="right", fill="y")
            # mousewheel scrolling
            self.picks_canvas.bind_all(
                "<MouseWheel>",
                lambda e: self._on_mousewheel(e, self.picks_canvas),
            )

            # Empty placeholder
            tk.Label(self.picks_inner,
                     text="\n\n\n🎯  ابدأ تحليلاً لظهور أفضل ٢٠ منتج للتسويق هنا.\n\n"
                          "       ٥ منتجات من كل قسم — إلكترونيات، المنزل، الجمال، الحيوانات الأليفة — مع روابط أفلييت جاهزة.\n",
                     bg="#0d1b2a", fg="#5a7a9a",
                     font=("Segoe UI", 11)).pack(pady=40)

        def _build_all_opps_tab(self) -> None:
            """Build the 'All Opportunities' tab with filters."""
            # Filter bar
            flt = tk.Frame(self.all_opps_tab, bg="#0d2235", pady=8)
            flt.pack(fill="x")
            tk.Label(flt, text="🔎 بحث:", bg="#0d2235", fg="#e8a020",
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", lambda *_: self.apply_filter())
            tk.Entry(flt, textvariable=self.search_var, width=24,
                     bg="#1a2e42", fg="#fff", insertbackground="#fff",
                     relief="flat").pack(side="left", padx=4, ipady=4)

            tk.Label(flt, text="القسم:", bg="#0d2235", fg="#a0b4c8",
                     font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
            self.cat_var = tk.StringVar(value="all")
            cat_box = ttk.Combobox(flt, textvariable=self.cat_var,
                                   values=["all", *CATEGORIES, "other"],
                                   width=10, state="readonly")
            cat_box.pack(side="left", padx=4)
            cat_box.bind("<<ComboboxSelected>>", lambda *_: self.apply_filter())

            tk.Label(flt, text="الحد الأدنى للنقاط:", bg="#0d2235", fg="#a0b4c8",
                     font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
            self.min_score_var = tk.IntVar(value=0)
            tk.Scale(flt, from_=0, to=100, orient="horizontal",
                     variable=self.min_score_var, length=160,
                     bg="#0d2235", fg="#fff", troughcolor="#1a2e42",
                     highlightthickness=0,
                     command=lambda *_: self.apply_filter()).pack(side="left", padx=4)

            tk.Label(flt, text="ترتيب:", bg="#0d2235", fg="#a0b4c8",
                     font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
            self.sort_var = tk.StringVar(value="score")
            sort_box = ttk.Combobox(flt, textvariable=self.sort_var,
                                    values=["score", "profit", "competition", "trend"],
                                    width=12, state="readonly")
            sort_box.pack(side="left", padx=4)
            sort_box.bind("<<ComboboxSelected>>", lambda *_: self.apply_filter())

            # Cards canvas
            container = tk.Frame(self.all_opps_tab, bg="#0d1b2a")
            container.pack(fill="both", expand=True)
            canvas = tk.Canvas(container, bg="#0d1b2a", highlightthickness=0)
            scroll = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
            self.cards_frame = tk.Frame(canvas, bg="#0d1b2a")
            self.cards_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")

        def _on_mousewheel(self, event: Any, canvas: Any) -> None:
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        # ---------- Marketplace + Settings ----------
        def _on_marketplace_change(self) -> None:
            self.config["marketplace"] = self.mp_var.get()
            save_config(self.config)
            # Re-render top picks if we already have data (so affiliate URLs update)
            if self.opportunities:
                self._render_top_picks()

        def _current_tag(self) -> str:
            mp = self.mp_var.get()
            return self.config.get("affiliate_tags", {}).get(mp, "") or ""

        def open_settings(self) -> None:
            top = tk.Toplevel(self.root)
            top.title("⚙ الإعدادات")
            top.geometry("620x560")
            top.configure(bg="#0d1b2a")
            top.transient(self.root)

            tk.Label(top, text="⚙ إعدادات الأداة",
                     bg="#0d1b2a", fg="#e8a020",
                     font=("Segoe UI", 16, "bold")).pack(pady=(18, 4))

            grid = tk.Frame(top, bg="#0d1b2a")
            grid.pack(padx=24, pady=8, fill="x")

            # ----- Single tag input (applies to all markets) -----
            tk.Label(grid, text="🏷  Amazon Associate Tag:",
                     bg="#0d1b2a", fg="#7ec8a0",
                     font=("Segoe UI", 11, "bold"), anchor="w"
                     ).grid(row=0, column=0, sticky="w", pady=(0, 4))
            tk.Label(grid,
                     text="(نفس الـ tag يتطبق على كل الأسواق: US/UK/DE/FR/IT/ES)",
                     bg="#0d1b2a", fg="#a0b4c8",
                     font=("Segoe UI", 8), anchor="w"
                     ).grid(row=1, column=0, sticky="w", pady=(0, 4))
            current_tag = ""
            for v in self.config.get("affiliate_tags", {}).values():
                if v:
                    current_tag = v
                    break
            tag_entry = tk.Entry(grid, width=36, bg="#1a2e42", fg="#fff",
                                 insertbackground="#fff", relief="flat",
                                 font=("Segoe UI", 11))
            tag_entry.insert(0, current_tag)
            tag_entry.grid(row=2, column=0, sticky="we", ipady=6)
            tk.Label(grid, text="مثال: nexora-20",
                     bg="#0d1b2a", fg="#5a7a9a",
                     font=("Segoe UI", 8, "italic"), anchor="w"
                     ).grid(row=3, column=0, sticky="w", pady=(2, 14))

            # ----- products.js path -----
            tk.Label(grid, text="🌐  مسار ملف products.js (موقعك):",
                     bg="#0d1b2a", fg="#7ec8a0",
                     font=("Segoe UI", 11, "bold"), anchor="w"
                     ).grid(row=4, column=0, sticky="w", pady=(8, 4))
            tk.Label(grid,
                     text="لما تضغط 'إضافة للموقع' الأداة هتكتب على الملف ده مباشرة.",
                     bg="#0d1b2a", fg="#a0b4c8",
                     font=("Segoe UI", 8), anchor="w"
                     ).grid(row=5, column=0, sticky="w", pady=(0, 4))
            path_row = tk.Frame(grid, bg="#0d1b2a")
            path_row.grid(row=6, column=0, sticky="we")
            path_row.columnconfigure(0, weight=1)
            path_var = tk.StringVar(value=self.config.get("products_js_path", ""))
            path_entry = tk.Entry(path_row, textvariable=path_var,
                                  bg="#1a2e42", fg="#fff",
                                  insertbackground="#fff", relief="flat",
                                  font=("Segoe UI", 10))
            path_entry.grid(row=0, column=0, sticky="we", ipady=5)

            def browse_path() -> None:
                p = filedialog.askopenfilename(
                    title="اختار ملف products.js",
                    filetypes=[("JavaScript", "*.js"), ("الكل", "*.*")],
                )
                if p:
                    path_var.set(p)
            tk.Button(path_row, text="📂 اختار", bg="#3a4f66", fg="#fff",
                      font=("Segoe UI", 9), relief="flat", cursor="hand2",
                      command=browse_path
                      ).grid(row=0, column=1, padx=(6, 0), ipady=4, ipadx=10)
            tk.Label(grid,
                     text="مثال: D:\\Amazon affiliate\\website\\products.js",
                     bg="#0d1b2a", fg="#5a7a9a",
                     font=("Segoe UI", 8, "italic"), anchor="w"
                     ).grid(row=7, column=0, sticky="w", pady=(2, 14))

            # ----- picks per category -----
            tk.Label(grid, text="🏆  عدد المنتجات في كل قسم:",
                     bg="#0d1b2a", fg="#7ec8a0",
                     font=("Segoe UI", 10, "bold"), anchor="w"
                     ).grid(row=8, column=0, sticky="w", pady=(8, 4))
            n_var = tk.IntVar(value=int(self.config.get("top_per_category", 5)))
            tk.Spinbox(grid, from_=1, to=10, textvariable=n_var, width=5,
                       bg="#1a2e42", fg="#fff", relief="flat",
                       font=("Segoe UI", 11)).grid(row=9, column=0, sticky="w", pady=2)

            def save_and_close() -> None:
                # apply same tag to all markets
                tag = tag_entry.get().strip()
                self.config["affiliate_tags"] = {mp: tag for mp in MARKETPLACES}
                self.config["top_per_category"] = max(1, min(10, n_var.get()))
                self.config["products_js_path"] = path_var.get().strip()
                save_config(self.config)
                if self.opportunities:
                    self._render_top_picks()
                # refresh website tab if open
                self._refresh_site_products()
                top.destroy()
                messagebox.showinfo(
                    "تم الحفظ",
                    "تم حفظ الإعدادات بنجاح.\nالروابط اتحدثت.",
                )

            btns = tk.Frame(top, bg="#0d1b2a")
            btns.pack(pady=18)
            tk.Button(btns, text="💾 حفظ", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                      command=save_and_close).pack(side="left", padx=6, ipady=6, ipadx=20)
            tk.Button(btns, text="إلغاء", bg="#5a6c7d", fg="#fff",
                      font=("Segoe UI", 10), relief="flat", cursor="hand2",
                      command=top.destroy).pack(side="left", padx=6, ipady=6, ipadx=14)

        # ---------- helpers ----------
        def log(self, m: str) -> None:
            self.log_box.insert("end", m + "\n")
            self.log_box.see("end")
            self.root.update_idletasks()

        def set_status(self, m: str) -> None:
            self.status.set(m)
            self.root.update_idletasks()

        # ---------- actions ----------
        def start(self) -> None:
            self.log_box.delete("1.0", "end")
            for w in self.cards_frame.winfo_children():
                w.destroy()
            for w in self.picks_inner.winfo_children():
                w.destroy()
            self.opportunities = []
            self.filtered = []
            self.picks = []
            self.picks_status.set("جاري التحليل...")
            threading.Thread(target=self._run, daemon=True).start()

        def _run(self) -> None:
            sources = [s for s, v in self.src.items() if v.get()]
            self.log("=" * 60)
            self.log("🎯 نكسورا — أداة استكشاف فرص أمازون v2.6")
            src_names = ', '.join(SOURCE_LABELS.get(s, s) for s in sources)
            self.log(f"المصادر: {src_names}  •  تحليل عميق: {'نعم' if self.deep_var.get() else 'لا'}")
            self.log(f"السوق: {MARKETPLACES[self.mp_var.get()]['name']}")
            self.log("=" * 60)
            mi = MarketIntelligence(
                use_selenium=True,
                headless=self.headless_var.get(),
                deep=self.deep_var.get(),
                marketplace=self.mp_var.get(),
                log_callback=self.log,
            )
            opps = mi.run(sources)
            self.opportunities = opps
            self.log(f"\n✅ انتهى التحليل. تم اكتشاف {len(opps)} فرصة.")
            self.set_status(f"اكتمل التحليل  •  {len(opps)} فرصة")
            self.root.after(0, self._render_top_picks)
            self.root.after(0, self.apply_filter)

        def apply_filter(self) -> None:
            q = self.search_var.get().lower().strip()
            cat = self.cat_var.get()
            min_score = self.min_score_var.get()
            sort_key = self.sort_var.get()

            def match(o: Opportunity) -> bool:
                if q and q not in o.label().lower():
                    return False
                if cat != "all" and o.category != cat:
                    return False
                if o.score < min_score:
                    return False
                return True

            filtered = [o for o in self.opportunities if match(o)]

            def sort_fn(o: Opportunity) -> float:
                if sort_key == "profit":
                    return -(o.profit.estimated_monthly_commission if o.profit else 0)
                if sort_key == "competition":
                    return o.competition.results_count if o.competition else 1e9
                if sort_key == "trend":
                    return -(o.trend.change_pct if o.trend else 0)
                return -o.score

            filtered.sort(key=sort_fn)
            self.filtered = filtered

            for w in self.cards_frame.winfo_children():
                w.destroy()
            for i, o in enumerate(filtered[:50], 1):
                self._add_card(o, i)
            self.set_status(
                f"عرض {len(filtered)} من أصل {len(self.opportunities)} فرصة"
            )

        def _add_card(self, o: Opportunity, rank: int) -> None:
            card = tk.Frame(self.cards_frame, bg="#1a2e42", relief="solid", bd=1)
            card.pack(fill="x", padx=5, pady=4)

            label = o.label()
            tk.Label(card, text=f"#{rank}. {label[:60]}",
                     bg="#1a2e42", fg="#fff",
                     font=("Segoe UI", 10, "bold"), anchor="w"
                     ).pack(fill="x", padx=10, pady=(8, 2))

            cat_label = CATEGORY_THEMES.get(
                o.category, CATEGORY_THEMES["other"]
            )["name"]
            line2 = f"💯 {o.score}/100  •  📂 {cat_label}  •  📊 {SOURCE_LABELS.get(o.source, o.source)}"
            if o.trend.direction != "unknown":
                trend_ar = TREND_LABELS.get(o.trend.direction, o.trend.direction)
                line2 += f"  •  {o.trend.sparkline} {trend_ar} ({o.trend.change_pct:+.1f}%)"
            tk.Label(card, text=line2, bg="#1a2e42", fg="#a0b4c8",
                     font=("Segoe UI", 8), anchor="w"
                     ).pack(fill="x", padx=10, pady=1)

            extras: list[str] = []
            if o.amazon and o.amazon.price:
                extras.append(f"💵 ${o.amazon.price}")
            if o.amazon and o.amazon.rating:
                extras.append(f"⭐ {o.amazon.rating} ({o.amazon.review_count or '؟'})")
            if o.amazon and o.amazon.bsr:
                extras.append(f"📈 ترتيب #{o.amazon.bsr:,}")
            if o.competition and o.competition.tier != "unknown":
                comp_ar = COMPETITION_LABELS.get(
                    o.competition.tier, o.competition.tier
                )
                extras.append(f"🥊 {comp_ar} ({o.competition.results_count:,})")
            if o.profit and o.profit.estimated_monthly_commission:
                extras.append(f"💰 ~${o.profit.estimated_monthly_commission:,.0f}/شهر")
            if extras:
                tk.Label(card, text="  •  ".join(extras), bg="#1a2e42", fg="#7ec8a0",
                         font=("Segoe UI", 8), anchor="w"
                         ).pack(fill="x", padx=10, pady=1)

            bf = tk.Frame(card, bg="#1a2e42")
            bf.pack(fill="x", padx=10, pady=(4, 8))
            mp = self.mp_var.get()
            tag = self._current_tag()
            aff_link = affiliate_url(o.asin, o.keyword, mp, tag)
            tk.Button(bf, text="🛒 افتح برابط الأفلييت", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=aff_link: webbrowser.open(u) if u else None
                      ).pack(side="left", padx=(0, 6), ipady=3, ipadx=8)
            tk.Button(bf, text="📋 نسخ الرابط", bg="#e8a020", fg="#000",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=aff_link: self._copy(u)
                      ).pack(side="left", padx=(0, 6), ipady=3, ipadx=8)
            tk.Button(bf, text="📤 للموقع", bg="#2a7fbf", fg="#fff",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda opp=o: self.add_one_to_site(opp)
                      ).pack(side="left", padx=(0, 6), ipady=3, ipadx=8)
            tk.Button(bf, text="📊 التفاصيل", bg="#3a4f66", fg="#fff",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda opp=o: self._show_detail(opp)
                      ).pack(side="left", ipady=3, ipadx=8)

        # ---------- TOP PICKS rendering ----------
        def _render_top_picks(self) -> None:
            """Render the curated TOP 20 picks panel grouped by category."""
            for w in self.picks_inner.winfo_children():
                w.destroy()

            n_per = int(self.config.get("top_per_category", 5))
            self.picks = top_picks(self.opportunities, n_per_cat=n_per, total=20)
            grouped = picks_grouped_by_category(self.picks)

            mp = self.mp_var.get()
            tag = self._current_tag()
            mp_name = MARKETPLACES[mp]["name"]
            tag_display = tag or "⚠ مفيش tag — افتح الإعدادات"
            self.picks_status.set(
                f"{len(self.picks)} منتج  •  {mp_name}  •  Tag: {tag_display}"
            )

            if not self.picks:
                tk.Label(self.picks_inner,
                         text="\n\nمفيش فرص متاحة لسه. اضغط 'بدء التحليل'.\n",
                         bg="#0d1b2a", fg="#5a7a9a",
                         font=("Segoe UI", 11)).pack(pady=40)
                return

            global_rank = 0
            for cat, items in grouped.items():
                if not items:
                    continue
                theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["other"])

                # Category section header
                hdr = tk.Frame(self.picks_inner, bg=theme["color"], pady=8)
                hdr.pack(fill="x", pady=(14, 0), padx=8)
                tk.Label(hdr,
                         text=f"  {theme['emoji']}  {theme['name']}  ({len(items)} منتج)",
                         bg=theme["color"], fg="#0d1b2a",
                         font=("Segoe UI", 13, "bold"), anchor="w"
                         ).pack(side="left", padx=10)

                # cards
                for o in items:
                    global_rank += 1
                    self._add_top_pick_card(o, global_rank, theme)

        def _add_top_pick_card(
            self,
            o: Opportunity,
            global_rank: int,
            theme: dict[str, str],
        ) -> None:
            """Render one TOP PICK card with gold accent and affiliate buttons."""
            outer = tk.Frame(self.picks_inner, bg=theme["color"])
            outer.pack(fill="x", padx=8, pady=(0, 4))

            card = tk.Frame(outer, bg="#1a2e42")
            card.pack(fill="x", padx=2, pady=(0, 2))  # leaves a thin colored border

            # Rank + Title row
            top_row = tk.Frame(card, bg="#1a2e42")
            top_row.pack(fill="x", padx=12, pady=(10, 2))

            tk.Label(top_row, text=f"#{global_rank}",
                     bg="#1a2e42", fg="#ffd166",
                     font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 10))

            title = (o.title or o.keyword or o.asin or "").strip()
            tk.Label(top_row, text=title[:75],
                     bg="#1a2e42", fg="#ffffff",
                     font=("Segoe UI", 11, "bold"), anchor="w", justify="left",
                     wraplength=900
                     ).pack(side="left", fill="x", expand=True)

            # Score badge
            tk.Label(top_row, text=f" {o.score}/100 ",
                     bg="#ffd166", fg="#1a1208",
                     font=("Segoe UI", 10, "bold")).pack(side="right", padx=4)

            # Stats row
            stats: list[str] = []
            if o.amazon and o.amazon.price:
                cur = MARKETPLACES.get(self.mp_var.get(), MARKETPLACES["us"])["currency"]
                cur_sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(cur, "")
                stats.append(f"{cur_sym}{o.amazon.price}")
            if o.amazon and o.amazon.rating:
                stats.append(f"⭐ {o.amazon.rating} ({o.amazon.review_count or '؟'})")
            if o.amazon and o.amazon.bsr:
                stats.append(f"📈 ترتيب #{o.amazon.bsr:,}")
            if o.trend.direction != "unknown":
                trend_ar = TREND_LABELS.get(o.trend.direction, o.trend.direction)
                stats.append(f"{o.trend.sparkline} {trend_ar} ({o.trend.change_pct:+.0f}%)")
            if o.competition and o.competition.tier != "unknown":
                comp_ar = COMPETITION_LABELS.get(
                    o.competition.tier, o.competition.tier
                )
                stats.append(f"🥊 {comp_ar}")
            if stats:
                tk.Label(card, text="  •  ".join(stats),
                         bg="#1a2e42", fg="#a0b4c8",
                         font=("Segoe UI", 9), anchor="w"
                         ).pack(fill="x", padx=12, pady=2)

            # Highlighted profit row
            if o.profit and o.profit.estimated_monthly_commission:
                profit_frame = tk.Frame(card, bg="#1a1208")
                profit_frame.pack(fill="x", padx=12, pady=4)
                tk.Label(profit_frame,
                         text=f"  💰  عمولة شهرية تقديرية ~${o.profit.estimated_monthly_commission:,.0f}  ",
                         bg="#1a1208", fg="#ffd166",
                         font=("Segoe UI", 11, "bold")).pack(side="left", pady=4)
                tk.Label(profit_frame,
                         text=f"({o.profit.estimated_monthly_sales:,} مبيعة × "
                              f"عمولة {o.profit.commission_rate*100:.1f}%)",
                         bg="#1a1208", fg="#a0b4c8",
                         font=("Segoe UI", 8, "italic")).pack(side="left", padx=8)

            # Action buttons
            mp = self.mp_var.get()
            tag = self._current_tag()
            aff_link = affiliate_url(o.asin, o.keyword, mp, tag)

            bf = tk.Frame(card, bg="#1a2e42")
            bf.pack(fill="x", padx=12, pady=(4, 12))
            tk.Button(bf, text="🛒 افتح برابط الأفلييت", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=aff_link: webbrowser.open(u) if u else None
                      ).pack(side="left", padx=(0, 6), ipady=4, ipadx=12)
            tk.Button(bf, text="📋 نسخ الرابط", bg="#ffd166", fg="#1a1208",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=aff_link: self._copy(u)
                      ).pack(side="left", padx=(0, 6), ipady=4, ipadx=12)
            tk.Button(bf, text="📤 إضافة للموقع", bg="#2a7fbf", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=lambda opp=o: self.add_one_to_site(opp)
                      ).pack(side="left", padx=(0, 6), ipady=4, ipadx=12)
            tk.Button(bf, text="📊 التفاصيل", bg="#3a4f66", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=lambda opp=o: self._show_detail(opp)
                      ).pack(side="left", ipady=4, ipadx=10)

            # Show URL inline (small)
            if aff_link:
                tk.Label(card, text=aff_link, bg="#1a2e42", fg="#5a7a9a",
                         font=("Consolas", 7), anchor="w"
                         ).pack(fill="x", padx=12, pady=(0, 6))

        def _copy(self, text: str) -> None:
            if not text:
                return
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.set_status(f"📋 تم النسخ: {text[:80]}")
            except Exception as exc:
                log.warning("clipboard copy failed: %s", exc)

        def _show_detail(self, o: Opportunity) -> None:
            top = tk.Toplevel(self.root)
            top.title(f"تفاصيل: {o.label()[:60]}")
            top.geometry("700x600")
            top.configure(bg="#0d1b2a")

            txt = scrolledtext.ScrolledText(top, bg="#0a1520", fg="#cfe8d4",
                                            font=("Consolas", 10), relief="flat")
            txt.pack(fill="both", expand=True, padx=10, pady=10)

            cat_label = CATEGORY_THEMES.get(
                o.category, CATEGORY_THEMES["other"]
            )["name"]
            src_label = SOURCE_LABELS.get(o.source, o.source)

            lines: list[str] = []
            lines.append(f"🎯 {o.label()}")
            lines.append("=" * 60)
            lines.append(f"النقاط: {o.score}/100")
            if o.score_breakdown:
                lines.append("تفاصيل النقاط: " + "  •  ".join(
                    f"{k}={v}" for k, v in o.score_breakdown.items()
                ))
            lines.append(f"المصدر: {src_label}  •  القسم: {cat_label}  •  النوع: {o.type}")
            lines.append(f"حجم الترافيك التقديري: {o.traffic:,}")
            lines.append("")
            lines.append("📈 الترند")
            trend_ar = TREND_LABELS.get(o.trend.direction, o.trend.direction)
            lines.append(f"  الاتجاه: {trend_ar}  {o.trend.sparkline}")
            lines.append(f"  نسبة التغير: {o.trend.change_pct:+.1f}%  "
                         f"(آخر فترة {o.trend.avg_recent} مقابل سابق {o.trend.avg_previous})")
            lines.append("")
            if o.competition:
                comp_ar = COMPETITION_LABELS.get(
                    o.competition.tier, o.competition.tier
                )
                lines.append("🥊 المنافسة")
                lines.append(f"  المستوى: {comp_ar}")
                lines.append(f"  عدد نتائج أمازون: {o.competition.results_count:,}")
                lines.append(f"  عدد المعلَن في الصفحة: {o.competition.sponsored_count}")
                lines.append("")
            if o.amazon:
                a = o.amazon
                lines.append("📦 تفاصيل المنتج على أمازون")
                lines.append(f"  ASIN: {a.asin}")
                lines.append(f"  العنوان: {a.title[:80]}")
                lines.append(f"  العلامة التجارية: {a.brand}")
                lines.append(f"  السعر: ${a.price if a.price else '؟'} {a.currency}")
                lines.append(f"  التقييم: {a.rating} • عدد التقييمات: {a.review_count}")
                lines.append(
                    f"  الترتيب في القسم (BSR): #{a.bsr:,} في {a.bsr_category}"
                    if a.bsr else "  الترتيب في القسم: غير معروف"
                )
                lines.append(f"  Prime: {'نعم' if a.prime else 'لا'}")
                lines.append(f"  التوفر: {a.availability}")
                lines.append(f"  عدد الاختيارات (variations): {a.variations_count}")
                if a.image_url:
                    lines.append(f"  الصورة: {a.image_url}")
                lines.append("")
            if o.profit:
                p = o.profit
                conf_ar = CONFIDENCE_LABELS.get(p.confidence, p.confidence)
                lines.append("💰 تقدير الأرباح")
                lines.append(f"  السعر: ${p.price}")
                lines.append(f"  المبيعات الشهرية المتوقعة: {p.estimated_monthly_sales:,} وحدة")
                lines.append(f"  نسبة العمولة لقسم ({cat_label}): {p.commission_rate*100:.1f}%")
                lines.append(f"  العمولة لكل مبيعة: ${p.commission_per_sale}")
                lines.append(f"  العمولة الشهرية التقديرية: ${p.estimated_monthly_commission:,.2f}")
                lines.append(f"  درجة الثقة في التقدير: {conf_ar}")
                lines.append("")
            if o.url:
                lines.append(f"🔗 {o.url}")
            txt.insert("1.0", "\n".join(lines))
            txt.configure(state="disabled")

        def export_dialog(self) -> None:
            if not self.opportunities:
                messagebox.showinfo("تصدير", "ابدأ التحليل الأول.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")],
            )
            if not path:
                return
            try:
                p = export(self.opportunities, path,
                           marketplace=self.mp_var.get(),
                           tag=self._current_tag())
                messagebox.showinfo(
                    "تم التصدير",
                    f"تم حفظ {len(self.opportunities)} صف في:\n{p}",
                )
            except Exception as exc:
                messagebox.showerror("فشل التصدير", str(exc))

        def export_top_picks(self) -> None:
            if not self.picks:
                messagebox.showinfo(
                    "تصدير أفضل ٢٠ منتج",
                    "ابدأ التحليل الأول — ساعتها هتلاقي الـ ٢٠ منتج هنا.",
                )
                return
            mp = self.mp_var.get()
            default_name = f"nexora_top20_{mp}.xlsx"
            path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                initialfile=default_name,
                filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")],
            )
            if not path:
                return
            try:
                p = export(self.picks, path, marketplace=mp, tag=self._current_tag())
                tag_disp = self._current_tag() or "(فاضي — افتح الإعدادات)"
                messagebox.showinfo(
                    "تم تصدير الـ ٢٠ منتج",
                    f"تم حفظ {len(self.picks)} منتج في:\n{p}\n\n"
                    f"السوق: {MARKETPLACES[mp]['name']}\n"
                    f"Tag: {tag_disp}",
                )
            except Exception as exc:
                messagebox.showerror("فشل التصدير", str(exc))

        def clear_cache(self) -> None:
            cache.clear()
            self.log("🧹 تم مسح الذاكرة المؤقتة.")

        # ---------- Website integration (products.js) ----------
        def _ensure_products_js_path(self) -> str:
            """Ensure we have a products.js path. Prompt the user if missing."""
            path = (self.config.get("products_js_path") or "").strip()
            if path and Path(path).exists():
                return path
            # Ask user to choose
            if not messagebox.askyesno(
                "مسار products.js",
                "مفيش مسار محدد لملف products.js بتاع موقعك.\n"
                "تحب تختار الملف دلوقتي؟",
            ):
                return ""
            chosen = filedialog.askopenfilename(
                title="اختار ملف products.js",
                filetypes=[("JavaScript", "*.js"), ("الكل", "*.*")],
            )
            if not chosen:
                return ""
            self.config["products_js_path"] = chosen
            save_config(self.config)
            return chosen

        def add_one_to_site(self, o: Opportunity) -> None:
            """Add a single product to the site's products.js (with dedupe)."""
            path = self._ensure_products_js_path()
            if not path:
                return
            try:
                existing = load_products_js(path)
                new_item = opportunity_to_product(
                    o, marketplace=self.mp_var.get(), tag=self._current_tag()
                )
                merged, added, updated = merge_products_into_site(
                    existing, [new_item]
                )
                save_products_js(path, merged)
            except Exception as exc:
                messagebox.showerror("فشل الإضافة", f"خطأ:\n{exc}")
                return
            if added:
                msg = "تمت الإضافة للموقع 👍"
            elif updated:
                msg = "المنتج موجود قبل كده — تم تحديث بياناته."
            else:
                msg = "لم يتم تغيير شيء."
            self.set_status(f"📤 {msg}  ({Path(path).name})")
            self._refresh_site_products()

        def add_all_picks_to_site(self) -> None:
            """Add all current TOP 20 picks to the site (with dedupe)."""
            if not self.picks:
                messagebox.showinfo(
                    "إضافة للموقع",
                    "ابدأ التحليل الأول — ساعتها هتظهر الـ ٢٠ منتج هنا.",
                )
                return
            path = self._ensure_products_js_path()
            if not path:
                return
            try:
                existing = load_products_js(path)
                new_items = [
                    opportunity_to_product(
                        o, marketplace=self.mp_var.get(), tag=self._current_tag()
                    )
                    for o in self.picks
                ]
                merged, added, updated = merge_products_into_site(
                    existing, new_items
                )
                save_products_js(path, merged)
            except Exception as exc:
                messagebox.showerror("فشل الإضافة", f"خطأ:\n{exc}")
                return
            messagebox.showinfo(
                "تمت الإضافة للموقع",
                f"تمت الإضافة بنجاح ✅\n\n"
                f"➕ منتجات جديدة:  {added}\n"
                f"♻ منتجات تم تحديثها:  {updated}\n\n"
                f"📂 الملف: {path}",
            )
            self.set_status(
                f"📤 تمت إضافة {added} منتج جديد للموقع "
                f"(و {updated} تحديث)"
            )
            self._refresh_site_products()

        def add_url_to_site(self) -> None:
            """Manually paste an Amazon URL and add it as a product."""
            top = tk.Toplevel(self.root)
            top.title("إضافة منتج برابط أمازون")
            top.geometry("560x220")
            top.configure(bg="#0d1b2a")
            top.transient(self.root)

            tk.Label(top, text="🔗 الصق رابط منتج من أمازون:",
                     bg="#0d1b2a", fg="#e8a020",
                     font=("Segoe UI", 12, "bold")).pack(pady=(18, 8))
            entry = tk.Entry(top, width=70, bg="#1a2e42", fg="#fff",
                             insertbackground="#fff", relief="flat",
                             font=("Segoe UI", 10))
            entry.pack(padx=20, ipady=6)
            tk.Label(top,
                     text="مثال: https://www.amazon.com/dp/B08HM4133L",
                     bg="#0d1b2a", fg="#5a7a9a",
                     font=("Segoe UI", 8, "italic")).pack(pady=(4, 12))

            def submit() -> None:
                url = entry.get().strip()
                if not url:
                    return
                # extract ASIN from URL
                import re
                m = re.search(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})", url)
                if not m:
                    messagebox.showerror(
                        "رابط غير صالح",
                        "الرابط ده مش رابط منتج أمازون صحيح.\n"
                        "تأكد إنه يحتوي على /dp/ASIN.",
                    )
                    return
                asin = m.group(1)
                top.destroy()
                self.set_status(f"⏳ جاري جلب بيانات المنتج {asin}...")
                # Build a minimal opportunity, then enrich via Amazon
                o = Opportunity(asin=asin, source="Manual", type="manual")
                try:
                    mi = MarketIntelligence(
                        use_selenium=False, deep=True,
                        marketplace=self.mp_var.get(),
                        log_callback=lambda m: None,
                    )
                    detail = mi.amazon.product_detail(asin)
                    if detail:
                        o.amazon = detail
                        if detail.title:
                            o.title = detail.title
                        o.category = categorize(o.keyword, o.title)
                        o.profit = calculate_profit(detail, o.category)
                except Exception as exc:
                    log.warning("manual ASIN fetch failed: %s", exc)
                self.add_one_to_site(o)

            btns = tk.Frame(top, bg="#0d1b2a")
            btns.pack(pady=12)
            tk.Button(btns, text="📤 إضافة", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                      command=submit
                      ).pack(side="left", padx=6, ipady=6, ipadx=20)
            tk.Button(btns, text="إلغاء", bg="#5a6c7d", fg="#fff",
                      font=("Segoe UI", 10), relief="flat", cursor="hand2",
                      command=top.destroy
                      ).pack(side="left", padx=6, ipady=6, ipadx=14)

        # ---------- Website tab ----------
        def _build_site_tab(self) -> None:
            """Tab: list of products currently in the site's products.js."""
            # Banner
            banner = tk.Frame(self.site_tab, bg="#0d2235", pady=10)
            banner.pack(fill="x")
            tk.Label(banner, text="🌐 منتجات الموقع",
                     bg="#0d2235", fg="#7ec8a0",
                     font=("Segoe UI", 14, "bold")).pack(side="left", padx=14)
            tk.Label(banner,
                     text="المنتجات اللي حالياً على products.js بتاع موقعك",
                     bg="#0d2235", fg="#a0b4c8",
                     font=("Segoe UI", 9, "italic")).pack(side="left", padx=4)

            tk.Button(banner, text="🔄 تحديث",
                      bg="#3a4f66", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=self._refresh_site_products
                      ).pack(side="right", padx=6, ipady=4, ipadx=10)
            tk.Button(banner, text="➕ إضافة برابط أمازون",
                      bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                      command=self.add_url_to_site
                      ).pack(side="right", padx=6, ipady=4, ipadx=10)
            tk.Button(banner, text="📂 فتح مجلد الملف",
                      bg="#5a6c7d", fg="#fff",
                      font=("Segoe UI", 9), relief="flat", cursor="hand2",
                      command=self._open_site_folder
                      ).pack(side="right", padx=6, ipady=4, ipadx=10)

            self.site_status = tk.StringVar(value="حدد مسار products.js من ⚙ الإعدادات.")
            tk.Label(self.site_tab, textvariable=self.site_status,
                     bg="#0d1b2a", fg="#e8a020",
                     font=("Segoe UI", 9, "italic"), anchor="w"
                     ).pack(fill="x", padx=14, pady=(4, 0))

            # scroll area
            container = tk.Frame(self.site_tab, bg="#0d1b2a")
            container.pack(fill="both", expand=True, padx=8, pady=8)
            canvas = tk.Canvas(container, bg="#0d1b2a", highlightthickness=0)
            scroll = tk.Scrollbar(container, orient="vertical",
                                  command=canvas.yview)
            self.site_inner = tk.Frame(canvas, bg="#0d1b2a")
            self.site_inner.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=self.site_inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            self.site_canvas = canvas

            # initial load
            self._refresh_site_products()

        def _open_site_folder(self) -> None:
            path = (self.config.get("products_js_path") or "").strip()
            if not path:
                messagebox.showinfo(
                    "مسار غير محدد",
                    "حدد مسار products.js من ⚙ الإعدادات الأول.",
                )
                return
            folder = str(Path(path).parent)
            try:
                if sys.platform == "win32":
                    os.startfile(folder)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])
            except Exception as exc:
                messagebox.showerror("فشل الفتح", str(exc))

        def _refresh_site_products(self) -> None:
            """Reload products.js and render the list with delete buttons."""
            if not hasattr(self, "site_inner"):
                return
            for w in self.site_inner.winfo_children():
                w.destroy()

            path = (self.config.get("products_js_path") or "").strip()
            if not path:
                self.site_status.set(
                    "⚠ حدد مسار products.js من ⚙ الإعدادات الأول."
                )
                tk.Label(self.site_inner,
                         text="\n\n🌐  اضغط ⚙ الإعدادات وحدد مسار ملف products.js\n"
                              "بتاع موقعك. بعدها هتظهر المنتجات هنا.\n",
                         bg="#0d1b2a", fg="#5a7a9a",
                         font=("Segoe UI", 11), justify="center"
                         ).pack(pady=40)
                return
            if not Path(path).exists():
                self.site_status.set(f"⚠ الملف مش موجود: {path}")
                tk.Label(self.site_inner,
                         text=f"\n\n⚠  الملف مش موجود في المسار:\n{path}\n\n"
                              "اتأكد من المسار في ⚙ الإعدادات.",
                         bg="#0d1b2a", fg="#e07b3b",
                         font=("Segoe UI", 10), justify="center"
                         ).pack(pady=40)
                return

            try:
                products = load_products_js(path)
            except Exception as exc:
                self.site_status.set(f"⚠ فشل قراءة الملف: {exc}")
                return

            self.site_status.set(
                f"📂 {Path(path).name}  •  {len(products)} منتج على الموقع"
            )

            if not products:
                tk.Label(self.site_inner,
                         text="\n\n📭  الموقع لسه فاضي.\n\n"
                              "اضغط '📤 إضافة كل الـ ٢٠ للموقع' "
                              "من تاب أفضل ٢٠ منتج.\n",
                         bg="#0d1b2a", fg="#5a7a9a",
                         font=("Segoe UI", 11), justify="center"
                         ).pack(pady=40)
                return

            for idx, prod in enumerate(products):
                self._add_site_card(idx, prod, path)

        def _add_site_card(
            self, idx: int, prod: dict[str, Any], path: str
        ) -> None:
            """One card for a site product, with a delete button."""
            cat = prod.get("category", "other")
            theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["other"])
            outer = tk.Frame(self.site_inner, bg=theme["color"])
            outer.pack(fill="x", padx=4, pady=(0, 6))
            card = tk.Frame(outer, bg="#1a2e42")
            card.pack(fill="x", padx=2, pady=(0, 2))

            # title row
            top_row = tk.Frame(card, bg="#1a2e42")
            top_row.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(top_row, text=f"#{idx+1}",
                     bg="#1a2e42", fg="#7ec8a0",
                     font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 8))
            title = (prod.get("title") or "بدون عنوان")[:80]
            tk.Label(top_row, text=title,
                     bg="#1a2e42", fg="#fff",
                     font=("Segoe UI", 10, "bold"),
                     wraplength=900, anchor="w", justify="left"
                     ).pack(side="left", fill="x", expand=True)
            tk.Label(top_row,
                     text=f" {theme['emoji']} {theme['name']} ",
                     bg=theme["color"], fg="#0d1b2a",
                     font=("Segoe UI", 8, "bold")).pack(side="right")

            # stats
            stats = []
            if prod.get("price"):
                stats.append(prod["price"])
            if prod.get("rating"):
                stats.append(f"⭐ {prod['rating']} ({prod.get('reviewCount', '')})")
            if prod.get("socialProof"):
                stats.append(f"👥 {prod['socialProof']}")
            if prod.get("badge"):
                stats.append(prod["badge"])
            if stats:
                tk.Label(card, text="  •  ".join(stats),
                         bg="#1a2e42", fg="#a0b4c8",
                         font=("Segoe UI", 9), anchor="w"
                         ).pack(fill="x", padx=10, pady=2)

            # buttons
            bf = tk.Frame(card, bg="#1a2e42")
            bf.pack(fill="x", padx=10, pady=(4, 10))
            link = prod.get("link", "")
            tk.Button(bf, text="🛒 فتح", bg="#27ae60", fg="#fff",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=link: webbrowser.open(u) if u else None
                      ).pack(side="left", padx=(0, 6), ipady=3, ipadx=8)
            tk.Button(bf, text="📋 نسخ الرابط", bg="#e8a020", fg="#000",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda u=link: self._copy(u)
                      ).pack(side="left", padx=(0, 6), ipady=3, ipadx=8)
            tk.Button(bf, text="🗑 حذف من الموقع",
                      bg="#c0392b", fg="#fff",
                      font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                      command=lambda i=idx, p=prod: self._delete_site_product(i, p, path)
                      ).pack(side="right", ipady=3, ipadx=8)

            # link inline (small)
            if link:
                tk.Label(card, text=link,
                         bg="#1a2e42", fg="#5a7a9a",
                         font=("Consolas", 7), anchor="w"
                         ).pack(fill="x", padx=10, pady=(0, 6))

        def _delete_site_product(
            self, idx: int, prod: dict[str, Any], path: str
        ) -> None:
            title = (prod.get("title") or "")[:60]
            if not messagebox.askyesno(
                "حذف منتج من الموقع",
                f"هل أنت متأكد من حذف هذا المنتج من products.js؟\n\n{title}",
            ):
                return
            try:
                products = load_products_js(path)
                # delete by exact match on link (more stable than index)
                target_link = (prod.get("link") or "").strip()
                products = [
                    p for p in products
                    if (p.get("link") or "").strip() != target_link
                ]
                save_products_js(path, products)
            except Exception as exc:
                messagebox.showerror("فشل الحذف", str(exc))
                return
            self.set_status(f"🗑 تم حذف منتج من الموقع. ({len(products)} متبقي)")
            self._refresh_site_products()

    root = tk.Tk()
    App(root)
    root.mainloop()


# ============================================================
# CLI
# ============================================================
def run_cli(args: argparse.Namespace) -> int:
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    cfg = load_config()
    marketplace = args.marketplace or cfg.get("marketplace", "us")
    if marketplace not in MARKETPLACES:
        marketplace = "us"
    tag = args.tag or cfg.get("affiliate_tags", {}).get(marketplace, "")

    log.info(
        "CLI run | sources=%s deep=%s headless=%s marketplace=%s",
        sources, args.deep, args.headless, marketplace,
    )

    mi = MarketIntelligence(
        use_selenium=not args.no_selenium,
        headless=args.headless,
        deep=args.deep,
        marketplace=marketplace,
        log_callback=lambda m: log.info(m),
    )
    opps = mi.run(sources)

    # ----- TOP 20 PICKS (curated, balanced across categories) -----
    n_per = int(cfg.get("top_per_category", 5))
    picks = top_picks(opps, n_per_cat=n_per, total=20)
    grouped = picks_grouped_by_category(picks)
    mp_name = MARKETPLACES[marketplace]["name"]

    print("\n" + "=" * 70)
    print(f" 🏆  أفضل ٢٠ منتج  —  {mp_name}  —  Tag: {tag or '(فاضي)'}")
    print("=" * 70)
    rank = 0
    for cat, items in grouped.items():
        if not items:
            continue
        theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["other"])
        print(f"\n  {theme['emoji']}  {theme['name']}  ({len(items)} منتج)")
        print("  " + "-" * 66)
        for o in items:
            rank += 1
            line = f"  #{rank:>2}  [{o.score:>3}/100]  {(o.title or o.keyword)[:50]:<50}"
            if o.profit and o.profit.estimated_monthly_commission:
                line += f"  💰 ~${o.profit.estimated_monthly_commission:,.0f}/شهر"
            if o.trend.direction != "unknown":
                line += f"  {o.trend.sparkline}"
            print(line)
            url = affiliate_url(o.asin, o.keyword, marketplace, tag)
            if url:
                print(f"        🔗 {url}")

    # ----- All opps summary -----
    if not args.top_picks_only:
        top = opps[: args.top] if args.top > 0 else opps
        print("\n" + "=" * 70)
        print(f" 📋  كل الفرص — أفضل {len(top)}")
        print("=" * 70)
        for i, o in enumerate(top, 1):
            line = f"{i:>2}. [{o.score:>3}] {o.label()[:55]}"
            if o.amazon and o.amazon.price:
                line += f" | ${o.amazon.price}"
            if o.profit and o.profit.estimated_monthly_commission:
                line += f" | ~${o.profit.estimated_monthly_commission:,.0f}/شهر"
            if o.competition and o.competition.tier != "unknown":
                comp_ar = COMPETITION_LABELS.get(
                    o.competition.tier, o.competition.tier
                )
                line += f" | {comp_ar}"
            if o.trend.direction != "unknown":
                line += f" | {o.trend.sparkline}"
            print(line)

    if args.export:
        path = export(opps, args.export, marketplace=marketplace, tag=tag)
        print(f"\n💾 تم التصدير في: {path}")
    if args.export_top_picks:
        path = export(picks, args.export_top_picks, marketplace=marketplace, tag=tag)
        print(f"💾 تم تصدير الـ ٢٠ منتج في: {path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "نكسورا — أداة استكشاف فرص أمازون v2.6  "
            "(NEXORA Market Intelligence)"
        )
    )
    p.add_argument("--no-gui", action="store_true",
                   help="تشغيل من سطر الأوامر فقط (بدون واجهة)")
    p.add_argument("--sources", default="google,pinterest,tiktok,amazon",
                   help="المصادر مفصولة بفواصل: google,pinterest,tiktok,amazon")
    p.add_argument("--deep", action="store_true", default=True,
                   help="تحليل أمازون عميق (افتراضي مفعّل)")
    p.add_argument("--no-deep", dest="deep", action="store_false",
                   help="تخطي التحليل العميق")
    p.add_argument("--headless", action="store_true", default=True,
                   help="تشغيل Chrome بدون واجهة (افتراضي مفعّل)")
    p.add_argument("--no-headless", dest="headless", action="store_false",
                   help="تشغيل Chrome بواجهة ظاهرة")
    p.add_argument("--no-selenium", action="store_true",
                   help="تخطي Selenium (الاعتماد على requests + pytrends فقط)")
    p.add_argument("--marketplace", default="",
                   choices=["", *MARKETPLACES.keys()],
                   help="السوق على أمازون: us / uk / de / fr / it / es")
    p.add_argument("--tag", default="",
                   help="Amazon Associate tag (يتجاوز الإعدادات لهذه التشغيلة فقط)")
    p.add_argument("--top", type=int, default=25,
                   help="عدد الفرص في قسم 'كل الفرص'")
    p.add_argument("--top-picks-only", action="store_true",
                   help="إظهار أفضل ٢٠ منتج فقط (تخطي قسم كل الفرص)")
    p.add_argument("--export", default="",
                   help="تصدير كل الفرص: .xlsx / .csv / .json")
    p.add_argument("--export-top-picks", default="",
                   help="تصدير أفضل ٢٠ منتج: .xlsx / .csv / .json")
    p.add_argument("--clear-cache", action="store_true",
                   help="مسح الذاكرة المؤقتة والخروج")
    p.add_argument("--verbose", action="store_true",
                   help="إظهار سجلات التشخيص الكاملة")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        for h in log.handlers:
            h.setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)

    if args.clear_cache:
        cache.clear()
        print("🧹 تم مسح الذاكرة المؤقتة.")
        return 0

    if args.no_gui:
        return run_cli(args)
    try:
        run_gui(initial_sources=[s.strip() for s in args.sources.split(",")])
    except Exception as exc:
        log.error("GUI failed: %s", exc)
        print(f"⚠ فشل تشغيل الواجهة: {exc}\n→ تم التحويل لوضع سطر الأوامر...")
        return run_cli(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
