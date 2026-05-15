"""Fetches financial news and market data; builds GoldBot seed document."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

YF_SYMBOL_MAP = {
    "XAUUSD": "GC=F",
    "XAUUSD=X": "GC=F",
}

NEWS_QUERY_MAP = {
    "XAUUSD": (
        "gold OR xauusd OR bullion OR fed OR powell OR inflation OR "
        "treasury yields OR us dollar OR central bank"
    ),
}


def _yf_symbol(ticker: str) -> str:
    symbol = YF_SYMBOL_MAP.get(ticker.upper(), ticker)
    if ticker.upper() == "XAUUSD=X":
        symbol = "GC=F"
    print(f"[DEBUG] GoldBot using YFinance Ticker: {symbol}")
    return symbol


def _news_query(ticker: str) -> str:
    return NEWS_QUERY_MAP.get(ticker.upper(), ticker)


def fetch_news(ticker: str, days: int = 2) -> list[dict]:
    """Fetch recent news articles for a ticker via NewsAPI."""
    import requests

    api_key = os.getenv("NEWS_API_KEY", "").strip()
    if not api_key:
        return []

    now = datetime.now(timezone.utc)
    params = {
        "q": _news_query(ticker),
        "from": (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 10,
        "apiKey": api_key,
    }

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles", [])
        return [article for article in articles if isinstance(article, dict)]
    except Exception as exc:
        print(f"News fetch failed for {ticker}: {exc}")
        return []


def fetch_price_history(ticker: str, period: str = "10d", interval: str = "15m"):
    """Fetch price history for a ticker from Yahoo Finance."""
    import yfinance as yf

    yf_symbol = _yf_symbol(ticker)
    try:
        instrument = yf.Ticker(yf_symbol)
        history = instrument.history(period=period, interval=interval, auto_adjust=False)
    except Exception as exc:
        print(f"Price history failed for {ticker}: {exc}")
        return None

    if history is None or history.empty:
        return None

    cleaned = history.copy()
    cleaned = cleaned.rename(columns={column: str(column).title() for column in cleaned.columns})
    required_columns = [column for column in ("Open", "High", "Low", "Close") if column in cleaned.columns]
    if required_columns:
        cleaned = cleaned.dropna(subset=required_columns)
    return cleaned


def fetch_market_snapshot(ticker: str) -> dict:
    """Fetch a short market snapshot from yfinance."""
    import yfinance as yf

    yf_symbol = _yf_symbol(ticker)
    try:
        instrument = yf.Ticker(yf_symbol)
        history = instrument.history(period="5d")
        info = instrument.info or {}
    except Exception as exc:
        print(f"Market snapshot failed for {ticker}: {exc}")
        return {
            "ticker": ticker,
            "current_price": 0.0,
            "5d_change_pct": 0.0,
            "volume": 0,
            "52w_high": None,
            "52w_low": None,
            "market_cap": None,
            "sector": "Unknown",
        }

    current_price = 0.0
    change_pct = 0.0
    volume = 0

    if not history.empty:
        closes = history["Close"].dropna()
        volumes = history["Volume"].dropna() if "Volume" in history else []
        if not closes.empty:
            current_price = float(closes.iloc[-1])
            first_close = float(closes.iloc[0])
            if first_close:
                change_pct = ((current_price - first_close) / first_close) * 100.0
        if len(volumes):
            volume = int(volumes.iloc[-1])

    if not current_price:
        current_price = float(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
            or 0.0
        )

    return {
        "ticker": ticker,
        "market_symbol": yf_symbol,
        "current_price": round(current_price, 6),
        "5d_change_pct": round(change_pct, 3),
        "volume": volume or int(info.get("volume") or 0),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector", "Unknown"),
    }


def build_seed_document(ticker: str) -> str:
    """Build a markdown seed document for GoldBot ingestion."""
    market = fetch_market_snapshot(ticker)
    articles = fetch_news(ticker)

    lines = [f"# Financial Seed Report: {ticker}", "", "## Market Snapshot"]
    for key in (
        "ticker",
        "current_price",
        "5d_change_pct",
        "volume",
        "52w_high",
        "52w_low",
        "market_cap",
        "sector",
    ):
        lines.append(f"- {key.replace('_', ' ').title()}: {market.get(key)}")

    lines.extend(["", "## Recent News"])
    if not articles:
        lines.append("No recent news articles found.")
    else:
        for article in articles:
            title = article.get("title") or "Untitled"
            source = (article.get("source") or {}).get("name") or "Unknown"
            description = article.get("description") or "No description available."
            lines.extend(
                [
                    f"### {title}",
                    f"Source: {source}",
                    description,
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"
