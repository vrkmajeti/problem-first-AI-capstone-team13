import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timezone

from backend.graph import build_workflow_graph, clean_json_string
from backend.seed_data import SCENARIOS, EXPOSURE_GRAPH
from backend.memory import clear_ledger

# Mock LLM response class
class MockResponse:
    def __init__(self, content: str):
        self.content = content

class TestWorkflow(unittest.TestCase):
    def setUp(self):
        clear_ledger()
        self.workflow = build_workflow_graph()
        self.watchlist = ["AAPL", "MSFT", "NVDA", "TSM", "DAL"]

    def mock_llm_invoke(self, messages):
        system_msg = messages[0].content
        user_msg = messages[1].content
        
        # A. Canonical Extraction Mocking
        if "extract a canonical structured event representation" in system_msg:
            extracted = []
            
            # Helper to check article properties and map them
            if "m5-announcement" in user_msg or "M5 Chip" in user_msg or "finnhub_direct_001" in user_msg:
                event = {
                    "articleId": "finnhub_direct_001",
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
                }
                extracted.append(event)
                
            if "copilot-revenue" in user_msg or "Copilot Subscriptions" in user_msg or "finnhub_direct_002" in user_msg:
                event = {
                    "articleId": "finnhub_direct_002",
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
                }
                extracted.append(event)
                
            if "foxconn-fire" in user_msg or "Zhengzhou Assembly Zone" in user_msg or "finnhub_dup_001" in user_msg:
                event = {
                    "articleId": "finnhub_dup_001",
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
                }
                extracted.append(event)
                
            if "factory-incident" in user_msg or "Zhengzhou Electronics Zone" in user_msg or "finnhub_dup_002" in user_msg:
                event = {
                    "articleId": "finnhub_dup_002",
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
                }
                extracted.append(event)
                
            if "foxconn-halt" in user_msg or "Zhengzhou Fire Halted" in user_msg or "finnhub_dup_003" in user_msg:
                event = {
                    "articleId": "finnhub_dup_003",
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
                }
                extracted.append(event)
                
            if "taiwan-earthquake" in user_msg or "currents_cross_001" in user_msg:
                event = {
                    "articleId": "currents_cross_001",
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
                }
                extracted.append(event)
                
            if "anthropic-claude" in user_msg or "currents_cross_002" in user_msg:
                event = {
                    "articleId": "currents_cross_002",
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
                }
                extracted.append(event)
                
            if "red-sea-disruption" in user_msg or "currents_cross_003" in user_msg:
                event = {
                    "articleId": "currents_cross_003",
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
                extracted.append(event)
                
            return MockResponse(json.dumps(extracted))

        # B. Synthesis Mocking
        elif "review the direct and indirect catalyst events" in system_msg:
            # Parse input to find ticker
            ticker = "UNKNOWN"
            for line in user_msg.split('\n'):
                if "TICKER CONFIG:" in line:
                    ticker = line.replace("TICKER CONFIG:", "").strip()
            
            return MockResponse(json.dumps({
                "summaryHeadline": f"Catalysts analyzed for {ticker}",
                "situationSummary": f"Analyzed latest direct and indirect events affecting {ticker}.",
                "mainCatalysts": [
                    {
                        "label": "Test Catalyst",
                        "relationshipType": "direct",
                        "eventType": "supply_chain",
                        "possibleInfluence": "positive",
                        "confidence": "high"
                    }
                ],
                "overallPossibleInfluence": "positive",
                "confidence": "medium",
                "uncertainties": ["Market volatility."],
                "watchItems": ["Volume indicators."]
            }))

        raise ValueError(f"Mock got unexpected message patterns: {messages}")

    @patch('backend.graph.get_llm_fast')
    @patch('backend.graph.get_llm')
    def test_iteration_1_direct_news(self, mock_get_llm, mock_get_llm_fast):
        """Test Iteration 1 direct company news path without duplicates."""
        mock_llm = MagicMock()
        mock_llm.invoke = self.mock_llm_invoke
        mock_get_llm.return_value = mock_llm
        # Extraction (Node 2) uses get_llm_fast; mock it too so the test is deterministic
        # and does not hit the real LLM API.
        mock_get_llm_fast.return_value = mock_llm

        initial_state = {
            "iteration": 1,
            "watchlist": self.watchlist,
            "scenario_id": "direct_news",
            "simulated_now": "2026-05-28T17:25:00Z",
            "articles": [],
            "canonical_events": [],
            "routed_candidates": [],
            "ticker_buckets": {},
            "ticker_syntheses": {},
            "duplicate_counts": {},
            "ingestion_metadata": {}
        }
        
        final_state = self.workflow.invoke(initial_state)
        
        # Assertions
        self.assertEqual(len(final_state["articles"]), 2)
        self.assertEqual(len(final_state["canonical_events"]), 2)
        # Check direct routing
        routed = final_state["routed_candidates"]
        self.assertTrue(any(r["ticker"] == "AAPL" and r["relationshipType"] == "direct" for r in routed))
        self.assertTrue(any(r["ticker"] == "MSFT" and r["relationshipType"] == "direct" for r in routed))
        
        # Check syntheses are present for watchlist
        self.assertIn("AAPL", final_state["ticker_syntheses"])
        self.assertIn("MSFT", final_state["ticker_syntheses"])

    @patch('backend.graph.get_llm_fast')
    @patch('backend.graph.get_llm')
    def test_iteration_2_ledger_duplicates(self, mock_get_llm, mock_get_llm_fast):
        """Test Iteration 2 catalyst memory deduplication and update detection."""
        mock_llm = MagicMock()
        mock_llm.invoke = self.mock_llm_invoke
        mock_get_llm.return_value = mock_llm
        mock_get_llm_fast.return_value = mock_llm

        initial_state = {
            "iteration": 2,
            "watchlist": self.watchlist,
            "scenario_id": "duplicate_news",
            "simulated_now": "2026-05-28T17:25:00Z",
            "articles": [],
            "canonical_events": [],
            "routed_candidates": [],
            "ticker_buckets": {},
            "ticker_syntheses": {},
            "duplicate_counts": {},
            "ingestion_metadata": {}
        }
        
        final_state = self.workflow.invoke(initial_state)
        
        # In duplicate_news scenario:
        # Article 1: Zhengzhou Fire (evt_finnhub_dup_001) -> new
        # Article 2: Zhengzhou fire incident (evt_finnhub_dup_002) -> duplicate
        # Article 3: Zhengzhou fire halts line (evt_finnhub_dup_003) -> update
        
        self.assertEqual(len(final_state["articles"]), 3)
        self.assertEqual(len(final_state["canonical_events"]), 3)
        
        # Duplicate count for AAPL should be 1
        self.assertEqual(final_state["duplicate_counts"].get("AAPL", 0), 1)

    @patch('backend.graph.get_llm_fast')
    @patch('backend.graph.get_llm')
    def test_iteration_3_cross_impact_routing(self, mock_get_llm, mock_get_llm_fast):
        """Test Iteration 3 cross impact graph routing for untickered events."""
        mock_llm = MagicMock()
        mock_llm.invoke = self.mock_llm_invoke
        mock_get_llm.return_value = mock_llm
        mock_get_llm_fast.return_value = mock_llm

        initial_state = {
            "iteration": 3,
            "watchlist": self.watchlist,
            "scenario_id": "cross_impact",
            "simulated_now": "2026-05-28T17:25:00Z",
            "articles": [],
            "canonical_events": [],
            "routed_candidates": [],
            "ticker_buckets": {},
            "ticker_syntheses": {},
            "duplicate_counts": {},
            "ingestion_metadata": {}
        }
        
        final_state = self.workflow.invoke(initial_state)
        
        self.assertEqual(len(final_state["articles"]), 3)
        
        # Verify cross impact candidate paths
        routed = final_state["routed_candidates"]
        
        # 1. Taiwan Earthquake should route to AAPL, NVDA, and TSM via semiconductor chain (eventId: evt_currents_cross_001)
        earthquake_routes = [r for r in routed if "evt_currents_cross_001" in r["eventId"]]
        self.assertTrue(any(r["ticker"] == "AAPL" for r in earthquake_routes))
        self.assertTrue(any(r["ticker"] == "NVDA" for r in earthquake_routes))
        self.assertTrue(any(r["ticker"] == "TSM" for r in earthquake_routes))
        
        # 2. Anthropic model launch should route to MSFT and NVDA via Frontier AI theme (eventId: evt_currents_cross_002)
        anthropic_routes = [r for r in routed if "evt_currents_cross_002" in r["eventId"]]
        self.assertTrue(any(r["ticker"] == "MSFT" for r in anthropic_routes))
        self.assertTrue(any(r["ticker"] == "NVDA" for r in anthropic_routes))
        
        # 3. Red Sea Disruption should route to DAL via Logistics Cost Risk -> Airline sensitivities (eventId: evt_currents_cross_003)
        redsea_routes = [r for r in routed if "evt_currents_cross_003" in r["eventId"]]
        self.assertTrue(any(r["ticker"] == "DAL" for r in redsea_routes))

if __name__ == "__main__":
    unittest.main()
