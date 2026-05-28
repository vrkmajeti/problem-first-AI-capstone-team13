# Capstone System Design: Intraday Cross-Impact Catalyst Briefings

## 0. Executive thesis

The system helps discretionary intraday traders monitor market-moving information without drowning in duplicate articles or missing external events that can affect watched stocks indirectly.

The product is **not a generic news summarizer** and not a buy/sell signal engine. It is a controlled AI workflow that turns direct company news and exposure-relevant external news into **deduplicated catalyst briefings**.

Each briefing explains:

1. what happened,
2. which watched ticker may be affected,
3. whether the relationship is direct or indirect,
4. the causal path from event to ticker,
5. how the event could tentatively influence the stock,
6. what uncertainty remains,
7. what follow-up signals the trader should watch.

The core thesis:

> Ticker-tagged news is not enough. Markets move through relationships: competitors, private companies, AI platforms, suppliers, regions, commodities, shipping routes, sanctions, wars, and macro shocks. The system must reason over catalysts and exposure paths, not isolated articles.

The architecture deliberately stays workflow-based. The financial domain is high-stakes, latency-sensitive, and compliance-sensitive. Autonomous agents and multi-agent systems add planning loops, unpredictable costs, harder debugging, and weaker observability. This project therefore uses LLMs only where language understanding is needed, and deterministic code where control matters.

```text
Direct company news + exposure-aware broad news
→ source and quality filters
→ batch canonical event extraction (single LLM call)
→ direct ticker routing or exposure-graph routing
→ catalyst ledger
→ ticker-specific context buckets
→ per-ticker market-impact synthesis
→ observability traces + eval scores
```

The three iterations are:

| Iteration | Capability | Architectural lesson |
|---|---|---|
| 1 | Direct per-ticker synthesis from company news | Start with ticker-tagged company news and one final synthesis per watched ticker |
| 2 | Catalyst memory before synthesis | Track stories as catalysts, not articles, so ticker synthesis is not polluted by duplicates |
| 3 | External cross-impact routing into ticker buckets | Detect untickered external events through an exposure graph and include them only in the affected ticker's synthesis |

The main capstone argument:

> Use LLMs for language normalization and explanation. Use deterministic code for API access, routing, graph traversal, memory, deduplication, compliance checks, and latency-critical decisions.

---

# 1. Scoping the project

## 1.1 Real-world problem

Discretionary intraday traders follow several stocks during the trading day. They need to understand quickly whether new information may affect one of their watched tickers.

Existing news alerts create four problems:

1. **Duplicate spam:** several outlets repeat the same catalyst.
2. **Article-level thinking:** every article is treated as a new event, even when it belongs to the same developing story.
3. **Ticker-only blindness:** war, sanctions, AI model launches, commodity shocks, shipping disruptions, supplier issues, private-company news, and sector events may affect a stock even when the article does not mention the ticker.
4. **Weak explanation:** alerts often say that something happened, but not why it may matter for the watched stock.

This system produces **catalyst briefings** instead of raw alerts. A briefing is a compact card plus a short market-impact explanation.

## 1.2 Target user

The target user is a **discretionary intraday trader**.

This means:

```text
manual decision-making,
short-horizon monitoring,
watchlist-based relevance,
not high-frequency trading,
not automated execution,
not buy/sell recommendations.
```

The system is not designed to beat professional terminals by milliseconds. The prototype target is a practical **5-10 minute monitoring loop**. The value is faster filtering, deduplication, and explanation than manual scanning.

## 1.3 Freshness and ingestion policy

Freshness is a core product requirement, not an implementation detail. The system is built for intraday use, so it should process only very recent news by default.

In the capstone demo, the user clicks a UI action such as **Fetch latest catalysts**. That manual action triggers live API requests and processes only articles from the latest freshness window.

The freshness window is controlled by the `FRESHNESS_LOOKBACK_MINUTES` environment variable:

```text
production target: 5-10 minutes
capstone live demo: 120 minutes (configurable)
reason for wider demo window: live API coverage is uneven; a wider window ensures
  enough articles reach the LLM steps for a meaningful capstone demonstration.
reason for production narrowness: minimise duplicate re-processing and keep
  the briefing focused on genuinely breaking news.
```

The lookback window affects how many articles enter the batch extraction step. A wider window means more articles per LLM call, which consumes more quota. The workflow is designed to degrade gracefully when the LLM is rate-limited rather than pollute the ledger with garbage (see §9.3 workflow fault behaviour).

In production, the same logic would be scheduled automatically every 5 minutes. The difference is orchestration only:

```text
Capstone demo: manual UI-triggered pull, wider freshness window
Production: automatic 5-minute polling loop, narrow freshness window
Core pipeline: identical in both modes
```

This freshness constraint is also the reason the system needs memory. Because every pull overlaps with the previous few minutes, the system will repeatedly see the same article, syndicated copies, and follow-up articles about the same catalyst. The catalyst ledger prevents repeated briefings and decides whether an incoming article is:

```text
new catalyst → emit new briefing
duplicate of known catalyst → suppress
meaningful update to known catalyst → emit update briefing
```

The golden dataset is separate from the capstone live input. It is used to design prompts, tune schemas, calibrate judges, and define expected behavior. It is not the same thing as the data processed by the live manual pull in the capstone demo.

## 1.4 Why generative AI is a good fit

Generative AI is useful because financial, technology, and geopolitical news is unstructured language. The model can normalize messy text into structured event fields and explain plausible causal mechanisms.

However, the LLM is not trusted to freely invent impact chains. The design separates responsibilities:

| Responsibility | Component | Reason |
|---|---|---|
| News fetching | API clients + manual UI trigger / scheduler | Predictable and auditable |
| Source and timestamp filters | Code | Objective rules |
| Exposure query generation | Code from graph | Keeps broad-news search bounded |
| Batch canonical event extraction | LLM | Batch-processes all articles in one call to minimize token overhead |
| Direct ticker routing | Code | Based on source tags and watchlist |
| Indirect impact routing | Exposure graph + code | Avoids vague LLM over-connection |
| Duplicate/update decision | Catalyst ledger + code | Needs determinism and evalability |
| Per-ticker synthesis | LLM | Produces the final market-impact analysis for each watched ticker from accepted events only |
| Compliance checks | Code + offline LLM judge | Reduce advice and hallucination risk |

## 1.5 Business and technical constraints

The capstone must be feasible on free or low-cost tooling, so the system is **manual-pull-first** and **source-light**.

The capstone demo does not require automatic polling. Instead, the user manually triggers a fresh API pull from the UI. The production upgrade path is to run the same pull logic automatically every 5 minutes.

Key constraints:

```text
limited API budgets,
limited build time,
no licensed real-time market data,
no automated trading,
no universal geopolitical reasoning,
no claim of financial advice,
need for auditable decisions,
need to avoid integrating many fragile niche APIs.
```

---

# 2. Data source strategy

## 2.1 Final source decision

The system uses **two primary API layers** plus a local exposure graph.

| Layer | Source | Used for | Iteration |
|---|---|---|---|
| Direct company-news layer | Finnhub company-news | Direct ticker/company catalysts by symbol and date | 1, 2 |
| Peer expansion layer | Finnhub company-peers | Public-company peers/competitors used to enrich the exposure graph and query plan | 3 support |
| Broad external-news discovery layer | Currents API search/latest-news | War, sanctions, AI/private-company news, disasters, shipping disruptions, export controls, commodity-related articles | 3 |
| Relationship layer | Local exposure graph | Decides whether external news has a valid path to watched tickers | 3 |
| Optional eval/replay backup | NewsAPI / Guardian / NewsData.io | Historical examples if source coverage is insufficient | offline only |

This avoids the unsustainable version of the project where every event class gets a separate API.

Both API layers are used with the same freshness rule in the capstone demo:

```text
manual UI-triggered pull
→ fetch latest available API results
→ local filter to last 5 minutes
→ max 10-minute lookback buffer
→ exact dedup
→ catalyst ledger memory check
```

The final principle is:

> Finnhub finds direct ticker news. Currents discovers broad external articles. The exposure graph decides whether those articles matter to watched tickers.

## 2.1.1 API usage by iteration

| Iteration | API/source used | Purpose | Runtime freshness rule | Storage rule |
|---|---|---|---|---|
| 1. Direct catalyst briefings | Finnhub company-news | Fetch direct company articles for watched tickers | Manual UI pull, local filter to last 5 minutes, max 10-minute lookback | Store only final per-ticker summary + ledger update; article/event payloads are transient/traced |
| 2. Catalyst memory | Finnhub company-news + catalyst ledger | Detect whether a fresh article is new, duplicate, or a meaningful update | Same 5-minute pull with 10-minute overlap | Store ledger entries and final per-ticker summaries only |
| 3. Cross-impact routing | Currents search/latest-news + exposure graph | Fetch external articles using graph-expanded query terms, then validate paths to watched tickers | Manual UI pull, local filter to last 5 minutes, max 10-minute lookback | Store only accepted graph, ledger entries, and final per-ticker summaries |
| Graph setup support | Finnhub company-peers + setup-time LLM enrichment | Propose peers, competitors, dependencies, regions, private companies, themes, and query terms when a ticker is added | Not part of runtime pull | Store only accepted graph nodes/edges/query terms |


## 2.2 Why Finnhub for Iteration 1 and 2

Finnhub is used for direct company news because its API includes a company-news endpoint that lists company news by symbol and date. That fits the watchlist workflow:

```text
watched ticker → Finnhub company-news(symbol, from, to) → direct catalyst candidates
```

Use Finnhub for:

```text
company-specific articles,
direct ticker catalysts,
Iteration 1 catalyst briefings,
Iteration 2 duplicate/update/new memory tests,
manual UI-triggered direct-news pulls for the live capstone flow.
```

Implementation notes:

```text
Endpoint: /company-news
Inputs: symbol, from, to
Mode for capstone: manual UI-triggered pull for today per ticker, then local filter to the last 5 minutes with a maximum 10-minute lookback buffer
Storage: no permanent raw article storage; raw and normalized payloads are transient or sent to observability traces
```

Finnhub should **not** be treated as the only source because it mainly solves the direct ticker-news problem. It does not reliably capture untickered external events like “Anthropic releases a frontier model” or “war escalation near a shipping route.”

## 2.3 How Finnhub company-peers is used

Finnhub also provides a **company-peers** endpoint. This is useful, but it must be used narrowly.

Use it for:

```text
peer and competitor expansion,
public-company adjacency,
watchlist query enrichment,
exposure graph suggestions for peer/sector relationships.
```

Do **not** use it for:

```text
supplier relationships,
customer relationships,
private-company dependencies,
regional production exposure,
shipping-route exposure,
commodity exposure.
```

Example:

```text
User watches AAPL.
Finnhub company-peers may suggest public-company peers/adjacent companies.
The exposure graph may add peer/competitive edges where defensible.
But TSMC is not discovered as an Apple supply-chain dependency from company-peers.
TSMC must be stored in the manually seeded exposure graph as supplier/customer or production exposure.
```

Implementation notes:

```text
Endpoint: /stock/peers or company-peers depending on SDK/documentation naming
Input: symbol
Mode for capstone: optional enrichment step when building or refreshing the exposure graph, not a runtime requirement for every manual pull
Storage: store only accepted peer edges in the exposure graph; do not permanently store the whole raw peer API response
```

This keeps the relationship layer controlled. Finnhub peers can suggest competitor/peer edges, but the graph remains the source of truth. A peer returned by the API is not automatically a valid cross-impact path until it is accepted into the graph with an edge type, confidence, and notes.

Finnhub company-peers can be paired with a setup-time LLM enrichment run. The peer API proposes public competitors or adjacent public companies; the LLM proposes broader exposure relationships such as suppliers, regions, private companies, technology themes, commodities, and search terms. Only accepted proposals are stored in the exposure graph.

## 2.4 Why Currents for Iteration 3

Currents is used as the broad external-news discovery API because it supports real-time/global news search and latest-news retrieval with filters such as keywords, language, country, category, and date ranges.

Use Currents for:

```text
war/conflict headlines,
sanctions,
shipping disruption,
private-company technology news,
AI model releases,
export controls,
commodity or energy shocks,
floods/disasters when they appear in mainstream coverage,
untickered external events that may affect watched stocks indirectly.
```

Important limitation:

> Currents is a broad news API, not a structured conflict or disaster-event API. It can discover war/disaster/technology articles, but the system must still extract event meaning and route through the exposure graph.

Implementation notes:

```text
Endpoint: /search for targeted exposure queries
Endpoint: /latest-news for category/country/language scans if needed
Inputs: keywords, language, country, category, start_date, end_date
Mode for capstone: manual UI-triggered targeted exposure-aware queries, then local filter to the last 5 minutes with a maximum 10-minute lookback buffer
Storage: no permanent raw article storage; raw and normalized payloads are transient or sent to observability traces
```

## 2.5 Why not GDELT, Marketaux, or many niche event APIs

Rejected as main source:

| Source | Reason |
|---|---|
| GDELT | Too broad and noisy. It turns the capstone into global-news filtering. |
| Marketaux | Too finance/market-news oriented and free tier is too limited for this use case. |
| GDACS / USGS / EONET / ReliefWeb / ACLED bundle | Technically relevant for some events, but too many integrations for the capstone. They fragment the architecture. |
| Company blogs/RSS bundle | Useful for Anthropic/OpenAI-style examples, but too fragmented as the main source. |
| Alpha Vantage | Not suitable as the main path because multi-ticker search is not watchlist-style and free-tier limits make rapid dataset construction harder. |

The capstone should not pretend there is a perfect free live source for every possible external event. The credible version is:

```text
Use one broad API for external article discovery.
Use an exposure graph to keep the search bounded.
Use replay examples where live coverage is insufficient.
```

## 2.6 How API usage changes by iteration

| Iteration | API usage | Purpose |
|---|---|---|
| 1 | Finnhub company-news only | Direct ticker/company catalyst briefings |
| 2 | Finnhub company-news only | Duplicate/update/new catalyst memory over repeated company articles |
| 3 | Finnhub company-news + optional Finnhub company-peers + Currents | Direct company catalysts, peer expansion, and untickered external events routed through the exposure graph |

---

# 3. Exposure graph design

## 3.1 What the exposure graph does

The exposure graph is the control layer for indirect reasoning.

It answers:

> If an external article does not mention a watched ticker, is there still a concrete, pre-approved path from the event to that ticker?

The graph does **not** predict the market. It only proposes plausible exposure paths. The LLM then explains the path with uncertainty.

Core rule:

> No graph path, no cross-impact briefing.

This is the main anti-hallucination guardrail for butterfly-effect reasoning.

## 3.2 How the graph is built for the capstone

For the capstone, the graph should be **manual-seeded and watchlist-specific**, not automatically generated from the entire web.

Build it in four steps:

### Step 1: Choose a small watchlist

Use 5-8 public tickers that make the cross-impact problem visible.

Example:

```text
NVDA, MSFT, GOOGL, AMZN, AAPL, TSM, LMT, DAL
```

### Step 2: Add direct company and ticker nodes

For each ticker:

```text
ticker node,
public company node,
sector node,
technology/theme nodes,
region nodes,
commodity/risk nodes where relevant.
```

Example:

```text
NVDA → Nvidia
Nvidia → semiconductors
Nvidia → frontier_ai_infrastructure
Nvidia → Taiwan semiconductor manufacturing exposure
```

### Step 3: Expand watched tickers into dependency and peer nodes

This is the step that makes cross-impact detection work.

The user watchlist stays small:

```text
AAPL
```

The system expands it internally through the exposure graph:

```text
AAPL → Apple
Apple → iPhone supply chain
Apple → TSMC
Apple → Foxconn
Apple → China manufacturing exposure
Apple → Taiwan semiconductor exposure
Apple → public peers / competitors where useful
```

There are two kinds of expansion:

| Expansion type | Example | How it is built | Used for |
|---|---|---|---|
| Dependency expansion | TSMC, Foxconn, Taiwan semiconductor exposure | Manually seeded graph edges | Supply-chain, production, regional, commodity, shipping, sanctions events |
| Peer expansion | public competitors or adjacent companies | Finnhub company-peers suggestions, then manually accepted into graph | Competitor/sector sentiment and public-peer news |

Important rule:

> Peer expansion is not supply-chain expansion. Finnhub company-peers can help identify public competitors or adjacent companies, but supplier/customer dependencies such as TSMC → Apple must come from the exposure graph. For the capstone, those dependency edges can be **LLM-assisted at setup time**, then reviewed or accepted into the stored graph before runtime.

### Step 4: Setup-time LLM exposure enrichment

When a ticker is added to the watchlist, the system may run a setup-time enrichment workflow. This is not part of the 5-minute runtime news-processing loop. Its purpose is to propose exposure graph nodes, edges, and query terms that make indirect news discoverable.

Example for `AAPL`:

```text
User adds AAPL
→ fetch Finnhub company profile / company-news metadata where useful
→ fetch Finnhub company-peers for public peer suggestions
→ run LLM exposure-enrichment prompt
→ LLM proposes suppliers, manufacturing partners, private companies, regions, commodities, technology themes, and query terms
→ user/developer accepts or edits proposed edges
→ accepted edges are stored in the exposure graph
```

The LLM is allowed to propose:

```text
supplier or manufacturing exposure: TSMC, Foxconn
regional exposure: Taiwan, China manufacturing
technology themes: semiconductor supply chain, AI platform competition
private companies: Anthropic, OpenAI, SpaceX, Stripe
commodities and routes: oil, lithium, Red Sea shipping
query terms: Taiwan semiconductor, TSMC disruption, Foxconn China production
```

The LLM is **not** allowed to directly decide that a live article affects a watched stock. Runtime impact routing uses only stored graph edges.

Setup-time enrichment output should be structured:

```json
{
  "ticker": "AAPL",
  "proposed_nodes": [
    { "id": "TSMC", "type": "public_company", "label": "Taiwan Semiconductor Manufacturing Company" },
    { "id": "Foxconn", "type": "company", "label": "Foxconn" },
    { "id": "Taiwan", "type": "region", "label": "Taiwan" },
    { "id": "semiconductor_supply_chain", "type": "theme", "label": "Semiconductor supply chain" }
  ],
  "proposed_edges": [
    {
      "from": "TSMC",
      "to": "AAPL",
      "type": "supplier_customer_exposure",
      "confidence": "high",
      "rationale": "Apple depends on TSMC for advanced chip manufacturing."
    },
    {
      "from": "Taiwan",
      "to": "TSMC",
      "type": "regional_exposure",
      "confidence": "high",
      "rationale": "TSMC has major semiconductor manufacturing exposure in Taiwan."
    }
  ],
  "query_terms": [
    "TSMC",
    "Taiwan semiconductor",
    "Foxconn",
    "China iPhone production",
    "chip export controls"
  ],
  "requires_review": true
}
```

This keeps the graph scalable without turning runtime into autonomous research. The graph can be built once, reviewed, stored, and reused for every later 5-minute manual pull.

### Step 5: Add only high-confidence edges

Do not try to encode every possible market relationship.

Add only relationships that are clear enough to defend in a presentation:

```text
company belongs to sector,
company has exposure to a technology theme,
private company competes in same technology theme,
region is relevant to production/supply chain,
commodity affects sector cost structure,
shipping route affects logistics-sensitive sectors,
sanctions/export controls affect a sector or product category.
```

### Step 6: Store each edge with confidence and source type

Every edge should include:

```text
edge_type,
strength,
confidence,
source_type,
notes,
last_reviewed_at.
```

This makes the graph auditable and prevents the LLM from inventing relationships.

## 3.3 What the graph should not do

The graph should not be a full knowledge graph of the market.

Do not build:

```text
full supply-chain database,
all global conflicts,
all public-company competitors,
all private AI companies,
automated web-mined relationship graph,
unbounded graph traversal.
```

For the capstone, it is enough to show **one or two curated cross-impact families**:

```text
AI model release → frontier AI competition → MSFT / GOOGL / AMZN / NVDA
Taiwan disruption → semiconductor manufacturing exposure → NVDA / AAPL / AMD / TSM
Red Sea conflict → shipping disruption → logistics or fuel-sensitive sectors
Middle East escalation → oil price risk → airlines / energy / transport
```

## 3.4 Graph schema

### ExposureGraphNode

```ts
export type ExposureGraphNode = {
  nodeId: string;
  nodeType:
    | "ticker"
    | "public_company"
    | "private_company"
    | "sector"
    | "technology_theme"
    | "product_category"
    | "commodity"
    | "region"
    | "country"
    | "shipping_route"
    | "risk_factor"
    | "macro_factor";
  name: string;
  aliases: string[];
  queryTerms: string[];
};
```

### ExposureGraphEdge

```ts
export type ExposureGraphEdge = {
  fromNodeId: string;
  toNodeId: string;
  edgeType:
    | "sector_member"
    | "technology_exposure"
    | "competitor_of"
    | "product_competitor_of"
    | "strategic_partner_of"
    | "cloud_provider_for"
    | "investor_in"
    | "supplier_of"
    | "customer_of"
    | "commodity_exposure"
    | "regional_exposure"
    | "production_exposure"
    | "sanction_exposure"
    | "shipping_exposure"
    | "macro_sensitivity";
  strength: "low" | "medium" | "high";
  confidence: number;
  sourceType: "manual_seed" | "filing" | "api_peer" | "api" | "wikidata" | "company_page" | "other";
  notes?: string;
  lastReviewedAt: string;
};
```

## 3.5 Example graph seed

```json
{
  "nodes": [
    {
      "nodeId": "ticker_MSFT",
      "nodeType": "ticker",
      "name": "MSFT",
      "aliases": ["Microsoft"],
      "queryTerms": ["Microsoft", "MSFT"]
    },
    {
      "nodeId": "private_Anthropic",
      "nodeType": "private_company",
      "name": "Anthropic",
      "aliases": ["Claude"],
      "queryTerms": ["Anthropic", "Claude", "Claude model"]
    },
    {
      "nodeId": "theme_frontier_ai",
      "nodeType": "technology_theme",
      "name": "Frontier AI",
      "aliases": ["AI models", "foundation models", "LLMs"],
      "queryTerms": ["frontier AI", "AI model", "large language model", "LLM"]
    },
    {
      "nodeId": "region_Taiwan",
      "nodeType": "region",
      "name": "Taiwan",
      "aliases": [],
      "queryTerms": ["Taiwan", "Taiwan earthquake", "Taiwan disruption"]
    },
    {
      "nodeId": "theme_semiconductors",
      "nodeType": "technology_theme",
      "name": "Semiconductors",
      "aliases": ["chips", "chipmaking"],
      "queryTerms": ["semiconductor", "chips", "chip export controls"]
    }
  ],
  "edges": [
    {
      "fromNodeId": "private_Anthropic",
      "toNodeId": "theme_frontier_ai",
      "edgeType": "technology_exposure",
      "strength": "high",
      "confidence": 0.9,
      "sourceType": "manual_seed",
      "notes": "Anthropic is a private frontier AI company; events about Claude are relevant to frontier AI competition.",
      "lastReviewedAt": "2026-05-28"
    },
    {
      "fromNodeId": "ticker_MSFT",
      "toNodeId": "theme_frontier_ai",
      "edgeType": "technology_exposure",
      "strength": "high",
      "confidence": 0.85,
      "sourceType": "manual_seed",
      "notes": "Microsoft is exposed to frontier AI through AI products and strategic AI positioning.",
      "lastReviewedAt": "2026-05-28"
    },
    {
      "fromNodeId": "region_Taiwan",
      "toNodeId": "theme_semiconductors",
      "edgeType": "regional_exposure",
      "strength": "high",
      "confidence": 0.85,
      "sourceType": "manual_seed",
      "notes": "Taiwan disruption can be relevant to semiconductor production risk.",
      "lastReviewedAt": "2026-05-28"
    }
  ]
}
```

## 3.6 How the graph drives query expansion before API calls

The exposure graph is used **before** articles arrive. This is the most important design point.

The user does not need to follow every related company manually. If the user follows only Apple, the watchlist remains:

```text
AAPL
```

Before querying Currents, the system expands that watchlist through accepted graph edges:

```text
AAPL
→ Apple
→ TSMC
→ Foxconn
→ Taiwan semiconductor exposure
→ China manufacturing exposure
→ iPhone supply chain
→ relevant public peers / competitors
```

That expanded set becomes the query plan.

Example query plan for AAPL:

```json
{
  "watchedTicker": "AAPL",
  "directFinnhubQueries": ["AAPL"],
  "currentsCrossImpactQueries": [
    "TSMC production disruption",
    "Taiwan semiconductor earthquake",
    "Foxconn factory disruption",
    "China iPhone production",
    "chip export controls Apple supply chain",
    "smartphone demand China",
    "Apple competitor AI device launch"
  ]
}
```

This is how the system can find an article about TSMC even when the user only follows AAPL and the article does not mention Apple.

There are two query families:

```text
Direct queries:
Finnhub company-news for watched ticker symbols.

Cross-impact queries:
Currents keyword queries generated from dependency, peer, sector, region, commodity, technology-theme, and risk-factor nodes connected to the watched tickers.
```

Finnhub company-peers may be used during graph setup or refresh to suggest public peer nodes. Those accepted peer nodes can then contribute query terms. However, the peer API is not treated as a supply-chain source.

For each watched ticker, collect nearby graph nodes:

```text
ticker → company → dependencies / peers / sector / themes / regions / commodities / risk factors
```

Then generate bounded Currents queries from their `queryTerms`.

Example for a watchlist containing MSFT, GOOGL, AMZN, NVDA, AAPL:

```text
Anthropic OR Claude
OpenAI OR GPT
Gemini AI model
frontier AI model release
Taiwan semiconductor disruption
chip export controls
Red Sea shipping disruption
oil sanctions Middle East
```

This is the key sustainability move:

> The system does not monitor all world news. It monitors exposure-aware broad news generated from the watchlist graph.

## 3.7 Runtime graph routing after API results

The graph is used a second time after articles arrive. Query expansion helps fetch potentially relevant external articles; runtime routing validates whether the article really connects back to a watched ticker.

```text
1. Currents returns a broad article.
2. The article is normalized.
3. LLM extracts a CanonicalEvent with entities, event_type, event_tags, region, sector, technology_theme, commodity, and risk factors.
4. Code maps extracted entities/tags to graph nodes.
5. Code traverses 1-3 hops from matched nodes to watched ticker nodes.
6. Weak paths are dropped.
7. Surviving paths become ImpactCandidates.
8. The catalyst ledger decides new/update/duplicate.
9. The LLM generates a briefing using only article facts + graph path.
```

Path scoring:

```text
path_score = event_severity * average_edge_confidence * path_shortness_bonus
```

Suggested thresholds:

```text
path_score >= 0.70 → emit candidate
0.45-0.69 → log as weak candidate, no user briefing in demo
< 0.45 → drop
```

## 3.8 Example: Anthropic model release

Input article:

```text
Anthropic releases a new Claude model.
```

Canonical event:

```json
{
  "eventType": "private_company_technology",
  "entities": ["Anthropic", "Claude"],
  "eventTags": ["frontier_ai", "model_release", "AI_competition"],
  "possibleDirectionalPressure": "mixed"
}
```

Graph path:

```text
Anthropic → frontier AI competition → MSFT / GOOGL / AMZN / NVDA exposure
```

Briefing framing:

```text
This is not direct company news about MSFT or GOOGL. It may matter because a frontier model release can affect investor perception of AI-platform competition. The impact is tentative and depends on benchmark credibility, adoption, pricing, and market interpretation.
```

## 3.9 Example: war/shipping disruption

Input article:

```text
Conflict escalates near a key shipping route.
```

Canonical event:

```json
{
  "eventType": "geopolitical",
  "entities": ["Red Sea"],
  "eventTags": ["war", "shipping_disruption", "logistics_cost_risk"],
  "possibleDirectionalPressure": "mixed"
}
```

Graph path:

```text
Red Sea shipping route → shipping/logistics cost risk → exposed watched ticker or sector
```

Briefing framing:

```text
The event may matter only if the watched company has logistics, fuel-cost, supply-chain, or commodity exposure encoded in the graph. No graph path means no briefing.
```

---

# 4. Model and component choices

## 4.1 Model selection principles

The model choice should prioritize:

1. **Faithfulness:** briefings must stay grounded in the article and graph path.
2. **Latency:** the system targets a 5-10 minute monitoring loop, not deep research.
3. **Cost:** the model should only be called after cheap filters and routing.
4. **Structured output reliability:** canonical events need valid JSON.

The first implementation should use a strong mid-tier model. A high-reasoning model is not necessary for every call because the workflow controls most of the reasoning path.

## 4.2 Suggested model roles

| Role | Model type | Runtime or offline | Reason |
|---|---|---|---|
| Batch canonical event extraction | Strong mid-tier LLM | Runtime | Convert a batch of multiple articles/event texts into a structured list of canonical events in a single LLM call |
| Per-ticker synthesis | Strong mid-tier LLM | Runtime | Generate one final market-impact synthesis per watched ticker from ticker-specific context only |
| Embeddings | Embedding model | Runtime | Cluster similar event summaries for catalyst memory |
| LLM judge | Strong LLM | Offline eval | Evaluate faithfulness and impact-path explanation quality |

## 4.3 Why not fine-tuning

Fine-tuning is not needed for the capstone. The system needs fresh information, structured context, graph constraints, and good prompts. Fine-tuning would add model lifecycle complexity before the architecture is proven.

## 4.4 Why not autonomous agents

Autonomous agents are deliberately rejected.

The process can be represented as a workflow graph:

```text
fetch → filter → extract → route → memory check → bucket by ticker → per-ticker synthesize → log
```

A planning agent is not needed to decide the steps. It would add latency, cost, and nondeterminism. For a financial-information product, observability and control are more important than open-ended autonomy.

---

# 5. Iterative solution design

## 5.0 Iterations overview

The final output is always **per watched ticker**. The system does not send all news for all companies into one large LLM call. It first routes articles/events into ticker-specific context buckets, then runs a final synthesis step for each ticker.

This matters because Apple should only see Apple-relevant context, including indirect events such as TSMC or Foxconn news if the exposure graph links them to Apple. Microsoft should not see unrelated Apple-only context.

### Iteration 1: Direct per-ticker catalyst synthesis

Convert ticker-tagged Finnhub company news into one final market-impact synthesis per watched ticker.

APIs used:

```text
Finnhub company-news only.
```

The system answers:

> For each watched ticker, what direct fresh catalysts appeared in the last 5 minutes, and what is the ticker-level situation?

### Iteration 2: Catalyst memory before per-ticker synthesis

Add a recent-catalyst ledger to decide whether each fresh article is new, duplicate, or a meaningful update before it enters the ticker context bucket.

APIs used:

```text
Finnhub company-news only.
```

The system answers:

> For each watched ticker, which fresh catalysts are new or updated enough to influence the final ticker synthesis?

### Iteration 3: External cross-impact routing into per-ticker synthesis

Add Currents broad-news discovery and exposure-graph routing. External events are included only in the ticker bucket that has a valid graph path to the event.

APIs used:

```text
Finnhub company-news + Currents search/latest-news + exposure graph.
```

The system answers:

> For each watched ticker, do any fresh untickered external events have a valid exposure path to that ticker, and how do they change the ticker-level market-impact synthesis?

---


# 6. Iteration 1: Direct company news to catalyst briefing

## 6.1 Architecture and design

### New features

Iteration 1 builds the basic direct-news spine:

```text
watchlist tickers
→ Finnhub company-news ingestion
→ source/freshness filters
→ batch canonical event extraction (single LLM call)
→ direct ticker routing
→ ticker context bucket
→ per-ticker market-impact synthesis
```

### Usage paradigm

Workflow agent.

The workflow is pre-orchestrated by code. The LLM does not choose tools or plan the process.

### Architecture diagram

```text
Customer watchlist
        ↓
Finnhub company-news pulls
        ↓
Freshness filter + exact dedup
        ↓
Batch canonical event extraction (single LLM call)
        ↓
Direct ticker routing (deterministic Code)
        ↓
Ticker context buckets
        ↓
One synthesis call per ticker
        ↓
Watchlist UI: per-ticker analysis + supporting event cards
```

### API calls

```text
GET Finnhub /company-news?symbol={ticker}&from={YYYY-MM-DD}&to={YYYY-MM-DD}
```

Recommended capstone usage:

```text
Manual UI trigger: Fetch latest catalysts.
Call Finnhub company-news for today's date for each watched ticker.
Locally filter to articles published/indexed in the last 5 minutes.
Allow a maximum 10-minute lookback buffer to avoid missing late-indexed articles.
Deduplicate by URL/article ID/title hash before LLM processing.
```

Important distinction:

```text
Capstone live input = fresh API response from manual UI pull.
Golden dataset = offline prompt/eval material, not the live capstone input.
```

### Context engineering

The LLM receives compact context:

```text
article headline,
article summary/body if available,
source,
published timestamp,
candidate ticker,
known company name,
format instructions,
compliance instructions.
```

The extraction prompt should require structured JSON:

```json
{
  "event_type": "earnings | guidance | regulation | supply_chain | legal | product | macro | geopolitical | technology | other",
  "event_summary": "one sentence",
  "hard_facts": ["fact 1", "fact 2"],
  "directly_mentions_ticker": true,
  "materiality": "high | medium | low | none",
  "possible_directional_pressure": "positive | negative | mixed | unclear",
  "uncertainties": ["uncertainty 1"],
  "evidence": ["source-grounded evidence"]
}
```

### Expected output

The user receives one **ticker-level market-impact synthesis** per watched ticker. The synthesis is supported by event-level catalyst cards, but the final suggestion/analysis is per ticker.

```json
{
  "ticker": "AAPL",
  "briefing_type": "new_catalyst",
  "relationship_type": "direct",
  "headline": "Apple supplier warning may pressure sentiment",
  "what_is_happening": "Short summary of the event.",
  "why_it_may_matter": "Explanation of the possible market mechanism.",
  "possible_stock_influence": {
    "direction": "negative",
    "strength": "medium",
    "confidence": "tentative"
  },
  "uncertainties": ["What is not known yet."],
  "watch_items": ["What to monitor next."],
  "evidence": ["Grounded source fact."],
  "not_financial_advice": true
}
```

### Storage and traces

Iteration 1 should keep the application storage small:

```text
Persistent app state:
watchlist_config,
briefings,
recent_catalyst_ledger entries created from emitted briefings.

Transient workflow artifacts:
raw API payloads, normalized article objects, canonical event objects.

Observability/eval platform traces:
API response metadata, normalized article fields, prompt inputs/outputs, extraction result, routing result, latency, token usage, and eval scores.
```

Raw and normalized articles are not permanent product tables. They are either processed in memory or emitted as traces to Phoenix, Langfuse, or a similar observability platform.

## 6.2 Evaluation and optimization

| Metric | Type | Purpose |
|---|---|---|
| Structured output validity | Code-based | JSON must match schema |
| Direct routing accuracy | Code/manual | Correct ticker assigned |
| Materiality precision | Human/LLM judge | Avoid briefing irrelevant articles |
| Briefing faithfulness | LLM judge + spot check | No fabricated facts |
| Compliance pass rate | Code/LLM judge | No buy/sell instructions |
| Latency per article | Operational | Keep workflow practical |

Good output:

```text
correct ticker,
clear event summary,
grounded explanation,
tentative impact language,
explicit uncertainty,
no financial advice.
```

Bad output:

```text
wrong ticker,
fabricated fact,
buy/sell recommendation,
confident prediction unsupported by evidence.
```

---

# 7. Iteration 2: Catalyst memory and story-threading

## 7.1 Architecture and design

### New features

Iteration 2 adds a recent-catalyst ledger.

The system stops treating articles as the unit of reasoning. The unit becomes the **catalyst thread**.

```text
same catalyst + no new fact → suppress
same catalyst + new hard fact → update briefing
new catalyst → new briefing
```

### Architecture diagram

```text
Normalized articles
        ↓
Batch canonical event extraction (single LLM call)
        ↓
Direct ticker routing (deterministic Code)
        ↓
Catalyst fingerprint mapping (per candidate)
        ↓
Recent-catalyst ledger lookup (deterministic Code check)
        ↓
Decision:
duplicate / update / new
        ↓
Only new/update events enter ticker context bucket
        ↓
One synthesis call per ticker
        ↓
Ledger update + per-ticker output + trace
```

### API calls

Still Finnhub only:

```text
GET Finnhub /company-news?symbol={ticker}&from={YYYY-MM-DD}&to={YYYY-MM-DD}
```

The difference from Iteration 1 is not the source. The difference is memory.

### Catalyst fingerprint

```text
ticker_focus,
event_type,
semantic event embedding,
hard facts,
source timestamp.
```

Embeddings are used for near-duplicate clustering, not for open-ended RAG.

### Ledger decision rules

```text
If exact article id/url already seen:
    drop as exact duplicate.

If semantic similarity above threshold and no new hard fact:
    suppress as duplicate.

If semantic similarity above threshold and new hard fact exists:
    emit update briefing.

If similarity below threshold:
    create new catalyst.
```

### Storage and traces

Iteration 2 adds only the memory needed for duplicate/update behavior:

```text
Persistent app state:
recent_catalyst_ledger, latest briefing reference, catalyst TTL, threshold configuration.

Optional compact fields inside the ledger:
source URL hashes, article title hashes, hard facts already seen, embedding reference or embedding value.

Observability/eval platform traces:
exact duplicate decision, semantic duplicate score, new-hard-fact decision, update/suppress/new decision, latency, token usage, and judge scores for offline eval.
```

The system does not need permanent `catalyst_members`, `canonical_events`, or full update logs as separate product tables unless the product later requires a detailed audit history.

### Ledger rollback on failed runs

The catalyst ledger is an in-memory store keyed per server process. If a pipeline run fails before the LLM synthesis step (for example, due to API rate-limiting), any ledger writes that Node 4 may have made during that run could incorrectly mark fresh articles as already-seen when the user retries.

The implemented defence:

```text
1. Before each /api/run invocation, snapshot the current ledger state.
2. After the run completes, check whether the workflow set llm_failed=True.
3. If yes, restore the snapshot, reverting all ledger writes from the failed run.
4. On unexpected pipeline crash, also restore the snapshot.
```

This means a failed run leaves zero trace in the ledger. The next retry sees all articles as genuinely fresh.

### Catalyst ledger entry

```json
{
  "catalyst_id": "cat_001",
  "ticker": "AAPL",
  "event_type": "supply_chain",
  "canonical_summary": "Apple supplier warns of production delays.",
  "embedding_ref": "emb_001",
  "first_seen_at": "2026-05-28T09:00:00Z",
  "last_updated_at": "2026-05-28T09:40:00Z",
  "expires_at": "2026-05-29T09:00:00Z",
  "member_article_ids": ["art_001", "art_002"],
  "hard_facts_seen": ["production delay", "supplier warning"],
  "status": "live"
}
```

## 7.2 Evaluation and optimization

| Metric | Type | Purpose |
|---|---|---|
| Duplicate suppression accuracy | Code/manual | Repeated articles should not create repeated briefings |
| Missed update rate | Manual/LLM judge | New facts should not be suppressed |
| Over-merge rate | Manual | Different catalysts should not be merged |
| Under-merge rate | Manual | Same catalyst should not create many threads |
| Catalyst dedup rate | Operational | Raw articles divided by unique catalysts |
| Ledger latency | Operational | Lookup should be fast |

Optimization proposals:

```text
If duplicate spam remains: lower similarity threshold or improve canonical summary.
If real updates are missed: include hard_fact comparison before suppression.
If unrelated events merge: add stricter event_type and ticker matching.
```

---

# 8. Iteration 3: External cross-impact catalyst routing

## 8.1 Architecture and design

### New features

Iteration 3 expands the system beyond direct ticker-tagged news.

It handles external events such as:

```text
war escalation,
sanctions,
shipping route disruption,
commodity shock,
energy price shock,
regional conflict,
private-company AI model release,
export controls,
supplier disruption,
sector-wide regulation,
natural disaster covered by mainstream news.
```

The system uses Currents to discover external articles and the exposure graph to decide whether they matter.

The LLM does not freely invent the butterfly effect. The graph proposes possible impact paths. The LLM explains the proposed path and marks uncertainty.

### Architecture diagram

```text
Watchlist
   ↓
Exposure graph
   ↓
Exposure-aware query planner
   ↓
Currents search/latest-news + Finnhub news
   ↓
Freshness filter + exact dedup
   ↓
Batch canonical event extraction (single LLM call)
   ↓
Event tags mapped to graph nodes & direct tickers
   ↓
Exposure graph traversal & direct routing (deterministic Code)
   ↓
Impacted watched ticker candidates
   ↓
Catalyst ledger per ticker (deterministic Code check)
   ↓
Ticker context buckets
   ↓
One cross-impact-aware synthesis call per ticker
```

### API calls

Currents targeted search:

```text
GET Currents /search?keywords={query}&language=en&start_date={date}&end_date={date}
```

Optional Currents latest-news scan:

```text
GET Currents /latest-news?language=en&category={category}&country={country}
```

Recommended capstone usage:

```text
Manual UI trigger: Fetch latest catalysts.
Generate 5-20 exposure-aware queries from the graph.
Run targeted Currents search/latest-news requests.
Do not ingest the full latest-news feed.
Locally filter to articles published/indexed in the last 5 minutes.
Allow a maximum 10-minute lookback buffer for indexing delays.
Do not permanently store raw JSON as product state. Keep raw payloads in memory or emit them to Phoenix/Langfuse-style traces with short retention.
Deduplicate by URL/title/source/time before LLM processing.
```

### Runtime target-resolution logic

```text
1. Extract event tags from the broad article.
2. Match tags/entities to graph nodes.
3. Traverse 1-3 hops from matched nodes.
4. Keep only paths ending in watched tickers.
5. Score path strength using edge confidence, event severity, and path length.
6. Drop weak or vague paths.
7. Send surviving path + event to the catalyst ledger for the affected ticker.
8. Add only new or materially updated events to that ticker's context bucket.
9. Generate one final synthesis per ticker from its own bucket.
```

### Ticker-specific context buckets

Before the final LLM synthesis, the backend creates one context package per watched ticker. This is the boundary that prevents context pollution across companies.

A ticker synthesis call receives only:

```text
ticker and company name,
run window,
direct events routed to this ticker,
cross-impact events routed to this ticker through valid graph paths,
recent active ledger entries for this ticker,
suppressed duplicate counts,
uncertainties and source references.
```

It must not receive:

```text
all raw articles,
all unrelated tickers,
full watchlist context,
full exposure graph,
unvalidated external events.
```

Example ticker bucket:

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "run_window": {
    "from": "2026-05-28T14:00:00Z",
    "to": "2026-05-28T14:05:00Z"
  },
  "direct_events": [
    {
      "event_id": "evt_001",
      "source": "Finnhub",
      "headline": "Apple faces new regulatory scrutiny",
      "event_type": "regulatory",
      "published_at": "2026-05-28T14:03:00Z",
      "possible_directional_pressure": "negative",
      "confidence": "medium"
    }
  ],
  "cross_impact_events": [
    {
      "event_id": "evt_002",
      "source": "Currents",
      "headline": "Taiwan semiconductor disruption reported",
      "event_type": "supply_chain_risk",
      "impact_path": ["Taiwan", "TSMC", "AAPL"],
      "why_routed_to_ticker": "Apple has semiconductor supply-chain exposure through TSMC.",
      "possible_directional_pressure": "negative",
      "confidence": "low_to_medium"
    }
  ],
  "recent_active_catalysts": [
    {
      "catalyst_id": "cat_001",
      "summary": "EU regulatory pressure remains active.",
      "last_updated_at": "2026-05-28T13:59:00Z"
    }
  ],
  "suppressed_duplicate_count": 3
}
```

### Example: Anthropic model release

```text
Article: Anthropic releases a new Claude model.
Event tags: Anthropic, Claude, frontier_ai, model_release.
Graph path: Anthropic → Frontier AI → MSFT / GOOGL / AMZN / NVDA.
Briefing: tentative competitive-pressure briefing for watched AI-exposed tickers.
```

### Example: war/shipping disruption

```text
Article: conflict escalates near a shipping route.
Event tags: war, shipping_route_disruption, logistics_cost_risk.
Graph path: shipping route → logistics cost risk → exposed sector/company/ticker.
Briefing: tentative cost/supply-chain risk briefing for watched exposed tickers.
```

### Example: Taiwan semiconductor disruption

```text
Article: earthquake or disruption affects Taiwan.
Event tags: Taiwan, semiconductor, production_disruption.
Graph path: Taiwan → semiconductor production exposure → watched semiconductor/AI hardware tickers.
Briefing: tentative supply-chain risk briefing.
```

## 8.2 Expected output

The final output is **one ticker-level market-impact synthesis per watched ticker**. Cross-impact events appear inside the ticker synthesis only when the graph path is valid.

```json
{
  "ticker": "AAPL",
  "run_window": {
    "from": "2026-05-28T14:00:00Z",
    "to": "2026-05-28T14:05:00Z"
  },
  "final_status": "mixed_to_negative",
  "summary_headline": "AAPL has fresh regulatory and supply-chain risk signals",
  "situation_summary": "In the latest freshness window, AAPL has one direct regulatory catalyst and one indirect semiconductor supply-chain catalyst routed through the exposure graph.",
  "main_catalysts": [
    {
      "type": "direct",
      "label": "Regulatory scrutiny",
      "possible_influence": "negative",
      "confidence": "medium"
    },
    {
      "type": "cross_impact",
      "label": "Taiwan semiconductor disruption risk",
      "impact_path": ["Taiwan", "TSMC", "AAPL"],
      "possible_influence": "negative",
      "confidence": "low_to_medium"
    }
  ],
  "tentative_stock_influence": "Possible negative intraday pressure if traders focus on regulatory and supply-chain risk. The evidence remains tentative because no direct Apple production impact is confirmed.",
  "uncertainties": [
    "No confirmed production impact from suppliers.",
    "The market may ignore the indirect catalyst without company or supplier confirmation."
  ],
  "watch_items": [
    "supplier statement",
    "company comment",
    "AAPL price and volume reaction"
  ],
  "source_event_ids": ["evt_001", "evt_002"],
  "not_financial_advice": true
}
```

The UI can still show underlying event-level cards below the ticker synthesis, but the top-level product answer is per ticker.

## 8.3 Evaluation and optimization

| Metric | Type | Purpose |
|---|---|---|
| Query precision | Manual/code | Currents queries should return exposure-relevant articles |
| Event-tag extraction accuracy | Code/manual | Entities, regions, themes, and risk tags must be right |
| Exposure routing precision | Manual/code | Routed tickers should have valid paths |
| False butterfly rate | Manual/LLM judge | Avoid vague over-connection |
| Path validity | Manual/LLM judge | Impact path should be concrete and plausible |
| Cross-impact recall on curated cases | Manual | Known indirect events should be caught |
| Briefing faithfulness | LLM judge | Explanation must stay within event + graph |

Good:

```text
routes broad event to watched ticker through a specific path,
shows the path clearly,
uses tentative language,
explains uncertainty,
does not pretend causality is proven.
```

Bad:

```text
routes to unrelated tickers,
uses vague “market uncertainty” logic for everything,
invents a relationship not in the graph,
presents speculation as certainty.
```

---

# 9. Overall system architecture

## 9.1 Final architecture

```text
                    ┌──────────────────────┐
                    │  Customer watchlist   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Exposure graph      │
                    │  query terms + paths │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
┌─────────▼─────────┐                    ┌──────────▼──────────┐
│ Direct news intake │                    │ External news intake │
│ Finnhub company    │                    │ Currents targeted    │
│ news by ticker     │                    │ search/latest-news   │
└─────────┬─────────┘                    └──────────┬──────────┘
          │                                         │
          └────────────────────┬────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Freshness + dedup    │
                    │ last 5 min, max 10   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Batch canonical     │
                    │ event extraction    │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
┌─────────▼─────────┐                    ┌──────────▼──────────┐
│ Direct ticker      │                    │ Exposure graph       │
│ routing            │                    │ routing              │
└─────────┬─────────┘                    └──────────┬──────────┘
          │                                         │
          └────────────────────┬────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Ledger per ticker    │
                    │ duplicate/update/new │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Ticker context       │
                    │ buckets              │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Per-ticker synthesis │
                    │ one LLM call/ticker  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Watchlist UI         │
                    │ ticker summaries     │
                    │ + trace evidence     │
                    └─────────────────────┘
```

The final LLM call is scoped per ticker. For example, the AAPL synthesis sees AAPL direct events, AAPL cross-impact events such as TSMC/Foxconn/Taiwan paths, and AAPL ledger entries. It does not see unrelated NVDA or MSFT context.

## 9.2 Storage and observability strategy

The system should not become a general news data warehouse. Storage is split into **product state**, **transient workflow artifacts**, and **observability/evaluation traces**.

### Persistent application state

| Store | Purpose | Retention |
|---|---|---|
| watchlist_config | Watched tickers and company names | Persistent |
| exposure_graph | Manually reviewed companies, sectors, themes, private companies, regions, commodities, routes, and risks | Persistent |
| recent_catalyst_ledger | Narrow memory for duplicate/update/new decisions | TTL-based, for example intraday or a few trading days |
| ticker_summaries | Final per-ticker market-impact synthesis for each manual run | Persistent for demo/session, optionally longer in production |
| prompt_and_threshold_config | Prompt versions, schema versions, similarity thresholds, TTL config | Persistent and versioned |

### Transient workflow artifacts

These objects are produced during a run but are not permanent product tables:

```text
raw API payloads,
normalized articles,
canonical events,
impact candidates,
event-level briefing/evidence objects,
ticker context buckets,
full LLM prompts/responses,
full decision logs.
```

They can live in memory during the request, or be kept only with a short TTL in development/debug mode.

### Observability and evaluation traces

Intermediate artifacts should be emitted to an observability platform such as **Arize Phoenix**, **Langfuse**, or a similar tracing/evaluation tool. Phoenix tracing captures model calls, retrieval, tool use, and custom logic step by step through OpenTelemetry-style traces. Langfuse supports LLM traces, latency/cost monitoring, prompt/completion inspection, evaluation scores, datasets, experiments, and prompt management.

The application should send traces for:

```text
manual fetch run ID,
API source and article metadata,
freshness filter result,
canonical extraction output,
direct/cross-impact routing decision,
exposure graph path,
ledger decision,
per-ticker synthesis prompt/output,
latency, token usage, cost,
eval scores and judge labels.
```

This keeps the product database lean while preserving enough visibility to debug failures, tune prompts, and present eval results.

### Golden dataset separation

Golden dataset examples are separate from runtime storage. They are stored as offline eval cases used for prompt design, schema tuning, judge calibration, and regression tests. They are not mixed into the live capstone input or product database.

## 9.3 Workflow fault behaviour

The pipeline uses a `llm_failed` sentinel field in the LangGraph state to implement fail-fast semantics.

```text
Node 2 (canonical event extraction):
  → If the LLM call raises an exception (rate-limit, timeout, etc.):
    → Set llm_failed=True
    → Return canonical_events=[]
    → Do NOT fall back to rule-based junk events (this would pollute the ledger)

Node 3 (routing) and Node 4 (ledger memory):
  → Receive empty canonical_events, produce no candidates.
  → Ledger is not written to.

Node 5 (per-ticker synthesis):
  → Check llm_failed at entry
  → If True: skip all LLM calls, return "Pipeline halted — LLM unavailable" per ticker

Node 6 (compliance gate):
  → Runs regardless; cleans whatever text was produced.

In main.py:
  → After workflow.invoke() returns, if llm_failed=True:
    → Roll back ledger to pre-run snapshot.
  → On any unexpected exception:
    → Also roll back ledger.
```

This ensures a failed run is completely idempotent from the ledger's perspective: the next re-run sees all articles as fresh.

The API response includes `"llmFailed": true/false` so the frontend can show a clear retry message rather than displaying empty or misleading synthesis cards.

## 9.4 What is not included

The capstone does not build:

```text
autonomous research agents,
trading execution,
buy/sell recommendation engine,
portfolio optimization,
universal geopolitical reasoning,
fully automated supply-chain graph construction,
real-time licensed market-data pricing,
fine-tuned financial model.
```

---

# 10. Evaluation plan

## 10.1 Evaluation philosophy

The evaluation focuses on the system's key risks:

```text
wrong ticker,
duplicate spam,
missed update,
hallucinated facts,
invalid impact path,
overgeneralized butterfly logic,
unsafe financial advice language,
source/API query noise.
```

Use code-based evals where outputs are objective. Use LLM judges only for subjective dimensions such as faithfulness and explanation quality.

## 10.2 Core metrics

| Component | Metric | Eval type |
|---|---|---|
| API ingestion | successful fetch and parse rate | Code |
| Query planner | query precision | Manual/code |
| Canonical extraction | JSON validity | Code |
| Canonical extraction | event-type accuracy | Manual/LLM judge |
| Direct routing | correct ticker assignment | Code/manual |
| Catalyst ledger | duplicate-card rate | Code/manual |
| Catalyst ledger | missed-update rate | Manual |
| Exposure graph routing | path validity | Manual/LLM judge |
| Exposure graph routing | false butterfly rate | Manual/LLM judge |
| Per-ticker synthesis | faithfulness and ticker-specific context containment | LLM judge + human spot check |
| Compliance | no advice language | Code/LLM judge |
| Operations | latency, LLM calls per article, and LLM calls per ticker | Logs |

## 10.3 Minimum reference set

The capstone does not need a huge benchmark. It needs a small, meaningful reference set:

```text
10-15 direct company-news examples,
5-10 duplicate/update examples,
5-10 cross-impact examples,
5 negative examples where no briefing should be emitted.
```

Expected behavior should be documented for each case.

## 10.4 LLM judge usage

LLM judges are used offline, not as a default runtime loop.

The judge checks:

```text
Does the briefing only use facts from the source event and graph path?
Is the impact path concrete?
Is uncertainty explicit?
Does the output avoid buy/sell advice?
Is the explanation useful for an intraday trader?
```

Runtime judge-retry is rejected for the main architecture because it adds latency and cost before proving value.

---

# 11. Guardrails

## 11.1 Input guardrails

Input content is untrusted.

Guardrails:

```text
store source metadata,
filter stale articles,
filter low-quality sources where possible,
deduplicate exact URLs/IDs,
do not allow article text to override system instructions,
separate source content from model instructions,
log source and timestamp for every briefing.
```

### Finnhub summary field deduplication

Finnhub's `summary` field frequently appends a verbatim copy of the article headline at the end of the summary text. Sending this duplication to the LLM inflates prompt tokens, degrades extraction quality, and creates misleading Arize traces where the summary appears to be the same across many articles.

The implemented fix strips the trailing headline repetition from the `summary` field before constructing the batch extraction prompt:

```text
clean_summary(headline, summary):
  if summary ends with headline (case-insensitive):
    strip headline from end of summary
    return cleaned summary
  else:
    return summary as-is
```

This runs as a pure text transformation in Node 2 before any LLM call. No API call or extra latency is added.

## 11.2 Output guardrails

The system must not provide direct trading instructions.

Avoid:

```text
buy,
sell,
enter trade,
exit trade,
you should short,
this is guaranteed,
this will move the stock.
```

Use:

```text
possible pressure,
potential risk,
tentative impact,
watch item,
uncertainty,
not financial advice.
```

## 11.3 Compliance posture

The product surfaces information and possible mechanisms. It does not recommend trades.

Every briefing should include:

```text
This is an informational briefing, not financial advice.
The impact assessment is tentative and may be incomplete.
Verify with market data and official sources before making decisions.
```

## 11.4 Cross-impact guardrail

The butterfly channel has a special guardrail:

> No graph path, no cross-impact briefing.

The LLM may explain a path, but it may not invent one that is not present in the exposure graph or explicit source context.

---

# 12. Cost, latency, and performance plan

## 12.1 Cost drivers

Main cost drivers:

```text
number of fetched articles,
number of Currents queries,
number of LLM extraction calls,
number of event extraction calls and per-ticker synthesis calls,
embedding calls for catalyst memory,
LLM judge calls during offline eval.
```

## 12.2 Latency strategy

The prototype target is a 5-10 minute freshness window: manual API pulls in the capstone demo, automatic 5-minute polling in production.

Latency levers:

```text
batch API pulls,
parallel article processing,
cheap code filters before LLM calls,
short structured extraction output,
ledger lookup before briefing synthesis,
graph routing before LLM explanation,
no autonomous planning loops.
```

## 12.3 Cost optimization hierarchy

Optimize in this order:

```text
1. Better query planner and source filters.
2. Group articles and run Batch Extraction in a single LLM call.
3. Fewer synthesis calls through ledger deduplication and routing.
4. Embedding threshold tuning.
5. Only then consider model changes.
```

Do not add autonomous loops or fine-tuning before proving the workflow.

## 12.4 Performance targets

| Target | Prototype expectation |
|---|---|
| Monitoring loop | 5-10 minutes |
| Finnhub pulls | Whole-day replay pulls or bounded polling |
| Currents queries | Exposure-aware, capped per run |
| Ledger lookup | milliseconds to low seconds |
| LLM calls | only after filters |
| Duplicate-card rate | low after Iteration 2 |
| False butterfly rate | explicitly measured in Iteration 3 |
| Compliance failures | zero tolerated in final demo outputs |

---

# 13. Tradeoffs and rejected alternatives

## 13.1 One big LLM call versus staged workflow

Rejected:

```text
Article + watchlist + broad context → one big LLM call → answer
```

Reason:

```text
hard to debug,
hard to evaluate,
more hallucination risk,
weak control over routing,
expensive at scale.
```

Accepted:

```text
extract → route → memory → synthesize
```

## 13.2 RAG versus catalyst ledger

This is not a classic RAG system. The main memory requirement is not “retrieve documents to answer a question.” It is:

> Have we already seen this catalyst, and did it materially develop?

Therefore, the system uses a recent-catalyst ledger with embeddings for near-duplicate clustering. This is narrower and more controllable than a general vector knowledge base.

## 13.3 LLM-only butterfly reasoning versus exposure graph

Rejected:

```text
Ask the LLM whether any world event could affect any watched ticker.
```

Reason:

```text
over-connects everything,
hard to evaluate,
low precision,
creates hallucinated causal chains.
```

Accepted:

```text
External article → extracted tags → exposure graph path → LLM explanation.
```

The graph controls the candidate path. The LLM explains it.

## 13.4 Many niche event APIs versus one broad news API

Rejected:

```text
GDACS + USGS + EONET + ReliefWeb + ACLED + RSS + company blogs + finance APIs
```

Reason:

```text
too many integrations,
too many schemas,
too much normalization,
too hard to build and present in the capstone.
```

Accepted:

```text
Finnhub for direct company news.
Currents for broad external article discovery.
Exposure graph for relevance.
```

## 13.5 Personalization removed

Position and strategy personalization were considered but removed from the final capstone scope.

Reason:

```text
The real project thesis is cross-impact detection, not trader-specific strategy adaptation.
Personalization adds extra stores, extraction logic, compliance risk, and eval burden.
Removing it makes the project cleaner and keeps the focus on indirect catalyst detection.
```

The system remains user-specific through the watchlist, but it does not model positions, risk tolerance, or trading strategy.

---

# 14. Presentation story

## Slide 1: Problem

Ticker-based alerts miss important events. War, sanctions, private-company AI news, commodity shocks, and supplier disruptions can affect a watched stock even when the ticker is not mentioned.

## Slide 2: Naive AI solution

A naive system summarizes every article. This creates duplicate spam, weak relevance, and hallucinated causal claims.

## Slide 3: Iteration 1

Direct company news from Finnhub becomes structured catalyst briefings.

## Slide 4: Iteration 2

The system adds memory. It tracks catalyst threads and decides whether each article is new, duplicate, or an update.

## Slide 5: Iteration 3

The system adds external cross-impact routing. Currents discovers exposure-aware broad articles, and the exposure graph maps them to watched tickers.

## Slide 6: Architecture

Show the workflow:

```text
watchlist → APIs → extract → route → ledger → synthesize → log
```

## Slide 7: Exposure graph

Show one concrete path:

```text
Anthropic model release → frontier AI competition → GOOGL/MSFT/AMZN/NVDA
```

or:

```text
Taiwan disruption → semiconductor production exposure → NVDA/AAPL/TSM
```

## Slide 8: Evals

Show the core evals:

```text
structured extraction validity,
duplicate suppression,
missed updates,
query precision,
path validity,
false butterfly rate,
faithfulness,
compliance.
```

## Slide 9: Tradeoffs

Explain rejected choices:

```text
Alpha Vantage as main source,
GDELT as broad source,
many niche event APIs,
autonomous agents,
LLM-only butterfly reasoning,
fine-tuning,
personalization.
```

## Slide 10: Final claim

The system is not a summarizer. It is a catalyst-routing and story-threading workflow for intraday traders.

---

# 15. Final capstone definition

## Product name

**Cross-Impact Catalyst Briefings**

## One-sentence definition

A workflow-based AI system that turns direct company news and exposure-relevant external news into deduplicated catalyst briefings for watched stocks.

## Final architecture claim

The system combines LLM-based canonical event extraction, deterministic catalyst memory, and exposure-graph routing to explain both direct and indirect market catalysts.

## Final iteration claim

```text
Iteration 1: produce per-ticker synthesis from direct Finnhub news.
Iteration 2: use catalyst memory so per-ticker synthesis is not polluted by duplicate or stale articles.
Iteration 3: add indirect cross-impact events from Currents through graph-validated paths into the correct ticker bucket.
```

## Final compliance claim

The system surfaces tentative information and possible mechanisms. It does not give buy/sell advice or execute trades.

---

# 16. Build priorities

## Must build

```text
Finnhub company-news fetcher,
Currents targeted search fetcher,
raw article storage,
freshness-window filter for last 5 minutes with 10-minute buffer,
normalized article schema,
canonical event extraction,
direct catalyst briefing generation,
recent-catalyst ledger,
duplicate/update/new logic,
manual seed exposure graph,
query planner from graph terms,
cross-impact routing for 1-2 event families,
decision logs,
simple UI/feed output.
```

## Should build

```text
embedding-based near-duplicate matching,
LLM judge eval script,
path-validity eval,
source-quality flags,
briefing compliance checker,
weak-candidate debug panel.
```

## Could build

```text
more graph edges,
more Currents query categories,
simple price movement context,
confidence calibration,
optional historical article backup source.
```

## Do not build for capstone

```text
position/strategy personalization,
autonomous agents,
multi-agent debate,
trade execution,
portfolio management,
universal geopolitical reasoning,
automated graph construction,
fine-tuning.
```

---

# 17. Implementation workflow guide for coding

## 17.1 Coding principle

Build the project as a workflow graph with typed intermediate objects.

Do not pass raw article blobs from step to step. Each step should output a structured object that can be logged, tested, and shown in the UI.

## 17.2 Suggested modules

```text
/src/ingestion
  finnhubClient.ts
  currentsClient.ts
  replayLoader.ts

/src/queryPlanning
  buildExposureQueries.ts
  queryBudget.ts

/src/normalization
  normalizeArticle.ts
  dedupeExact.ts

/src/extraction
  extractCanonicalEvent.ts
  schemas.ts

/src/routing
  routeDirectTicker.ts
  mapEventToGraphNodes.ts
  exposureGraph.ts
  routeCrossImpact.ts

/src/memory
  catalystLedger.ts
  similarity.ts
  ttl.ts

/src/briefing
  synthesizeBriefing.ts
  complianceCheck.ts

/src/evals
  runReferenceSet.ts
  judgeFaithfulness.ts
  judgePathValidity.ts
  evaluateQueryPrecision.ts

/src/ui
  briefingViewModel.ts
  catalystThreadViewModel.ts
```

## 17.3 Workflow graph to build

```text
manual UI trigger: Fetch latest catalysts
  ↓
load watchlist
  ↓
load exposure graph
  ↓
build query plan
  ├── Finnhub direct company-news queries
  └── Currents exposure-aware broad-news queries
  ↓
fetch latest API results
  ↓
filter to last 5 minutes, max 10-minute lookback
  ↓
normalize articles
  ↓
exact dedup
  ↓
canonical event extraction
  ↓
route direct candidates
  ↓
route cross-impact candidates through graph
  ↓
merge impact candidates
  ↓
ledger decision
  ↓
add new/update event to ticker bucket, then per-ticker synthesis
  ↓
compliance check
  ↓
store ticker summary
  ↓
render watchlist UI
```

## 17.4 What should be stored

Store only durable product state in the application database:

```text
WatchlistConfig: watched tickers and company metadata.
ExposureGraph: nodes and edges for indirect impact.
CatalystLedgerEntry: live catalyst memory for duplicate/update/new decisions.
TickerSummary: final user-facing per-ticker synthesis for a manual run.
PromptAndThresholdConfig: prompt version, schema version, model choice, similarity thresholds, TTL settings.
EvalCase: golden dataset example, stored separately from runtime product data.
```

Do not create permanent product tables for every intermediate object. These should be transient or traced:

```text
RawArticle,
NormalizedArticle,
CanonicalEvent,
ImpactCandidate,
EventBriefing / event-level evidence objects,
TickerContextBucket,
full DecisionLog,
full LLM prompts and responses.
```

Use Phoenix, Langfuse, or a similar observability/eval platform for traces. The app emits structured trace spans; the observability tool stores the debugging and eval details.

## 17.5 Minimal data structures

### WatchlistConfig

```ts
export type WatchlistConfig = {
  watchlistId: string;
  tickers: Array<{
    ticker: string;
    companyName: string;
    exchange?: string;
  }>;
};
```

### QueryPlan

```ts
export type QueryPlan = {
  queryPlanId: string;
  createdAt: string;
  finnhubQueries: Array<{
    symbol: string;
    from: string;
    to: string;
    reason: "direct_company_news";
  }>;
  currentsQueries: Array<{
    keywords: string;
    language: "en";
    startDate?: string;
    endDate?: string;
    graphNodeRefs: string[];
    reason: string;
  }>;
};
```

### Transient workflow schemas

These types are useful in code, but they are not permanent product tables. They are created during a run, passed between workflow steps, and emitted as trace attributes/spans.

```ts
export type NormalizedArticle = {
  articleId: string;
  sourceApi: "finnhub" | "currents";
  sourceName: string;
  url: string;
  headline: string;
  summary?: string;
  publishedAt: string;
  relatedTickers: string[];
};

export type CanonicalEvent = {
  eventId: string;
  sourceArticleIds: string[];
  eventType:
    | "earnings"
    | "guidance"
    | "supply_chain"
    | "regulatory"
    | "legal"
    | "macro"
    | "geopolitical"
    | "commodity"
    | "sector"
    | "private_company_technology"
    | "natural_disaster"
    | "other";
  eventSummary: string;
  hardFacts: string[];
  entities: string[];
  eventTags: string[];
  regions?: string[];
  sectors?: string[];
  commodities?: string[];
  technologyThemes?: string[];
  possibleDirectionalPressure: "positive" | "negative" | "mixed" | "unclear";
  uncertaintyNotes: string[];
  evidence: string[];
};

export type ImpactCandidate = {
  candidateId: string;
  ticker: string;
  relationshipType: "direct" | "indirect";
  eventId: string;
  impactPath: string[];
  pathConfidence: number;
  reasonForRouting: string;
};
```

### CatalystLedgerEntry

```ts
export type CatalystLedgerEntry = {
  catalystId: string;
  ticker: string;
  eventType: CanonicalEvent["eventType"];
  relationshipType: "direct" | "indirect";
  canonicalSummary: string;
  embeddingRef?: string;
  firstSeenAt: string;
  lastUpdatedAt: string;
  expiresAt: string;
  memberArticleIds: string[];
  hardFactsSeen: string[];
  status: "live" | "expired";
};
```

### TickerContextBucket transient

This object is built during a manual fetch run and passed to the final per-ticker synthesis call. It is not stored as permanent product state.

```ts
export type TickerContextBucket = {
  runId: string;
  ticker: string;
  companyName: string;
  window: {
    from: string;
    to: string;
  };
  directEvents: Array<{
    eventId: string;
    eventType: CanonicalEvent["eventType"];
    headline: string;
    eventSummary: string;
    hardFacts: string[];
    possibleDirectionalPressure: CanonicalEvent["possibleDirectionalPressure"];
    confidence: "low" | "medium" | "high";
    sourceArticleIds: string[];
  }>;
  crossImpactEvents: Array<{
    eventId: string;
    eventType: CanonicalEvent["eventType"];
    headline: string;
    eventSummary: string;
    impactPath: string[];
    reasonForRouting: string;
    pathConfidence: number;
    possibleDirectionalPressure: CanonicalEvent["possibleDirectionalPressure"];
    sourceArticleIds: string[];
  }>;
  recentLedgerEntries: CatalystLedgerEntry[];
  suppressedDuplicateCount: number;
};
```

### TickerSummary

This is the final user-facing object stored by the application. It summarizes the accepted fresh and updated catalysts for one watched ticker in one manual run.

```ts
export type TickerSummary = {
  summaryId: string;
  runId: string;
  ticker: string;
  companyName: string;
  createdAt: string;
  window: {
    from: string;
    to: string;
  };
  summaryHeadline: string;
  situationSummary: string;
  mainCatalysts: Array<{
    label: string;
    relationshipType: "direct" | "indirect";
    eventType: CanonicalEvent["eventType"];
    possibleInfluence: "positive" | "negative" | "mixed" | "unclear";
    confidence: "low" | "medium" | "high" | "tentative";
    recency: "breaking" | "recent" | "background";  // derived from minutesAgo at synthesis time
    impactPath?: string[];
  }>;
  overallPossibleInfluence: "positive" | "negative" | "mixed" | "unclear";
  confidence: "low" | "medium" | "high" | "tentative";
  uncertainties: string[];
  watchItems: string[];
  sourceEventIds: string[];
  sourceArticleUrlHashes: string[];
  notFinancialAdvice: true;
  llmFailed?: boolean;  // true if the run was halted due to LLM unavailability
};
```

### Observability trace payload

The app does not need a permanent `DecisionLog` table. Instead, emit structured trace spans to Phoenix, Langfuse, or a similar platform. A compact local trace payload can look like this:

```ts
export type WorkflowTracePayload = {
  runId: string;
  timestamp: string;
  stage:
    | "query_planning"
    | "fetch"
    | "freshness_filter"
    | "canonical_extraction"
    | "direct_routing"
    | "cross_impact_routing"
    | "ledger"
    | "ticker_synthesis"
    | "compliance"
    | "eval";
  sourceApi?: "finnhub" | "currents";
  articleUrlHash?: string;
  ticker?: string;
  graphPath?: string[];
  ledgerDecision?: "new" | "update" | "duplicate" | "drop";
  model?: string;
  promptVersion?: string;
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  evalScores?: Record<string, number | string>;
  reason?: string;
};
```

## 17.6 UI data structure

The UI should be organized around the **final per-ticker synthesis**, not around a permanent feed of event-level briefings. Event-level details can still be shown as expandable evidence, but they are produced from the current ticker context bucket and observability traces rather than stored as durable product records.

Suggested UI view model:

```ts
export type TickerSummaryViewModel = {
  summaryId: string;
  runId: string;
  ticker: string;
  companyName: string;
  createdAt: string;
  summaryHeadline: string;
  situationSummary: string;
  overallPossibleInfluence: "positive" | "negative" | "mixed" | "unclear";
  confidence: "low" | "medium" | "high" | "tentative";
  catalystCount: number;
  directCatalystCount: number;
  crossImpactCatalystCount: number;
  keyImpactPaths: string[][];
  uncertainties: string[];
  watchItems: string[];
  sourceCount: number;
};
```

UI sections:

```text
Top: one latest synthesis per watched ticker.
Ticker detail: expand a ticker to inspect the main catalysts used in the synthesis.
Impact path view: show graph paths for indirect events.
Debug/eval panel: pull trace data from Phoenix/Langfuse for why items were routed, suppressed, or summarized.
```

The normal user-facing object is `TickerSummary`. Event-level artifacts are useful for explanation and debugging, but they are transient workflow context or observability trace data, not a permanent product feed by default.

## 17.7 Implementation order

Build in this order:

```text
1. WatchlistConfig, ExposureGraph, CatalystLedgerEntry, TickerSummary, and transient workflow types.
2. Finnhub company-news manual fetcher with 5-10 minute freshness filter.
3. Canonical event extraction prompt + schema validation.
4. Basic direct briefing synthesis.
5. Exact dedup.
6. Catalyst ledger with simple similarity.
7. Update/duplicate/new decisions.
8. Manual exposure graph JSON.
9. Query planner from graph terms.
10. Currents targeted search fetcher.
11. Cross-impact routing for 1-2 event families.
12. UI feed and thread view.
13. Phoenix/Langfuse tracing for workflow spans, LLM calls, latency, cost, and eval scores.
13. Eval scripts.
14. Compliance checks.
```

## 17.8 Minimum credible demo flow

The demo should start with a manual UI pull: **Fetch latest catalysts**. The system processes API results from the configured freshness window (120 minutes in the capstone live mode).

The demo should show three examples:

```text
1. Direct company article creates a catalyst briefing.
2. Duplicate article is suppressed, while a new hard fact creates an update.
3. Anthropic/war/Taiwan/shipping event does not mention the ticker, but the exposure graph routes it to a watched stock and the briefing explains the path.
```

That proves the full project thesis.

## 17.9 Implementation notes: runtime behaviour decisions

The following decisions were made during implementation and differ from or extend the original design.

### Freshness window in live mode

`FRESHNESS_LOOKBACK_MINUTES` is set to `120` in the capstone live environment (configurable via `.env`). The original design targeted 5-10 minutes. The wider window is used for the capstone demo because live API coverage over very short windows is sparse and inconsistent. In production, this should be reduced to 5-10 minutes once automatic polling is active.

### Batch extraction prompt includes article age

Each article in the Node 2 batch prompt now includes a `PUBLISHED: <timestamp> (X mins ago)` label. This gives the LLM explicit recency context during extraction, which improves prioritisation of breaking events.

### Per-ticker synthesis is recency-weighted

Before each ticker's context bucket is sent to the synthesis LLM, each event is annotated with a `minutesAgo` field. The synthesis system prompt instructs the LLM to weight events by recency:

```text
< 30 minutes old  → HIGH priority (breaking)
30–90 minutes old → MEDIUM priority (recent)
> 90 minutes old  → BACKGROUND context
```

The `mainCatalysts` schema includes a `recency` field (`breaking | recent | background`) in the LLM output.

### Workflow halts on LLM failure; ledger rolls back

If Node 2 (canonical event extraction) fails due to LLM unavailability (rate-limit, timeout):

```text
→ llm_failed=True is set in the LangGraph state
→ canonical_events=[] is returned (no rule-based fallback)
→ Node 5 (synthesis) skips all LLM calls
→ The API response includes "llmFailed": true
→ The ledger is rolled back to its pre-run state
```

This replaces the previous behaviour of silently continuing with rule-based garbage events, which would pollute the ledger and cause real articles to appear as duplicates on the next re-run.

### Finnhub summary cleaning

Finnhub appends the article headline verbatim at the end of the `summary` field. This is stripped before the batch extraction prompt is constructed, preventing token waste and ensuring the Arize trace shows distinct per-article summaries.

---

# 18. API references

The project relies on these documented APIs:

1. Finnhub API documentation: https://finnhub.io/docs/api
2. Finnhub rate limits: https://finnhub.io/docs/api/rate-limit
3. Currents API home/free tier: https://currentsapi.services/en
4. Currents latest-news endpoint: https://currentsapi.services/en/docs/latest_news
5. Currents search endpoint: https://currentsapi.services/en/docs/search
6. Currents pricing/free tier: https://currentsapi.services/en/product/price

Important source caveat:

```text
The API references establish feasibility and access pattern, not a guarantee that every war, flood, or private-company event will appear in the feed. The capstone pipeline therefore applies a local 5-minute freshness filter with a 10-minute safety buffer after fetching API results. The capstone should validate source coverage with a small API test before finalizing the demo dataset.
```
