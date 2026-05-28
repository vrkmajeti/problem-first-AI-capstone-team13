import math
import os
import re
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone, timedelta

import numpy as np

# In-memory storage for the Catalyst Ledger entries
_ledger_store: List[Dict[str, Any]] = []

# ----------------------------------------------------------------------------
# Catalyst near-duplicate detection engine
# ----------------------------------------------------------------------------
# Previously every candidate event triggered a paid/quota'd REMOTE embedding API
# call (Gemini embedding-001 / OpenAI text-embedding-3-small). That was the main
# recurring cost in the dedup path. It is replaced by a LOCAL engine with $0/call:
#
#   Primary  : local ONNX embedding model via `fastembed` (BAAI/bge-small-en-v1.5,
#              384 dims). Downloaded once (~50 MB), then runs offline on CPU with no
#              network call and no per-call cost. Preserves the semantic dedup quality
#              of the old API path — it catches paraphrased duplicates of the same
#              catalyst that a purely lexical match would miss.
#   Fallback : deterministic lexical token-frequency cosine (`calculate_text_similarity`).
#              Zero extra dependencies. Used automatically if the embedding model cannot
#              be loaded (e.g. offline first-run with no cached model). Lower recall on
#              heavy paraphrases but fully deterministic and auditable.
#
# Either way there is no remote embedding API and no ongoing embedding cost.

# Embedding model name (overridable via env for experimentation).
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Lazily-initialised singleton + availability flag.
_embedding_model = None
_embedding_unavailable = False

# Small English stopword set so common filler words don't inflate similarity scores.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was",
    "were", "will", "with",
})


def _tokenize(text: str) -> List[str]:
    """Lowercase, alphanumeric tokenization with stopword removal."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _get_embedding_model():
    """Lazily load the local fastembed model. Returns None if unavailable."""
    global _embedding_model, _embedding_unavailable
    if _embedding_unavailable:
        return None
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
            _embedding_model = TextEmbedding(model_name=_EMBEDDING_MODEL_NAME)
        except Exception as e:
            print(f"Local embedding model unavailable ({e}). Falling back to lexical similarity.")
            _embedding_unavailable = True
            return None
    return _embedding_model


def is_embedding_active() -> bool:
    """Whether the local neural embedding engine is loaded and in use (vs lexical fallback)."""
    return _get_embedding_model() is not None


def get_text_embedding(text: str) -> Optional[List[float]]:
    """
    Returns a local embedding vector for `text`, or None if the embedding model is
    unavailable (in which case callers fall back to lexical similarity).

    Wrapped in an OpenTelemetry span so Arize Phoenix still captures dedup embedding
    activity — now as a $0 local CPU computation rather than a remote API call.
    """
    model = _get_embedding_model()
    if model is None:
        return None

    try:
        from opentelemetry import trace as otel_trace
        tracer = otel_trace.get_tracer("catalyst-memory")
    except Exception:
        tracer = None

    def _embed() -> List[float]:
        # fastembed returns a generator of numpy arrays
        vec = next(iter(model.embed([text])))
        return [float(x) for x in vec]

    if tracer:
        with tracer.start_as_current_span("catalyst.embedding") as span:
            span.set_attribute("embedding.provider", "local_fastembed")
            span.set_attribute("embedding.model", _EMBEDDING_MODEL_NAME)
            span.set_attribute("embedding.input_chars", len(text))
            vec = _embed()
            span.set_attribute("embedding.dimensions", len(vec))
            span.set_attribute("embedding.status", "success")
            return vec
    return _embed()


def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    v1 = np.asarray(vec1, dtype=float)
    v2 = np.asarray(vec2, dtype=float)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


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

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Deterministic lexical similarity between two short texts using token-frequency
    (term-frequency) cosine similarity.

    This is the FALLBACK matcher, used when the local neural embedding model is not
    available. There are no fixed-size vectors and no hashing, so there are no
    collisions: each text is represented as a sparse Counter of its (stopword-filtered)
    tokens, and cosine is computed over the shared vocabulary. Returns a value in
    [0.0, 1.0].

    The call is wrapped in an OpenTelemetry span so Arize Phoenix still shows catalyst
    dedup activity (a near-zero-latency local computation, no API call).
    """
    try:
        from opentelemetry import trace as otel_trace
        tracer = otel_trace.get_tracer("catalyst-memory")
    except Exception:
        tracer = None

    def _compute() -> float:
        c1 = Counter(_tokenize(text1))
        c2 = Counter(_tokenize(text2))
        if not c1 or not c2:
            return 0.0
        common = set(c1) & set(c2)
        dot = sum(c1[t] * c2[t] for t in common)
        if dot == 0:
            return 0.0
        norm1 = math.sqrt(sum(v * v for v in c1.values()))
        norm2 = math.sqrt(sum(v * v for v in c2.values()))
        return dot / (norm1 * norm2)

    if tracer:
        with tracer.start_as_current_span("catalyst.similarity") as span:
            span.set_attribute("similarity.method", "lexical_tf_cosine")
            span.set_attribute("similarity.input_chars", len(text1) + len(text2))
            score = _compute()
            span.set_attribute("similarity.score", score)
            return score
    return _compute()


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
    
    # Compute the local embedding of the incoming summary once (None if model unavailable).
    event_embedding = get_text_embedding(event_summary)

    best_entry = None
    highest_sim = 0.0

    for entry in active_entries:
        entry_summary = entry.get("canonicalSummary", "")
        if not entry_summary:
            continue
        entry_emb = entry.get("embedding_vec")
        if event_embedding is not None and entry_emb:
            # Primary path: semantic cosine over local embedding vectors.
            sim = calculate_cosine_similarity(event_embedding, entry_emb)
        else:
            # Fallback path: deterministic lexical cosine over summaries.
            sim = calculate_text_similarity(event_summary, entry_summary)
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
            # Refresh the stored embedding to reflect the updated summary (no-op under lexical fallback).
            updated_emb = get_text_embedding(best_entry["canonicalSummary"])
            if updated_emb is not None:
                best_entry["embedding_vec"] = updated_emb
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
