from typing import List, Dict, Any, Tuple
import numpy as np
from datetime import datetime, timezone, timedelta
from backend.config import GEMINI_API_KEY, OPENAI_API_KEY, LLM_PROVIDER

# In-memory storage for the Catalyst Ledger entries
_ledger_store: List[Dict[str, Any]] = []

def get_ledger() -> List[Dict[str, Any]]:
    """Returns all active ledger entries."""
    # Clean up expired items first
    now = datetime.now(timezone.utc)
    for entry in _ledger_store:
        exp_time = datetime.fromisoformat(entry["expiresAt"])
        if now > exp_time:
            entry["status"] = "expired"
    return [entry for entry in _ledger_store if entry["status"] == "live"]

def clear_ledger():
    """Clears the ledger store."""
    global _ledger_store
    _ledger_store = []

def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculates cosine similarity between two vectors."""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return float(dot_product / (norm_v1 * norm_v2))

_gemini_embedding_failed = False

def get_text_embedding(text: str) -> List[float]:
    """
    Generates embedding vector for a given text using LangChain Google/OpenAI embedding models.
    Falls back to a deterministic hash-based bag-of-words vector if keys are missing or API fails.
    All calls are traced via OpenTelemetry so Arize Phoenix can monitor embedding latency and usage.
    """
    global _gemini_embedding_failed

    # Start an explicit OTel span so Phoenix captures embedding calls
    # (LangChainInstrumentor only covers chat models, not standalone embed_query calls)
    try:
        from opentelemetry import trace as otel_trace
        tracer = otel_trace.get_tracer("catalyst-memory")
    except Exception:
        tracer = None

    def _do_embed() -> List[float]:
        if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
            from langchain_openai import OpenAIEmbeddings
            embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY, model="text-embedding-3-small")
            return embeddings.embed_query(text)
        elif GEMINI_API_KEY and not _gemini_embedding_failed:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            embeddings = GoogleGenerativeAIEmbeddings(google_api_key=GEMINI_API_KEY, model="models/embedding-001")
            return embeddings.embed_query(text)
        raise RuntimeError("No embedding provider available")

    # Determine provider label for span attributes
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        provider_label = "openai"
        model_label = "text-embedding-3-small"
    elif GEMINI_API_KEY and not _gemini_embedding_failed:
        provider_label = "google_gemini"
        model_label = "models/embedding-001"
    else:
        provider_label = "fallback_hash_bow"
        model_label = "token-hash-128"

    if tracer:
        with tracer.start_as_current_span("catalyst.embedding") as span:
            span.set_attribute("embedding.provider", provider_label)
            span.set_attribute("embedding.model", model_label)
            span.set_attribute("embedding.input_chars", len(text))
            span.set_attribute("embedding.is_fallback", _gemini_embedding_failed)
            try:
                vec = _do_embed()
                span.set_attribute("embedding.dimensions", len(vec))
                span.set_attribute("embedding.status", "success")
                return vec
            except Exception as e:
                if not _gemini_embedding_failed:
                    print(f"Embedding API failed or not configured, disabling and using fallback: {e}")
                    _gemini_embedding_failed = True
                span.set_attribute("embedding.status", "fallback")
                span.set_attribute("embedding.error", str(e))
    else:
        try:
            return _do_embed()
        except Exception as e:
            if not _gemini_embedding_failed:
                print(f"Embedding API failed or not configured, disabling and using fallback: {e}")
                _gemini_embedding_failed = True

    # Fallback: simple token-frequency embedding representation (size 128)
    vector = [0.0] * 128
    words = text.lower().split()
    for word in words:
        # Simple hash routing to generate a pseudo-random but deterministic feature index
        idx = hash(word) % 128
        vector[idx] += 1.0
    # Normalize vector
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = [v / norm for v in vector]
    return list(vector)


def get_jaccard_similarity(str1: str, str2: str) -> float:
    """Calculates word-level Jaccard similarity between two strings."""
    set1 = set(str1.lower().split())
    set2 = set(str2.lower().split())
    if not set1 or not set2:
        return 0.0
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return len(intersection) / len(union)

def check_for_new_facts(event_facts: List[str], ledger_facts: List[str]) -> Tuple[bool, List[str]]:
    """
    Compares event facts against already seen facts in the ledger entry.
    Returns (has_new_facts, list_of_new_facts).
    A fact is considered 'new' if its word-level Jaccard similarity is less than 0.6
    relative to ALL existing facts in the ledger entry.
    """
    new_facts = []
    has_new_facts = False
    
    for ef in event_facts:
        is_duplicate = False
        for lf in ledger_facts:
            sim = get_jaccard_similarity(ef, lf)
            if sim >= 0.6:
                is_duplicate = True
                break
        if not is_duplicate:
            new_facts.append(ef)
            has_new_facts = True
            
    return has_new_facts, new_facts

def check_ledger_decision(ticker: str, canonical_event: Dict[str, Any], similarity_threshold: float = 0.75) -> Tuple[str, str, List[str]]:
    """
    Checks the incoming event against the active catalyst ledger.
    Returns a tuple: (decision, catalyst_id, list_of_new_facts)
    decision can be: "new" | "update" | "duplicate"
    """
    event_summary = canonical_event.get("eventSummary", "")
    event_type = canonical_event.get("eventType", "")
    event_facts = canonical_event.get("hardFacts", [])
    
    # Ingesting articles can have related article IDs
    article_ids = canonical_event.get("sourceArticleIds", [])
    
    # 1. Fetch active ledger entries for this specific ticker & event_type
    active_entries = [
        entry for entry in _ledger_store 
        if entry["ticker"] == ticker and entry["eventType"] == event_type and entry["status"] == "live"
    ]
    
    # Calculate embedding for the current event summary
    event_embedding = get_text_embedding(event_summary)
    
    best_entry = None
    highest_sim = 0.0
    
    for entry in active_entries:
        entry_emb = entry.get("embedding_vec")
        if not entry_emb:
            continue
        sim = calculate_cosine_similarity(event_embedding, entry_emb)
        if sim > highest_sim:
            highest_sim = sim
            best_entry = entry

    # If similarity is above the threshold, it is the same catalyst thread
    if best_entry and highest_sim >= similarity_threshold:
        catalyst_id = best_entry["catalystId"]
        
        # Check if there are new hard facts
        has_new_facts, new_facts = check_for_new_facts(event_facts, best_entry["hardFactsSeen"])
        
        if has_new_facts:
            # Update ledger entry
            best_entry["lastUpdatedAt"] = datetime.now(timezone.utc).isoformat()
            best_entry["memberArticleIds"] = list(set(best_entry["memberArticleIds"] + article_ids))
            best_entry["hardFactsSeen"] = list(set(best_entry["hardFactsSeen"] + event_facts))
            best_entry["canonicalSummary"] = f"{best_entry['canonicalSummary']} Update: {event_summary}"
            # Recalculate embedding with updated summary
            best_entry["embedding_vec"] = get_text_embedding(best_entry["canonicalSummary"])
            return "update", catalyst_id, new_facts
        else:
            # Suppress as duplicate, but log the article reference
            best_entry["memberArticleIds"] = list(set(best_entry["memberArticleIds"] + article_ids))
            return "duplicate", catalyst_id, []
            
    # If similarity is below threshold, create a new catalyst entry
    catalyst_id = f"cat_{ticker}_{int(datetime.now().timestamp())}_{len(_ledger_store)}"
    now_str = datetime.now(timezone.utc).isoformat()
    expires_str = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat() # 1 day TTL
    
    new_entry = {
        "catalystId": catalyst_id,
        "ticker": ticker,
        "eventType": event_type,
        "relationshipType": "direct" if len(canonical_event.get("relatedTickers", [])) > 0 else "indirect",
        "canonicalSummary": event_summary,
        "embedding_vec": event_embedding,
        "firstSeenAt": now_str,
        "lastUpdatedAt": now_str,
        "expiresAt": expires_str,
        "memberArticleIds": article_ids,
        "hardFactsSeen": event_facts,
        "status": "live"
    }
    _ledger_store.append(new_entry)
    
    return "new", catalyst_id, event_facts
