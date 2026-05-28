import json
import re
from typing import TypedDict, List, Dict, Any, Tuple
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from backend.config import get_llm, get_llm_fast, FRESHNESS_LOOKBACK_MINUTES
from backend.ingestion import get_news_payload
from backend.routing import get_cross_impact_keywords, route_cross_impact
from backend.memory import check_ledger_decision

# Define LangGraph State
class WorkflowState(TypedDict):
    iteration: int
    watchlist: List[str]
    scenario_id: str
    simulated_now: str
    articles: List[Dict[str, Any]]
    canonical_events: List[Dict[str, Any]]
    routed_candidates: List[Dict[str, Any]]
    ticker_buckets: Dict[str, Dict[str, Any]]
    ticker_syntheses: Dict[str, Dict[str, Any]]
    duplicate_counts: Dict[str, int]
    ingestion_metadata: Dict[str, Any]
    llm_failed: bool  # Sentinel: set True if a critical LLM node fails; halts downstream LLM calls

def clean_json_string(text: str) -> str:
    """Cleans markdown JSON code blocks from LLM output if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

# 1. Fetch & Filter Node
def fetch_and_filter_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 1: Fetching & Filtering News] ---")
    iteration = state.get("iteration", 3)
    watchlist = state.get("watchlist", [])
    scenario_id = state.get("scenario_id", "live")
    simulated_now = state.get("simulated_now", "2026-05-28T17:25:00Z")
    
    # Query expansion is only active in Iteration 3
    cross_impact_keywords = []
    if iteration == 3:
        cross_impact_keywords = get_cross_impact_keywords(watchlist)
        print(f"Expanded search terms from exposure graph: {cross_impact_keywords}")
        
    payload = get_news_payload(
        symbol_watchlist=watchlist,
        cross_impact_keywords=cross_impact_keywords,
        scenario_id=scenario_id,
        simulated_now_str=simulated_now
    )
    
    return {
        "articles": payload["articles"],
        "ingestion_metadata": {
            "total_ingested": payload["total_ingested"],
            "passed_freshness": payload["passed_freshness"]
        }
    }

MOCK_EVENTS = {
    "finnhub_direct_001": {
        "eventType": "supply_chain",
        "eventSummary": "Apple unveils M5 chip utilizing TSMC 2nm technology.",
        "hardFacts": ["Apple announced M5 chip family", "Uses TSMC 2nm lithography", "40% faster local LLM processing"],
        "entities": ["Apple", "AAPL", "TSMC"],
        "eventTags": ["M5", "semiconductor", "2nm"],
        "regions": ["Taiwan"],
        "sectors": ["technology"],
        "commodities": ["microchips"],
        "technologyThemes": ["semiconductors"],
        "possibleDirectionalPressure": "positive",
        "uncertaintyNotes": ["yield rates of 2nm nodes"],
        "evidence": ["announced its M5 chip family", "leverages TSMC's 2nm lithography"]
    },
    "finnhub_direct_002": {
        "eventType": "earnings",
        "eventSummary": "Microsoft exceeds guidance fueled by 28% cloud growth from Copilot.",
        "hardFacts": ["Cloud revenue expanded 28%", "Boosted by Microsoft 365 Copilot adoption"],
        "entities": ["Microsoft", "MSFT"],
        "eventTags": ["cloud", "Copilot", "earnings"],
        "regions": [],
        "sectors": ["technology"],
        "commodities": [],
        "technologyThemes": ["frontier AI"],
        "possibleDirectionalPressure": "positive",
        "uncertaintyNotes": ["sustainability of Copilot subscription growth"],
        "evidence": ["cloud services grew 28%", "boosted by corporate adoption of Microsoft 365 Copilot"]
    },
    "finnhub_dup_001": {
        "eventType": "supply_chain",
        "eventSummary": "Fire reported at electronics manufacturing zone in Zhengzhou.",
        "hardFacts": ["fire in component warehouse", "Zhengzhou assembly zone", "no casualties"],
        "entities": ["Foxconn", "AAPL"],
        "eventTags": ["Zhengzhou", "fire", "factory"],
        "regions": ["China"],
        "sectors": ["technology"],
        "commodities": [],
        "technologyThemes": [],
        "possibleDirectionalPressure": "negative",
        "uncertaintyNotes": ["damage scale to inventory"],
        "evidence": ["Zhengzhou assembly zone", "fire broke out in a component warehouse"]
    },
    "finnhub_dup_002": {
        "eventType": "supply_chain",
        "eventSummary": "Fire reported at electronics manufacturing zone in Zhengzhou.",
        "hardFacts": ["fire in component warehouse", "Zhengzhou assembly zone"],
        "entities": ["Foxconn", "AAPL"],
        "eventTags": ["Zhengzhou", "fire", "factory"],
        "regions": ["China"],
        "sectors": ["technology"],
        "commodities": [],
        "technologyThemes": [],
        "possibleDirectionalPressure": "negative",
        "uncertaintyNotes": ["production impact"],
        "evidence": ["fire in a Zhengzhou electronics manufacturing plant", "examining potential damage"]
    },
    "finnhub_dup_003": {
        "eventType": "supply_chain",
        "eventSummary": "Fire reported at electronics manufacturing zone in Zhengzhou halts lines.",
        "hardFacts": ["fire in component warehouse", "Zhengzhou assembly zone", "assembly lines halted", "2 million iPhones delayed"],
        "entities": ["Foxconn", "AAPL", "Apple"],
        "eventTags": ["Zhengzhou", "fire", "halt", "iPhone"],
        "regions": ["China"],
        "sectors": ["technology"],
        "commodities": [],
        "technologyThemes": [],
        "possibleDirectionalPressure": "negative",
        "uncertaintyNotes": ["duration of shutdown"],
        "evidence": ["fire in Zhengzhou factory warehouse", "complete shutdown of advanced assembly lines", "delay shipment of 2 million iPhone units"]
    },
    "currents_cross_001": {
        "eventType": "natural_disaster",
        "eventSummary": "7.2 magnitude earthquake in Taiwan prompts foundry evacuations.",
        "hardFacts": ["7.2 magnitude earthquake struck eastern Taiwan", "Semiconductor fabs in Hsinchu evacuated", "Possible calibration damage to lithography tools"],
        "entities": ["Taiwan", "TSMC"],
        "eventTags": ["Taiwan", "earthquake", "lithography", "semiconductor"],
        "regions": ["Taiwan"],
        "sectors": ["technology"],
        "commodities": ["silicon", "microchips"],
        "technologyThemes": ["semiconductors"],
        "possibleDirectionalPressure": "negative",
        "uncertaintyNotes": ["calibration recovery time"],
        "evidence": ["7.2 magnitude earthquake shook eastern Taiwan", "evacuated staff", "calibration damage to high-end lithography equipment"]
    },
    "currents_cross_002": {
        "eventType": "private_company_technology",
        "eventSummary": "Anthropic launches Claude 3.7 Sonnet setting coding benchmarks.",
        "hardFacts": ["Anthropic launched Claude 3.7 Sonnet", "Outperforms platforms in coding, math, chemistry"],
        "entities": ["Anthropic", "Claude"],
        "eventTags": ["Anthropic", "Claude", "model release"],
        "regions": [],
        "sectors": ["technology"],
        "commodities": [],
        "technologyThemes": ["frontier AI"],
        "possibleDirectionalPressure": "positive",
        "uncertaintyNotes": ["pricing structures", "competitor response timeline"],
        "evidence": ["launched Claude 3.7 Sonnet", "achieves state-of-the-art results"]
    },
    "currents_cross_003": {
        "eventType": "geopolitical",
        "eventSummary": "Drone strikes near Bab el-Mandeb reroute Red Sea shipping.",
        "hardFacts": ["Cargo ships targeted by drone strikes in Bab el-Mandeb", "Red Sea route suspended", "Container rates surge 30%"],
        "entities": ["Red Sea", "Bab el-Mandeb"],
        "eventTags": ["Red Sea", "drone strikes", "shipping", "freight rates"],
        "regions": ["Red Sea", "Middle East"],
        "sectors": ["shipping", "airlines"],
        "commodities": ["oil"],
        "technologyThemes": [],
        "possibleDirectionalPressure": "negative",
        "uncertaintyNotes": ["duration of rerouting", "naval security intervention"],
        "evidence": ["targeted by drone strikes near the Bab el-Mandeb", "suspension of Red Sea", "rates surged 30%"]
    }
}

# 2. Canonical Event Extraction Node
def canonical_event_extraction_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 2: Canonical Event Extraction] ---")
    articles = state.get("articles", [])
    canonical_events = []
    
    if not articles:
        print("No articles fetched to extract events from.")
        return {"canonical_events": []}
        
    # Check if API Keys are set
    from backend.config import GEMINI_API_KEY, OPENAI_API_KEY
    use_mock = not (GEMINI_API_KEY or OPENAI_API_KEY)
    
    if use_mock:
        print("No LLM API keys found. Falling back to pre-baked canonical event extraction.")
        for art in articles:
            art_id = art["articleId"]
            
            if art_id in MOCK_EVENTS:
                event = copy_dict(MOCK_EVENTS[art_id])
            else:
                # Generic fallback if custom articles are passed
                event = {
                    "eventType": "other",
                    "eventSummary": art["headline"],
                    "hardFacts": [art.get("summary") or art["headline"]],
                    "entities": art.get("relatedTickers", []),
                    "eventTags": ["general"],
                    "regions": [],
                    "sectors": [],
                    "commodities": [],
                    "technologyThemes": [],
                    "possibleDirectionalPressure": "unclear",
                    "uncertaintyNotes": ["Source data completeness"],
                    "evidence": [art["headline"]]
                }
            
            # Map identifiers and source urls
            event["eventId"] = f"evt_{art_id}"
            event["sourceArticleIds"] = [art_id]
            event["relatedTickers"] = art.get("relatedTickers", [])
            event["sourceUrl"] = art.get("url")
            event["sourceHeadline"] = art.get("headline")
            
            canonical_events.append(event)
            print(f"Mock Extracted Event: {event['eventSummary']} (Type: {event['eventType']})")
            
        return {"canonical_events": canonical_events}

    llm = get_llm_fast()
    
    # System instructions for batch canonical extraction
    system_prompt = """You are an expert financial news analyst. Your task is to analyze a list of news articles and extract a canonical structured event representation for each relevant article.

You must return a valid JSON list of objects matching this schema exactly:
[
  {
    "articleId": "string (the exact articleId of the source article)",
    "eventType": "earnings" | "guidance" | "supply_chain" | "regulatory" | "legal" | "macro" | "geopolitical" | "commodity" | "sector" | "private_company_technology" | "natural_disaster" | "other",
    "eventSummary": "one sentence summarizing the key catalyst event",
    "hardFacts": ["grounded list of facts, numbers, dates, or details mentioned in the text"],
    "entities": ["list of companies, products, routes, places, or platforms involved"],
    "eventTags": ["normalized keywords useful for graph matching (e.g. Taiwan, shipping, semiconductor, model release)"],
    "regions": ["countries or regions affected (e.g. Taiwan, China, Red Sea)"],
    "sectors": ["economic sectors (e.g. technology, airlines, shipping)"],
    "commodities": ["commodities affected (e.g. oil, silicon, microchips)"],
    "technologyThemes": ["specific technology sub-themes if any (e.g. frontier AI, lithography)"],
    "possibleDirectionalPressure": "positive" | "negative" | "mixed" | "unclear",
    "uncertaintyNotes": ["what key uncertainties remain from this article"],
    "evidence": ["verbatim phrases from the article proving the hard facts"]
  }
]

Strict Rules:
1. For each article in the input list, extract the corresponding event structure. If an article is completely irrelevant or noise, you may omit it or map it as eventType "other".
2. Do NOT invent or extrapolate facts. Extract only what is written in the article text.
3. The possibleDirectionalPressure must reflect short-term intraday influence.
4. Do NOT provide buy or sell advice.
5. Output ONLY valid JSON array, do not wrap in markdown or prefix/suffix.
"""

    # Reference time for computing article age
    ref_time = datetime_now()

    def clean_summary(headline: str, summary: str) -> str:
        """Strips Finnhub-style trailing headline repetition from the summary field."""
        if not summary:
            return ""
        # Finnhub often appends the full headline at the end of the summary text.
        # Strip it if the summary ends with the headline (case-insensitive).
        stripped = summary.strip()
        if stripped.lower().endswith(headline.strip().lower()):
            stripped = stripped[: -len(headline.strip())].rstrip(" .,;")
        return stripped

    # Build the input message containing all articles
    user_content = "Analyze the following news articles and return a JSON list of event objects:\n\n"
    for i, art in enumerate(articles):
        headline = art['headline']
        raw_summary = art.get('summary', '')
        summary = clean_summary(headline, raw_summary)
        try:
            from datetime import datetime, timezone
            pub_dt = datetime.fromisoformat(art['publishedAt'].replace('Z', '+00:00')).astimezone(timezone.utc)
            minutes_ago = int((ref_time - pub_dt).total_seconds() / 60)
        except Exception:
            minutes_ago = -1
        age_label = f"{minutes_ago} mins ago" if minutes_ago >= 0 else "unknown age"
        user_content += f"""--- ARTICLE {i+1} ---
ARTICLE ID: {art['articleId']}
SOURCE: {art['sourceName']}
PUBLISHED: {art['publishedAt']} ({age_label})
URL: {art['url']}
HEADLINE: {headline}
SUMMARY: {summary}
RELATED TICKERS IN SOURCE: {', '.join(art.get('relatedTickers', []))}
\n"""

    try:
        print(f"Calling LLM to extract events from {len(articles)} articles in one batch...")
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ])
        cleaned = clean_json_string(response.content)
        extracted_events = json.loads(cleaned)
        
        # Ensure it is a list
        if not isinstance(extracted_events, list):
            # If the LLM returned a single dict, wrap it
            if isinstance(extracted_events, dict):
                extracted_events = [extracted_events]
            else:
                extracted_events = []
                
        # Create map of articles by ID for easy lookup
        art_map = {art["articleId"]: art for art in articles}
        
        for event in extracted_events:
            art_id = event.get("articleId")
            if not art_id and len(articles) == 1:
                # If LLM forgot the articleId but there was only one article, associate it
                art_id = articles[0]["articleId"]
                
            art = art_map.get(art_id)
            if art:
                event["eventId"] = f"evt_{art['articleId']}"
                event["sourceArticleIds"] = [art["articleId"]]
                event["relatedTickers"] = art.get("relatedTickers", [])
                event["sourceUrl"] = art.get("url")
                event["sourceHeadline"] = art.get("headline")
                canonical_events.append(event)
                print(f"Extracted Event: {event['eventSummary']} (Type: {event['eventType']})")
            else:
                print(f"Warning: Extracted event references unknown articleId: {art_id}")
                
    except Exception as e:
        print(f"Error in batch canonical event extraction: {e}")
        # Signal downstream nodes that LLM is unavailable — do NOT silently continue with
        # garbage rule-based events that will pollute the ledger and synthesis.
        print("LLM unavailable in Node 2. Setting llm_failed=True to halt downstream LLM steps.")
        return {"canonical_events": [], "llm_failed": True}
            
    return {"canonical_events": canonical_events, "llm_failed": False}

# 3. Routing Node
def routing_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 3: Candidate Routing] ---")
    iteration = state.get("iteration", 3)
    watchlist = state.get("watchlist", [])
    canonical_events = state.get("canonical_events", [])
    
    routed_candidates = []
    
    for event in canonical_events:
        # A. Direct Routing (Applies to all iterations)
        # Check if the source article was pre-tagged with a watchlist ticker
        for ticker in watchlist:
            if ticker in event.get("relatedTickers", []):
                routed_candidates.append({
                    "candidateId": f"cand_{ticker}_{event['eventId'][:8]}",
                    "ticker": ticker,
                    "relationshipType": "direct",
                    "eventId": event["eventId"],
                    "impactPath": [ticker],
                    "pathConfidence": 1.0,
                    "reasonForRouting": f"Directly tagged in news source for ticker {ticker}."
                })
                print(f"Direct Route: {event['eventSummary']} -> {ticker}")
                
        # B. Cross-Impact Graph Routing (Iteration 3 only)
        if iteration == 3:
            indirect_candidates = route_cross_impact(event, watchlist)
            for ic in indirect_candidates:
                # Avoid duplicates with direct routing
                is_dup = any(c["ticker"] == ic["ticker"] and c["eventId"] == ic["eventId"] for c in routed_candidates)
                if not is_dup:
                    routed_candidates.append(ic)
                    print(f"Cross-Impact Route: {event['eventSummary']} -> {ic['ticker']} via {ic['impactPath']} (Conf: {ic['pathConfidence']})")
                    
    return {"routed_candidates": routed_candidates}

# 4. Ledger Memory Node
def ledger_memory_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 4: Ledger Memory Check] ---")
    iteration = state.get("iteration", 2)
    routed_candidates = state.get("routed_candidates", [])
    canonical_events = {e["eventId"]: e for e in state.get("canonical_events", [])}
    
    filtered_candidates = []
    duplicate_counts = {}
    
    for cand in routed_candidates:
        ticker = cand["ticker"]
        event_id = cand["eventId"]
        event = canonical_events[event_id]
        
        # Iteration 1 skips ledger memory, treating everything as a new briefing
        if iteration == 1:
            cand["ledgerDecision"] = "new"
            cand["newFacts"] = event.get("hardFacts", [])
            cand["catalystId"] = f"cat_{ticker}_{event_id[:8]}"
            filtered_candidates.append(cand)
            continue
            
        # Iterations 2 and 3 use Catalyst Memory
        decision, cat_id, new_facts = check_ledger_decision(ticker, event)
        cand["ledgerDecision"] = decision
        cand["newFacts"] = new_facts
        cand["catalystId"] = cat_id
        
        if decision == "duplicate":
            duplicate_counts[ticker] = duplicate_counts.get(ticker, 0) + 1
            print(f"Memory: Suppressing duplicate event for {ticker}. (Catalyst: {cat_id})")
        else:
            filtered_candidates.append(cand)
            print(f"Memory: Accepted event for {ticker} as {decision.upper()}. (Catalyst: {cat_id})")
            
    return {"routed_candidates": filtered_candidates, "duplicate_counts": duplicate_counts}

# 5. Per-Ticker Synthesis Node
def per_ticker_synthesis_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 5: Per-Ticker Synthesis] ---")
    
    # Halt: if Node 2 signalled LLM failure, skip synthesis entirely
    if state.get("llm_failed", False):
        print("Skipping synthesis: upstream LLM failure detected (llm_failed=True).")
        watchlist = state.get("watchlist", [])
        empty_syntheses = {}
        for ticker in watchlist:
            empty_syntheses[ticker] = {
                "summaryId": f"sum_halted_{ticker}",
                "ticker": ticker,
                "summaryHeadline": "Pipeline halted — LLM unavailable",
                "situationSummary": "The LLM was rate-limited or unavailable during event extraction. No synthesis was produced. Please retry after the quota resets or switch to a paid API tier.",
                "mainCatalysts": [],
                "overallPossibleInfluence": "unclear",
                "confidence": "low",
                "uncertainties": ["LLM quota exhausted."],
                "watchItems": ["Retry after quota reset."],
                "sourceEventIds": [],
                "sourceArticleUrls": [],
                "notFinancialAdvice": True
            }
        return {"ticker_buckets": {}, "ticker_syntheses": empty_syntheses}

    watchlist = state.get("watchlist", [])
    routed_candidates = state.get("routed_candidates", [])
    duplicate_counts = state.get("duplicate_counts", {})
    canonical_events = {e["eventId"]: e for e in state.get("canonical_events", [])}
    
    # 1. Create context buckets per ticker
    ticker_buckets = {}
    for ticker in watchlist:
        ticker_buckets[ticker] = {
            "ticker": ticker,
            "directEvents": [],
            "crossImpactEvents": [],
            "suppressedDuplicateCount": duplicate_counts.get(ticker, 0)
        }
        
    for cand in routed_candidates:
        ticker = cand["ticker"]
        event_id = cand["eventId"]
        event = canonical_events[event_id]
        
        event_entry = {
            "eventId": event_id,
            "eventType": event["eventType"],
            "headline": event.get("sourceHeadline", ""),
            "eventSummary": event["eventSummary"],
            "hardFacts": cand.get("newFacts", event["hardFacts"]),
            "possibleDirectionalPressure": event["possibleDirectionalPressure"],
            "sourceArticleIds": event["sourceArticleIds"],
            "sourceUrl": event.get("sourceUrl", ""),
            "uncertaintyNotes": event.get("uncertaintyNotes", [])
        }
        
        if cand["relationshipType"] == "direct":
            ticker_buckets[ticker]["directEvents"].append(event_entry)
        else:
            event_entry["impactPath"] = cand["impactPath"]
            event_entry["reasonForRouting"] = cand["reasonForRouting"]
            event_entry["pathConfidence"] = cand["pathConfidence"]
            event_entry["pathStrength"] = cand.get("pathStrength", "strong")
            ticker_buckets[ticker]["crossImpactEvents"].append(event_entry)
            
    # 2. Run synthesis via LLM (or mock) for each ticker
    ticker_syntheses = {}
    
    # Check if API Keys are set
    from backend.config import GEMINI_API_KEY, OPENAI_API_KEY
    use_mock = not (GEMINI_API_KEY or OPENAI_API_KEY)
    
    if use_mock:
        print("No LLM API keys found. Falling back to rules-based mock synthesis.")
        for ticker, bucket in ticker_buckets.items():
            if not bucket["directEvents"] and not bucket["crossImpactEvents"]:
                metadata = state.get("ingestion_metadata", {})
                total = metadata.get("total_ingested", 0)
                passed = metadata.get("passed_freshness", 0)
                if total > 0 and passed == 0:
                    situation_summary = f"Ingested {total} articles today, but 0 passed the freshness filter (none were published within the last {FRESHNESS_LOOKBACK_MINUTES} minutes). They were filtered out as older news."
                else:
                    situation_summary = f"No new catalysts were detected in the latest freshness window ({FRESHNESS_LOOKBACK_MINUTES} mins)."
                    
                ticker_syntheses[ticker] = {
                    "summaryId": f"sum_{ticker}_{int(datetime_now().timestamp())}",
                    "ticker": ticker,
                    "summaryHeadline": "No new catalysts detected",
                    "situationSummary": situation_summary,
                    "mainCatalysts": [],
                    "overallPossibleInfluence": "unclear",
                    "confidence": "low",
                    "uncertainties": ["No active events to assess."],
                    "watchItems": ["Continue monitoring watchlist."],
                    "sourceEventIds": [],
                    "sourceArticleUrls": [],
                    "notFinancialAdvice": True
                }
                continue
                
            print(f"Mock Synthesizing catalyst briefing for ticker: {ticker}")
            
            # Determine overall influence
            all_events = bucket["directEvents"] + bucket["crossImpactEvents"]
            pressures = [e["possibleDirectionalPressure"] for e in all_events]
            if "negative" in pressures and "positive" in pressures:
                overall_influence = "mixed"
            elif "negative" in pressures:
                overall_influence = "negative"
            elif "positive" in pressures:
                overall_influence = "positive"
            else:
                overall_influence = "mixed"
                
            # Build headlines and summaries
            direct_summaries = [e["eventSummary"] for e in bucket["directEvents"]]
            cross_summaries = [f"{e['eventSummary']} (routed via {' -> '.join(e['impactPath'])})" for e in bucket["crossImpactEvents"]]
            
            headline = f"Catalyst update for {ticker}: "
            if direct_summaries and cross_summaries:
                headline += "Direct corporate and indirect exposure events active"
            elif direct_summaries:
                headline += "Direct announcements detected"
            else:
                headline += "Indirect cross-impact exposure pathways detected"
                
            situation_summary = f"In the latest monitoring window, {ticker} has active catalysts. "
            if direct_summaries:
                situation_summary += f"Direct corporate events: {'. '.join(direct_summaries)}. "
            if cross_summaries:
                situation_summary += f"Indirect cross-impact events routed through the exposure graph: {'. '.join(cross_summaries)}."
                
            # Catalysts list
            main_catalysts = []
            for de in bucket["directEvents"]:
                main_catalysts.append({
                    "label": de["eventSummary"],
                    "relationshipType": "direct",
                    "eventType": de["eventType"],
                    "possibleInfluence": de["possibleDirectionalPressure"],
                    "confidence": "high"
                })
            for ce in bucket["crossImpactEvents"]:
                main_catalysts.append({
                    "label": ce["eventSummary"],
                    "relationshipType": "indirect",
                    "eventType": ce["eventType"],
                    "possibleInfluence": ce["possibleDirectionalPressure"],
                    "confidence": "tentative",
                    "impactPath": ce["impactPath"]
                })
                
            # Gather uncertainties
            uncertainties = []
            for e in all_events:
                uncertainties.extend(e.get("uncertaintyNotes", []))
            if not uncertainties:
                uncertainties = ["General macroeconomic conditions and market volatility."]
            else:
                # Deduplicate
                uncertainties = list(set(uncertainties))
                
            # Gather source URLs and IDs
            src_ids = [e["eventId"] for e in all_events]
            src_urls = list(set([e["sourceUrl"] for e in all_events if e.get("sourceUrl")]))
            
            ticker_syntheses[ticker] = {
                "summaryId": f"sum_{ticker}_{int(datetime_now().timestamp())}",
                "ticker": ticker,
                "summaryHeadline": headline,
                "situationSummary": situation_summary,
                "mainCatalysts": main_catalysts,
                "overallPossibleInfluence": overall_influence,
                "confidence": "tentative",
                "uncertainties": uncertainties[:4], # Limit to 4 items
                "watchItems": [
                    f"{ticker} price and volume action",
                    f"Follow-up updates from related entities and supply partners"
                ],
                "sourceEventIds": src_ids,
                "sourceArticleUrls": src_urls,
                "notFinancialAdvice": True,
                "complianceDisclaimer": "This is an informational briefing, not financial advice. The impact assessment is tentative and may be incomplete. Verify with market data and official sources before making decisions."
            }
        return {"ticker_buckets": ticker_buckets, "ticker_syntheses": ticker_syntheses}

    llm = get_llm()
    
    synthesis_system_prompt = """You are a professional financial synthesis analyst supporting a discretionary intraday trader. 
Your task is to review the direct and indirect catalyst events for a specific watched ticker and write a market-impact synthesis.

Each event in the context includes a "minutesAgo" field indicating how many minutes ago it was published relative to now.
RECENCY RULE: Weight events published more recently (lower minutesAgo) more heavily in your assessment.
For intraday trading, events < 30 minutes old are HIGH priority. Events 30-90 minutes old are MEDIUM priority.
Events > 90 minutes old are BACKGROUND context — still relevant but should not dominate the headline.

You must output a JSON object matching this schema exactly:
{
  "summaryHeadline": "one concise headline summarizing the net catalyst situation",
  "situationSummary": "paragraph explanation of what has happened, referencing direct and indirect paths, and explicitly noting which catalysts are breaking vs. background",
  "mainCatalysts": [
    {
      "label": "short catalyst title",
      "relationshipType": "direct" | "indirect",
      "eventType": "event type string",
      "possibleInfluence": "positive" | "negative" | "mixed" | "unclear",
      "confidence": "low" | "medium" | "high" | "tentative",
      "recency": "breaking" | "recent" | "background",
      "impactPath": ["list", "of", "nodes"]
    }
  ],
  "overallPossibleInfluence": "positive" | "negative" | "mixed" | "unclear",
  "confidence": "low" | "medium" | "high" | "tentative",
  "uncertainties": ["specific uncertainties or unknowns for the trader to monitor"],
  "watchItems": ["specific ticker signals, announcements, or price markers to watch next"]
}

Cross-impact path strength:
Each cross-impact event includes a "pathStrength" field indicating routing confidence:
- "strong" (pathConfidence >= 0.70): The exposure path is well-supported. Include this event in mainCatalysts.
- "weak" (pathConfidence 0.45–0.69): The exposure path is marginal. Do NOT include in mainCatalysts.
  Instead, reference it only in watchItems or uncertainties (e.g., "Watch for confirmation of [event] impact via [path]").

Strict Rules:
1. ONLY utilize the facts provided in the prompt context. Do NOT invent companies, news, or metrics.
2. If there are no new events in the direct or cross-impact arrays, output the following:
   - summaryHeadline: "No new catalysts detected"
   - situationSummary: "No new catalysts were detected in the latest freshness window."
   - overallPossibleInfluence: "unclear"
   - confidence: "low"
   - mainCatalysts: []
3. Use tentative, risk-aware language. Never state market movements as guarantees. Use terms like "possible pressure", "potential risk", "tentative impact".
4. Do NOT give investment or trading advice. Do NOT write "buy", "sell", "we recommend shorting".
5. Output ONLY valid JSON without markdown wrapping.
"""

    ref_time = datetime_now()

    def annotate_event_recency(event: Dict[str, Any]) -> Dict[str, Any]:
        """Adds minutesAgo field to an event dict for the synthesis prompt."""
        try:
            from datetime import datetime, timezone
            # sourceHeadline events don't carry publishedAt — skip gracefully
            pub_raw = event.get("publishedAt", "")
            if pub_raw:
                pub_dt = datetime.fromisoformat(pub_raw.replace('Z', '+00:00')).astimezone(timezone.utc)
                event["minutesAgo"] = int((ref_time - pub_dt).total_seconds() / 60)
        except Exception:
            event["minutesAgo"] = -1
        return event

    for ticker, bucket in ticker_buckets.items():
        # Check if anything happened for this ticker
        if not bucket["directEvents"] and not bucket["crossImpactEvents"]:
            metadata = state.get("ingestion_metadata", {})
            total = metadata.get("total_ingested", 0)
            passed = metadata.get("passed_freshness", 0)
            if total > 0 and passed == 0:
                situation_summary = f"Ingested {total} articles today, but 0 passed the freshness filter (none were published within the last {FRESHNESS_LOOKBACK_MINUTES} minutes). They were filtered out as older news."
            else:
                situation_summary = f"No new catalysts were detected in the latest freshness window ({FRESHNESS_LOOKBACK_MINUTES} mins)."

            ticker_syntheses[ticker] = {
                "summaryId": f"sum_{ticker}_{int(datetime_now().timestamp())}",
                "ticker": ticker,
                "summaryHeadline": "No new catalysts detected",
                "situationSummary": situation_summary,
                "mainCatalysts": [],
                "overallPossibleInfluence": "unclear",
                "confidence": "low",
                "uncertainties": ["No active events to assess."],
                "watchItems": ["Continue monitoring watchlist."],
                "sourceEventIds": [],
                "sourceArticleUrls": [],
                "notFinancialAdvice": True
            }
            continue

        # Annotate each event with its recency in minutes before sending to LLM
        annotated_bucket = dict(bucket)
        annotated_bucket["directEvents"] = [annotate_event_recency(dict(e)) for e in bucket["directEvents"]]
        annotated_bucket["crossImpactEvents"] = [annotate_event_recency(dict(e)) for e in bucket["crossImpactEvents"]]
            
        print(f"Synthesizing catalyst briefing for ticker: {ticker}")
        context_str = json.dumps(annotated_bucket, indent=2)
        user_prompt = f"TICKER CONFIG: {ticker}\nCONTEXT BUCKET:\n{context_str}"
        
        try:
            response = llm.invoke([
                SystemMessage(content=synthesis_system_prompt),
                HumanMessage(content=user_prompt)
            ])
            cleaned = clean_json_string(response.content)
            synthesis = json.loads(cleaned)
            
            # Map additional metadata
            synthesis["summaryId"] = f"sum_{ticker}_{int(datetime_now().timestamp())}"
            synthesis["ticker"] = ticker
            
            # Extract source IDs
            src_ids = []
            src_urls = []
            for de in bucket["directEvents"]:
                src_ids.append(de["eventId"])
                if de.get("sourceUrl"):
                    src_urls.append(de["sourceUrl"])
            for ce in bucket["crossImpactEvents"]:
                src_ids.append(ce["eventId"])
                if ce.get("sourceUrl"):
                    src_urls.append(ce["sourceUrl"])
            
            synthesis["sourceEventIds"] = src_ids
            synthesis["sourceArticleUrls"] = list(set(src_urls))
            synthesis["notFinancialAdvice"] = True
            
            # Ensure compliance disclaimer is present
            synthesis["complianceDisclaimer"] = "This is an informational briefing, not financial advice. The impact assessment is tentative and may be incomplete. Verify with market data and official sources before making decisions."
            
            ticker_syntheses[ticker] = synthesis
        except Exception as e:
            print(f"Error synthesizing briefing for {ticker}: {e}")
            ticker_syntheses[ticker] = {
                "summaryId": f"sum_error_{ticker}",
                "ticker": ticker,
                "summaryHeadline": "Error in catalyst synthesis",
                "situationSummary": f"A processing error occurred during LLM briefing synthesis: {str(e)}",
                "mainCatalysts": [],
                "overallPossibleInfluence": "unclear",
                "confidence": "low",
                "uncertainties": ["System processing error."],
                "watchItems": [],
                "sourceEventIds": [],
                "sourceArticleUrls": [],
                "notFinancialAdvice": True
            }
            
    return {"ticker_buckets": ticker_buckets, "ticker_syntheses": ticker_syntheses}

# Helper to capture timestamp for ID generation
def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)

# 6. Compliance Gate Node
def compliance_gate_node(state: WorkflowState) -> Dict[str, Any]:
    print("--- [Node 6: Compliance Gate Check] ---")
    ticker_syntheses = state.get("ticker_syntheses", {})
    
    # Simple rule-based compliance cleaner to ensure no buy/sell recommendations slip through
    forbidden_patterns = [
        (r'\bbuy\b', 'monitor'),
        (r'\bsell\b', 'assess'),
        (r'\bshould short\b', 'may face downward sentiment pressure'),
        (r'\binvest in\b', 'watch exposure to'),
        (r'\bwe recommend\b', 'it may be useful to')
    ]
    
    cleaned_syntheses = {}
    for ticker, syn in ticker_syntheses.items():
        syn_copy = copy_dict(syn)
        
        # Run compliance check on text fields
        headline = syn_copy.get("summaryHeadline", "")
        summary = syn_copy.get("situationSummary", "")
        
        for pattern, replacement in forbidden_patterns:
            headline = re.sub(pattern, replacement, headline, flags=re.IGNORECASE)
            summary = re.sub(pattern, replacement, summary, flags=re.IGNORECASE)
            
        syn_copy["summaryHeadline"] = headline
        syn_copy["situationSummary"] = summary
        
        # Enforce the flag
        syn_copy["notFinancialAdvice"] = True
        cleaned_syntheses[ticker] = syn_copy
        
    return {"ticker_syntheses": cleaned_syntheses}

def copy_dict(d):
    # Shallow copy for simplicity
    return {k: v for k, v in d.items()}

# Construct LangGraph Workflow
def build_workflow_graph() -> StateGraph:
    workflow = StateGraph(WorkflowState)
    
    # Add Nodes
    workflow.add_node("fetch_and_filter", fetch_and_filter_node)
    workflow.add_node("extract_events", canonical_event_extraction_node)
    workflow.add_node("route_events", routing_node)
    workflow.add_node("check_ledger", ledger_memory_node)
    workflow.add_node("synthesize_ticker_briefings", per_ticker_synthesis_node)
    workflow.add_node("compliance_gate", compliance_gate_node)
    
    # Define Edges / Transitions
    workflow.set_entry_point("fetch_and_filter")
    workflow.add_edge("fetch_and_filter", "extract_events")
    workflow.add_edge("extract_events", "route_events")
    workflow.add_edge("route_events", "check_ledger")
    workflow.add_edge("check_ledger", "synthesize_ticker_briefings")
    workflow.add_edge("synthesize_ticker_briefings", "compliance_gate")
    workflow.add_edge("compliance_gate", END)
    
    return workflow.compile()
