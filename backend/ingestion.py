import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from backend.config import FINNHUB_API_KEY, CURRENTS_API_KEY, FRESHNESS_LOOKBACK_MINUTES
from backend.seed_data import SCENARIOS

def normalize_iso_timestamp(ts: str) -> datetime:
    """Helper to convert various timestamp formats to timezone-aware datetime."""
    try:
        # Standard ISO format with 'Z'
        if ts.endswith('Z'):
            return datetime.fromisoformat(ts[:-1]).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        # Fallback to current time if parsing fails
        return datetime.now(timezone.utc)

def fetch_finnhub_direct_news(symbol: str, minutes_lookback: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches company-specific news from Finnhub.
    API: GET /company-news?symbol={symbol}&from={date}&to={date}
    """
    if not FINNHUB_API_KEY:
        print(f"Warning: Finnhub API Key not set. Direct news fetch for {symbol} skipped.")
        return []

    now = datetime.now(timezone.utc)
    # Finnhub requires YYYY-MM-DD
    today_str = now.strftime("%Y-%m-%d")
    
    url = f"https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from": today_str,
        "to": today_str,
        "token": FINNHUB_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Finnhub API error ({response.status_code}): {response.text}")
            return []
        
        articles = response.json()
        normalized = []
        for art in articles:
            # Finnhub timestamp is unix epoch in seconds
            published_dt = datetime.fromtimestamp(art.get("datetime", 0), timezone.utc)
            
            normalized.append({
                "articleId": f"finnhub_{art.get('id', '')}",
                "sourceApi": "finnhub",
                "sourceName": art.get("source", "Finnhub"),
                "url": art.get("url", ""),
                "headline": art.get("headline", ""),
                "summary": art.get("summary", ""),
                "publishedAt": published_dt.isoformat(),
                "relatedTickers": [symbol]
            })
        return normalized
    except Exception as e:
        print(f"Error fetching Finnhub news for {symbol}: {e}")
        return []

def fetch_currents_cross_impact_news(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Fetches broad external news from Currents API matching query terms.
    API: GET /search?keywords={query}&language=en
    """
    if not CURRENTS_API_KEY:
        print("Warning: Currents API Key not set. Cross-impact news fetch skipped.")
        return []
    
    if not keywords:
        return []

    # Join keywords with OR or run targeted search
    query_str = " OR ".join(keywords)
    url = f"https://api.currentsapi.services/v1/search"
    params = {
        "keywords": query_str,
        "language": "en",
        "apiKey": CURRENTS_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Currents API error ({response.status_code}): {response.text}")
            return []
        
        data = response.json()
        articles = data.get("news", [])
        normalized = []
        for art in articles:
            # Currents uses standard ISO string for published
            normalized.append({
                "articleId": f"currents_{art.get('id', '')}",
                "sourceApi": "currents",
                "sourceName": art.get("author", "Currents"),
                "url": art.get("url", ""),
                "headline": art.get("title", ""),
                "summary": art.get("description", ""),
                "publishedAt": art.get("published", ""),
                "relatedTickers": []  # Currents doesn't tag tickers
            })
        return normalized
    except Exception as e:
        print(f"Error fetching Currents news: {e}")
        return []

def get_news_payload(
    symbol_watchlist: List[str], 
    cross_impact_keywords: List[str], 
    scenario_id: str = "live",
    simulated_now_str: str = "2026-05-28T17:25:00Z",
    extra_tickers: List[str] = None
) -> Dict[str, Any]:
    """
    Fetches news from either live APIs or scenario mock data.
    Applies the freshness window filter: articles published in the last N minutes 
    (where N is FRESHNESS_LOOKBACK_MINUTES).
    """
    all_articles = []
    
    if scenario_id != "live":
        # Load simulated scenario articles
        scenario = SCENARIOS.get(scenario_id)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found.")
        
        all_articles = list(scenario["articles"])
        # Use simulated 'now' for filtering
        reference_time = normalize_iso_timestamp(simulated_now_str)
        print(f"Replay Scenario Active: {scenario['name']}")
        print(f"Simulating time: {reference_time.isoformat()}")
    else:
        # Fetch Live
        tickers_to_query = list(symbol_watchlist)
        if extra_tickers:
            tickers_to_query.extend([t for t in extra_tickers if t not in tickers_to_query])
            
        print(f"Live Ingestion Active. Watchlist Tickers: {symbol_watchlist}. Extra Tickers: {extra_tickers}. Cross-impact Keywords: {cross_impact_keywords}")
        # Fetch Finnhub direct company-news for all target tickers
        for symbol in tickers_to_query:
            all_articles.extend(fetch_finnhub_direct_news(symbol))
        
        # Fetch Currents cross-impact news
        if cross_impact_keywords:
            all_articles.extend(fetch_currents_cross_impact_news(cross_impact_keywords))
            
        reference_time = datetime.now(timezone.utc)

    # Apply freshness filter: last N minutes lookback buffer
    filtered_articles = []
    seen_urls = set()
    
    print(f"Filtering articles using FRESHNESS_LOOKBACK_MINUTES = {FRESHNESS_LOOKBACK_MINUTES} mins (relative to reference time: {reference_time.isoformat()})")
    for art in all_articles:
        url = art.get("url", "")
        if not url or url in seen_urls:
            continue
        
        pub_time = normalize_iso_timestamp(art.get("publishedAt", ""))
        time_diff_sec = (reference_time - pub_time).total_seconds()
        delta_mins = time_diff_sec / 60.0
        
        # Log each article details to show user time delta
        print(f"  - Article: '{art.get('headline')[:60]}...' | Published: {art.get('publishedAt')} | Delta: {delta_mins:.2f} mins")
        
        # Freshness filter:
        # - not in the future (relative to reference_time)
        # - published within the configured lookback window
        is_fresh = 0 <= time_diff_sec <= (FRESHNESS_LOOKBACK_MINUTES * 60)
        
        if is_fresh or scenario_id != "live":
            filtered_articles.append(art)
            seen_urls.add(url)
            
    print(f"Ingested {len(all_articles)} articles, {len(filtered_articles)} passed freshness filter.")
    return {
        "articles": filtered_articles,
        "total_ingested": len(all_articles),
        "passed_freshness": len(filtered_articles)
    }
