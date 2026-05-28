# Exposure Graph and Scenario Replay Data

EXPOSURE_GRAPH = {
    "nodes": [
        # Watched Ticker Nodes
        {
            "nodeId": "ticker_AAPL",
            "nodeType": "ticker",
            "name": "AAPL",
            "aliases": ["Apple", "Apple Inc."],
            "queryTerms": ["Apple", "AAPL", "iPhone"]
        },
        {
            "nodeId": "ticker_MSFT",
            "nodeType": "ticker",
            "name": "MSFT",
            "aliases": ["Microsoft", "Microsoft Corp."],
            "queryTerms": ["Microsoft", "MSFT", "Azure"]
        },
        {
            "nodeId": "ticker_NVDA",
            "nodeType": "ticker",
            "name": "NVDA",
            "aliases": ["Nvidia", "Nvidia Corp."],
            "queryTerms": ["Nvidia", "NVDA", "GeForce", "H100", "Blackwell"]
        },
        {
            "nodeId": "ticker_TSM",
            "nodeType": "ticker",
            "name": "TSM",
            "aliases": ["TSMC", "Taiwan Semiconductor Manufacturing"],
            "queryTerms": ["TSMC", "TSM", "Taiwan Semiconductor"]
        },
        {
            "nodeId": "ticker_DAL",
            "nodeType": "ticker",
            "name": "DAL",
            "aliases": ["Delta Air Lines", "Delta"],
            "queryTerms": ["Delta Air Lines", "DAL"]
        },
        # Supply Chain / Partner Nodes
        {
            "nodeId": "supplier_Foxconn",
            "nodeType": "private_company",
            "name": "Foxconn",
            "aliases": ["Hon Hai Precision Industry"],
            "queryTerms": ["Foxconn", "Hon Hai"]
        },
        # Region Nodes
        {
            "nodeId": "region_Taiwan",
            "nodeType": "region",
            "name": "Taiwan",
            "aliases": ["Formosa"],
            "queryTerms": ["Taiwan", "Hsinchu", "Taipei"]
        },
        # Theme Nodes
        {
            "nodeId": "theme_frontier_ai",
            "nodeType": "technology_theme",
            "name": "Frontier AI",
            "aliases": ["AI models", "foundation models", "LLMs", "Generative AI"],
            "queryTerms": ["frontier AI", "AI model", "large language model", "LLM", "GPT", "Claude", "Gemini"]
        },
        {
            "nodeId": "theme_semiconductors",
            "nodeType": "technology_theme",
            "name": "Semiconductors",
            "aliases": ["chips", "silicon", "foundry"],
            "queryTerms": ["semiconductor", "microchips", "foundry", "fab"]
        },
        # Geopolitical / Risk Nodes
        {
            "nodeId": "route_Red_Sea",
            "nodeType": "shipping_route",
            "name": "Red Sea Shipping",
            "aliases": ["Suez Canal", "Bab el-Mandeb"],
            "queryTerms": ["Red Sea", "Suez Canal", "Bab el-Mandeb", "shipping lane", "maritime transport"]
        },
        {
            "nodeId": "risk_logistics_cost",
            "nodeType": "risk_factor",
            "name": "Logistics Cost Risk",
            "aliases": ["freight rates", "shipping costs", "fuel surcharge"],
            "queryTerms": ["freight rates", "shipping cost", "jet fuel", "oil price"]
        },
        # Tech Companies
        {
            "nodeId": "company_Anthropic",
            "nodeType": "private_company",
            "name": "Anthropic",
            "aliases": ["Claude AI"],
            "queryTerms": ["Anthropic", "Claude model", "Claude 3"]
        },
        {
            "nodeId": "company_OpenAI",
            "nodeType": "private_company",
            "name": "OpenAI",
            "aliases": ["ChatGPT", "Sora"],
            "queryTerms": ["OpenAI", "ChatGPT", "GPT-5", "Sora"]
        }
    ],
    "edges": [
        # AAPL relationships
        {
            "fromNodeId": "ticker_TSM",
            "toNodeId": "ticker_AAPL",
            "edgeType": "supplier_of",
            "strength": "high",
            "confidence": 0.95,
            "sourceType": "manual_seed",
            "notes": "TSMC is the exclusive manufacturing partner for Apple silicon (A-series and M-series chips).",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "supplier_Foxconn",
            "toNodeId": "ticker_AAPL",
            "edgeType": "supplier_of",
            "strength": "high",
            "confidence": 0.90,
            "sourceType": "manual_seed",
            "notes": "Foxconn is Apple's largest assembly partner for iPhones.",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "theme_semiconductors",
            "toNodeId": "ticker_AAPL",
            "edgeType": "technology_exposure",
            "strength": "medium",
            "confidence": 0.90,
            "sourceType": "manual_seed",
            "notes": "Apple depends heavily on semiconductor supply chains for all hardware products.",
            "lastReviewedAt": "2026-05-28"
        },
        # TSM relationships
        {
            "fromNodeId": "region_Taiwan",
            "toNodeId": "ticker_TSM",
            "edgeType": "regional_exposure",
            "strength": "high",
            "confidence": 0.99,
            "sourceType": "manual_seed",
            "notes": "TSMC operates its advanced semiconductor fabrication facilities (fabs) primarily in Taiwan.",
            "lastReviewedAt": "2026-05-28"
        },
        # NVDA relationships
        {
            "fromNodeId": "ticker_TSM",
            "toNodeId": "ticker_NVDA",
            "edgeType": "supplier_of",
            "strength": "high",
            "confidence": 0.95,
            "sourceType": "manual_seed",
            "notes": "Nvidia relies on TSMC to fabricate its cutting-edge AI and gaming GPUs.",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "theme_semiconductors",
            "toNodeId": "ticker_NVDA",
            "edgeType": "technology_exposure",
            "strength": "high",
            "confidence": 0.99,
            "sourceType": "manual_seed",
            "notes": "Nvidia is a pure-play fabless chip company; semiconductor cycles and tech directly define its revenue.",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "theme_frontier_ai",
            "toNodeId": "ticker_NVDA",
            "edgeType": "technology_exposure",
            "strength": "high",
            "confidence": 0.90,
            "sourceType": "manual_seed",
            "notes": "Nvidia is the dominant hardware supplier (GPUs) for training and deploying frontier AI models.",
            "lastReviewedAt": "2026-05-28"
        },
        # MSFT relationships
        {
            "fromNodeId": "theme_frontier_ai",
            "toNodeId": "ticker_MSFT",
            "edgeType": "technology_exposure",
            "strength": "high",
            "confidence": 0.90,
            "sourceType": "manual_seed",
            "notes": "Microsoft is heavily exposed to Frontier AI through its Azure AI services, Copilot, and alliance with OpenAI.",
            "lastReviewedAt": "2026-05-28"
        },
        # Private AI companies to Frontier AI theme
        {
            "fromNodeId": "company_Anthropic",
            "toNodeId": "theme_frontier_ai",
            "edgeType": "technology_exposure",
            "strength": "high",
            "confidence": 0.95,
            "sourceType": "manual_seed",
            "notes": "Anthropic develops Claude, a leading frontier LLM family, competing directly with OpenAI and Microsoft partners.",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "company_OpenAI",
            "toNodeId": "theme_frontier_ai",
            "edgeType": "technology_exposure",
            "strength": "high",
            "confidence": 0.95,
            "sourceType": "manual_seed",
            "notes": "OpenAI is the developer of ChatGPT and GPT models, driving frontier AI themes.",
            "lastReviewedAt": "2026-05-28"
        },
        # DAL relationships (Logistics/Route)
        {
            "fromNodeId": "route_Red_Sea",
            "toNodeId": "risk_logistics_cost",
            "edgeType": "shipping_exposure",
            "strength": "medium",
            "confidence": 0.85,
            "sourceType": "manual_seed",
            "notes": "Red Sea maritime route disruptions force freight rerouting, driving up global oil, transport, and general logistics costs.",
            "lastReviewedAt": "2026-05-28"
        },
        {
            "fromNodeId": "risk_logistics_cost",
            "toNodeId": "ticker_DAL",
            "edgeType": "macro_sensitivity",
            "strength": "medium",
            "confidence": 0.80,
            "sourceType": "manual_seed",
            "notes": "Delta Air Lines is sensitive to global oil shocks and rising jet fuel costs resulting from logistics and supply chain strains.",
            "lastReviewedAt": "2026-05-28"
        }
    ]
}

SCENARIOS = {
    "direct_news": {
        "name": "Scenario 1: Direct Company Announcements",
        "description": "Simulates standard, direct company-level catalyst news tagged with ticker symbols.",
        "articles": [
            {
                "articleId": "finnhub_direct_001",
                "sourceApi": "finnhub",
                "sourceName": "Finnhub Financial News",
                "url": "https://finnhub.io/news/aapl/m5-announcement",
                "headline": "Apple Inc. (AAPL) Unveils Next-Gen M5 Chip Architecture Engineered with 2nm Tech for On-Device AI",
                "summary": "Today Apple officially announced its M5 chip family, which will power upcoming MacBooks and iPads. The processor leverages TSMC's 2nm lithography to deliver 40% faster local LLM processing and improved thermal efficiency.",
                "publishedAt": "2026-05-28T17:20:00Z",
                "relatedTickers": ["AAPL"]
            },
            {
                "articleId": "finnhub_direct_002",
                "sourceApi": "finnhub",
                "sourceName": "Tech Market Dispatch",
                "url": "https://finnhub.io/news/msft/copilot-revenue",
                "headline": "Microsoft (MSFT) Exceeds Guidance as Copilot Subscriptions Drive 28% Cloud Revenue Expansion",
                "summary": "Microsoft Corp announced its latest financial metrics, showing cloud services grew 28% year over year, heavily boosted by corporate adoption of Microsoft 365 Copilot integrations.",
                "publishedAt": "2026-05-28T17:21:00Z",
                "relatedTickers": ["MSFT"]
            }
        ]
    },
    "duplicate_news": {
        "name": "Scenario 2: Duplicate Spam & Story Updates",
        "description": "Simulates repetitive reports and subsequent story updates to test catalyst ledger deduplication.",
        "articles": [
            {
                "articleId": "finnhub_dup_001",
                "sourceApi": "finnhub",
                "sourceName": "Global Wire News",
                "url": "https://finnhub.io/news/aapl/foxconn-fire",
                "headline": "Fire Reported at Major Electronics Plant in Zhengzhou Assembly Zone; iPhone Lines Affected",
                "summary": "Local emergency services were called to an industrial facility in Zhengzhou. Unconfirmed reports state a small fire broke out in a component warehouse. Authorities say no casualties are reported.",
                "publishedAt": "2026-05-28T17:20:00Z",
                "relatedTickers": ["AAPL"]
            },
            {
                "articleId": "finnhub_dup_002",
                "sourceApi": "finnhub",
                "sourceName": "Syndicated Press Association",
                "url": "https://finnhub.io/news/aapl/zhengzhou-factory-incident",
                "headline": "Factory Incident in Zhengzhou Electronics Zone Challenges Smartphone Supply Chains",
                "summary": "Emergency units responded to a fire in a Zhengzhou electronics manufacturing plant. The incident took place near assembly warehouses. Investigators are examining potential damage to hardware supplies.",
                "publishedAt": "2026-05-28T17:21:30Z",
                "relatedTickers": ["AAPL"]
            },
            {
                "articleId": "finnhub_dup_003",
                "sourceApi": "finnhub",
                "sourceName": "Market Intel Weekly",
                "url": "https://finnhub.io/news/aapl/foxconn-halt",
                "headline": "Update: Foxconn Confirms Zhengzhou Fire Halted Apple iPhone Production Lines; 2M Units Impacted",
                "summary": "Foxconn issued a statement confirming a fire in Zhengzhou factory warehouse, leading to a complete shutdown of advanced assembly lines. Analysts estimate the halt will delay shipment of 2 million iPhone units, representing a high material hit.",
                "publishedAt": "2026-05-28T17:24:00Z",
                "relatedTickers": ["AAPL"]
            }
        ]
    },
    "cross_impact": {
        "name": "Scenario 3: Geopolitical, Tech, & Supply-Chain Cross-Impact",
        "description": "Simulates broad, untickered external events. Checks if the system correctly routes them through the exposure graph.",
        "articles": [
            {
                "articleId": "currents_cross_001",
                "sourceApi": "currents",
                "sourceName": "Taipei Daily Tribune",
                "url": "https://currentsapi.services/news/taiwan-earthquake",
                "headline": "Major 7.2 Magnitude Earthquake Strikes Eastern Taiwan; High-Tech Foundries Evacuate Fabs",
                "summary": "A powerful 7.2 magnitude earthquake shook eastern Taiwan today. High-tech manufacturing facilities in Hsinchu Science Park, including advanced semiconductor silicon fabs, evacuated staff. Initial reports indicate possible precision calibration damage to high-end lithography equipment.",
                "publishedAt": "2026-05-28T17:20:00Z",
                "relatedTickers": []  # Untickered external event!
            },
            {
                "articleId": "currents_cross_002",
                "sourceApi": "currents",
                "sourceName": "AI Innovation Monitor",
                "url": "https://currentsapi.services/news/anthropic-claude",
                "headline": "Anthropic Launches Claude 3.7 Sonnet, Redefining LLM Benchmarks for Complex Reasoning",
                "summary": "Anthropic PBC has officially launched Claude 3.7 Sonnet. The model achieves state-of-the-art results on software engineering, mathematical proofing, and chemical synthesis benchmarks, outperforming comparable open and closed model platforms.",
                "publishedAt": "2026-05-28T17:21:00Z",
                "relatedTickers": []  # Untickered external event!
            },
            {
                "articleId": "currents_cross_003",
                "sourceApi": "currents",
                "sourceName": "Middle East Shipping Journal",
                "url": "https://currentsapi.services/news/red-sea-disruption",
                "headline": "Drone Attacks Force Global Freight Carriers to Abandon Red Sea Routing, Skyrocketing Rates",
                "summary": "Two large cargo ships were targeted by drone strikes near the Bab el-Mandeb strait. In response, major maritime shipping alliances announced a complete suspension of Red Sea and Suez Canal routes, directing vessels around the Cape of Good Hope. Spot container rates surged 30% along with oil logistics surcharges.",
                "publishedAt": "2026-05-28T17:22:00Z",
                "relatedTickers": []  # Untickered external event!
            }
        ]
    }
}
