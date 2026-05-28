import json
import re
from typing import TypedDict, List, Dict, Any, Tuple
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from backend.config import get_llm
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
        
    articles = get_news_payload(
        symbol_watchlist=watchlist,
        cross_impact_keywords=cross_impact_keywords,
        scenario_id=scenario_id,
        simulated_now_str=simulated_now
    )
    
    return {"articles": articles}

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

    llm = get_llm()
    
    # System instructions for canonical extraction
    system_prompt = """You are an expert financial news analyst. Your task is to extract a canonical structured event representation from a news article. 

You must return a valid JSON object matching this schema exactly:
{
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

Strict Rules:
1. Do NOT invent or extrapolate facts. Extract only what is written in the article text.
2. The possibleDirectionalPressure must reflect short-term intraday influence (e.g. positive for guidance beats, negative for factory fires).
3. Do NOT provide buy or sell advice. Do NOT recommend entering or exiting any trade.
4. Output ONLY valid JSON, do not wrap in markdown or prefix/suffix.
"""

    for art in articles:
        user_content = f"""SOURCE: {art['sourceName']}
TIMESTAMP: {art['publishedAt']}
URL: {art['url']}
HEADLINE: {art['headline']}
SUMMARY: {art.get('summary', '')}
RELATED TICKERS IN SOURCE: {', '.join(art.get('relatedTickers', []))}"""

        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            cleaned = clean_json_string(response.content)
            event = json.loads(cleaned)
            
            # Map source article ID and related tickers
            event["eventId"] = f"evt_{art['articleId']}"
            event["sourceArticleIds"] = [art["articleId"]]
            event["relatedTickers"] = art.get("relatedTickers", [])
            event["sourceUrl"] = art.get("url")
            event["sourceHeadline"] = art.get("headline")
            
            canonical_events.append(event)
            print(f"Extracted Event: {event['eventSummary']} (Type: {event['eventType']})")
        except Exception as e:
            print(f"Error extracting canonical event for {art['articleId']}: {e}")
            
    return {"canonical_events": canonical_events}

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
                ticker_syntheses[ticker] = {
                    "summaryId": f"sum_{ticker}_{int(datetime_now().timestamp())}",
                    "ticker": ticker,
                    "summaryHeadline": "No new catalysts detected",
                    "situationSummary": "No new catalysts were detected in the latest freshness window.",
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

You must output a JSON object matching this schema exactly:
{
  "summaryHeadline": "one concise headline summarizing the net catalyst situation",
  "situationSummary": "paragraph explanation of what has happened, referencing direct and indirect paths",
  "mainCatalysts": [
    {
      "label": "short catalyst title",
      "relationshipType": "direct" | "indirect",
      "eventType": "event type string",
      "possibleInfluence": "positive" | "negative" | "mixed" | "unclear",
      "confidence": "low" | "medium" | "high" | "tentative",
      "impactPath": ["list", "of", "nodes"]
    }
  ],
  "overallPossibleInfluence": "positive" | "negative" | "mixed" | "unclear",
  "confidence": "low" | "medium" | "high" | "tentative",
  "uncertainties": ["specific uncertainties or unknowns for the trader to monitor"],
  "watchItems": ["specific ticker signals, announcements, or price markers to watch next"]
}

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

    for ticker, bucket in ticker_buckets.items():
        # Check if anything happened for this ticker
        if not bucket["directEvents"] and not bucket["crossImpactEvents"]:
            ticker_syntheses[ticker] = {
                "summaryId": f"sum_{ticker}_{int(datetime_now().timestamp())}",
                "ticker": ticker,
                "summaryHeadline": "No new catalysts detected",
                "situationSummary": "No new catalysts were detected in the latest freshness window.",
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
            
        print(f"Synthesizing catalyst briefing for ticker: {ticker}")
        context_str = json.dumps(bucket, indent=2)
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
