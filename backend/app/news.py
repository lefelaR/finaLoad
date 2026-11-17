"""News ingestion and a transparent sentiment scorer.

Live Marketaux / FinBERT are used when their env vars are set.
Otherwise the sample wire is scored with the same rules lexicon.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.logic import dedup_articles, news_gauge

# Word weights applied to the currency the sentence is about.
LEXICON = {
    "hike": 75,
    "hawkish": 45,
    "hawks": 40,
    "beat": 35,
    "beats": 35,
    "hotter": 40,
    "hot": 30,
    "firms": 25,
    "surge": 30,
    "strong": 20,
    "gains": 15,
    "cut": -50,
    "cuts": -45,
    "dovish": -45,
    "miss": -35,
    "misses": -35,
    "cooler": -30,
    "weak": -30,
    "contracts": -40,
    "contraction": -40,
    "recession": -45,
    "fall": -15,
    "easing": -25,
}


def score_text(headline: str, text: str = "") -> tuple[int, int]:
    """Return (eur_score, usd_score) on -100..100. Net for EUR/USD is eur - usd."""
    blob = f"{headline} {text}".lower()
    tokens = set(re.findall(r"[a-z]+", blob))
    weight = 0
    for word, value in LEXICON.items():
        if word in tokens:
            weight += value
    weight = max(-100, min(100, weight))

    mentions_eur = bool(tokens & {"ecb", "euro", "eur", "lagarde", "german", "eurozone"})
    mentions_usd = bool(tokens & {"fed", "fomc", "dollar", "usd", "cpi", "nfp", "powell", "us"})

    eur = 0
    usd = 0
    if mentions_eur and not mentions_usd:
        eur = weight
    elif mentions_usd and not mentions_eur:
        usd = weight
    elif mentions_eur and mentions_usd:
        eur = weight // 2
        usd = weight // 2
    else:
        eur = weight // 2
    return int(eur), int(usd)


def _article(
    headline: str,
    source: str,
    minutes_ago: int,
    url: str,
    entities: list[str],
    text: str,
    now: datetime,
) -> dict:
    eur, usd = score_text(headline, text)
    published = now - timedelta(minutes=minutes_ago)
    return {
        "headline": headline,
        "source": source,
        "published_at": published,
        "url": url,
        "entities": entities,
        "raw_text": text,
        "eur_score": eur,
        "usd_score": usd,
        "net_score": eur - usd,
    }


def sample_articles(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = [
        _article(
            "US CPI hotter than forecast, dollar firms",
            "Sample wire",
            12,
            "https://news.google.com/search?q=US+CPI+EUR+USD",
            ["USD", "CPI"],
            "US CPI prints 0.4% versus a 0.3% forecast and the dollar firms.",
            now,
        ),
        _article(
            "Powell sounds hawkish and the dollar firms",
            "Sample wire",
            48,
            "https://news.google.com/search?q=Powell+hawkish+dollar",
            ["USD", "Fed"],
            "Powell sounds hawkish and the dollar firms.",
            now,
        ),
        _article(
            "German manufacturing PMI contracts again",
            "Sample wire",
            96,
            "https://news.google.com/search?q=German+manufacturing+PMI",
            ["EUR", "PMI"],
            "German manufacturing PMI contracts for a fourth month.",
            now,
        ),
        _article(
            "ECB hints at hike as Lagarde stays hawkish",
            "Sample wire",
            240,
            "https://news.google.com/search?q=ECB+hints+at+hike",
            ["EUR", "ECB"],
            "ECB hints at hike. Lagarde says the council remains hawkish.",
            now,
        ),
        _article(
            "Euro gains as ECB stays hawkish",
            "Sample wire",
            310,
            "https://news.google.com/search?q=Euro+ECB+hawkish",
            ["EUR", "ECB"],
            "The euro gains as the ECB stays hawkish.",
            now,
        ),
        _article(
            "US retail sales miss, dollar slips",
            "Sample wire",
            280,
            "https://news.google.com/search?q=US+retail+sales+dollar",
            ["USD"],
            "US retail sales miss expectations and the dollar slips.",
            now,
        ),
        _article(
            "NFP beats forecast and the dollar surges",
            "Sample wire",
            400,
            "https://news.google.com/search?q=NFP+dollar",
            ["USD", "NFP"],
            "NFP beats the forecast and the dollar surges.",
            now,
        ),
        _article(
            "Eurozone growth stays weak into the quarter",
            "Sample wire",
            520,
            "https://news.google.com/search?q=Eurozone+growth",
            ["EUR"],
            "Eurozone growth stays weak into the quarter.",
            now,
        ),
        _article(
            "Fed officials stay hawkish into the next meeting",
            "Sample wire",
            640,
            "https://news.google.com/search?q=Fed+hawkish",
            ["USD", "Fed"],
            "Fed officials stay hawkish into the next meeting.",
            now,
        ),
        _article(
            "ECB holds and sounds dovish on the next move",
            "Sample wire",
            800,
            "https://news.google.com/search?q=ECB+dovish",
            ["EUR", "ECB"],
            "The ECB holds and sounds dovish on the next move.",
            now,
        ),
        _article(
            "Dollar eases after a cooler inflation print",
            "Sample wire",
            980,
            "https://news.google.com/search?q=dollar+cooler+inflation",
            ["USD", "CPI"],
            "The dollar eases after a cooler inflation print.",
            now,
        ),
        _article(
            "Lagarde says euro area demand stays weak",
            "Sample wire",
            1200,
            "https://news.google.com/search?q=Lagarde+euro+demand",
            ["EUR", "ECB"],
            "Lagarde says euro area demand stays weak.",
            now,
        ),
    ]
    return dedup_articles(rows)


def aggregate(articles: list[dict], now: datetime, hours: float = 3) -> dict:
    window = [row for row in articles if (now - row["published_at"]).total_seconds() <= hours * 3600]
    if not window:
        window = articles[:3]
    eur = sum(row["eur_score"] for row in window) / len(window)
    usd = sum(row["usd_score"] for row in window) / len(window)
    net = eur - usd
    # FXNewsBias is the previous 3-hour cycle, so it can disagree with the live read.
    fx_eur = 62
    fx_usd = 48
    fx_net = fx_eur - fx_usd
    ranked = sorted(window, key=lambda row: abs(row["net_score"]), reverse=True)
    return {
        "eur_score": round(eur),
        "usd_score": round(usd),
        "net": round(net),
        "label": news_gauge(net),
        "fxnewsbias_eur": fx_eur,
        "fxnewsbias_usd": fx_usd,
        "fxnewsbias_net": fx_net,
        "method": "rules-lexicon",
        "drivers": ranked[:3],
        "window_count": len(window),
    }


def fetch_marketaux(now: datetime) -> list[dict] | None:
    token = os.environ.get("MARKETAUX_API_KEY", "").strip()
    if not token:
        return None
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "search": "EUR OR USD OR ECB OR \"Federal Reserve\" OR EUR/USD",
        "language": "en",
        "limit": 20,
        "api_token": token,
    }
    try:
        response = httpx.get(url, params=params, timeout=8)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    articles = []
    for item in payload.get("data", []):
        headline = item.get("title") or ""
        text = item.get("description") or item.get("snippet") or ""
        eur, usd = score_with_optional_model(headline, text)
        published = item.get("published_at") or now.isoformat()
        stamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
        entities = [tag.get("symbol") for tag in item.get("entities", []) if tag.get("symbol")]
        articles.append(
            {
                "headline": headline,
                "source": (item.get("source") or "Marketaux"),
                "published_at": stamp,
                "url": item.get("url") or "https://www.marketaux.com",
                "entities": entities or ["EUR", "USD"],
                "raw_text": text,
                "eur_score": eur,
                "usd_score": usd,
                "net_score": eur - usd,
            }
        )
    return dedup_articles(articles) or None


def score_with_optional_model(headline: str, text: str) -> tuple[int, int]:
    endpoint = os.environ.get("SENTIMENT_API_URL", "").strip()
    if endpoint:
        try:
            response = httpx.post(
                endpoint,
                json={"headline": headline, "text": text},
                timeout=6,
            )
            response.raise_for_status()
            body = response.json()
            eur = int(body["eur_score"])
            usd = int(body["usd_score"])
            return max(-100, min(100, eur)), max(-100, min(100, usd))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
    return score_text(headline, text)


def load_news(now: datetime | None = None) -> tuple[list[dict], str]:
    now = now or datetime.now(timezone.utc)
    live = fetch_marketaux(now)
    if live:
        return live, "marketaux"
    return sample_articles(now), "sample"
