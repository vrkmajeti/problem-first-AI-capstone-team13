import os
from dotenv import load_dotenv

# Load environment variables (supports root and backend folder)
load_dotenv()
backend_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(backend_env_path):
    load_dotenv(backend_env_path, override=True)

# API Keys & Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY", "")

PHOENIX_PORT = int(os.getenv("PHOENIX_PORT", "6006"))
PHOENIX_PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME", "cross-impact-catalysts")
FRESHNESS_LOOKBACK_MINUTES = int(os.getenv("FRESHNESS_LOOKBACK_MINUTES", "10"))

# Global variables to track Phoenix session
phoenix_session = None

def init_phoenix():
    """Initializes Arize Phoenix tracing by registering the OTel provider."""
    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor

        # Register the tracing collector (sends to localhost:4317 by default)
        print("Registering Arize Phoenix OpenTelemetry tracing provider...")
        register(project_name=PHOENIX_PROJECT_NAME)
        
        # Instrument LangChain & LangGraph
        LangChainInstrumentor().instrument()
        print("Arize Phoenix OpenTelemetry tracing provider registered successfully.")
    except Exception as e:
        print(f"Warning: Failed to initialize Arize Phoenix OpenTelemetry provider: {e}")
        print("Traces will not be captured.")

def get_llm():
    """Returns the reasoning-capable LLM (used for synthesis, complex tasks)."""
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in the environment.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini", temperature=0.0)
    else:
        # Default is Gemini
        if not GEMINI_API_KEY:
            if OPENAI_API_KEY:
                print("Warning: GEMINI_API_KEY is not set but OPENAI_API_KEY is. Falling back to OpenAI.")
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini", temperature=0.0)
            else:
                raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is set.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(google_api_key=GEMINI_API_KEY, model="gemini-2.5-flash", temperature=0.0)

def get_llm_fast():
    """Returns a faster/cheaper LLM for simple structured extraction tasks.
    OpenAI: gpt-4.1-nano  |  Gemini: gemini-2.5-flash (same, flash is already fast)
    """
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in the environment.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4.1-nano", temperature=0.0)
    else:
        # Gemini flash is already the fast/cheap tier — reuse it
        if not GEMINI_API_KEY:
            if OPENAI_API_KEY:
                print("Warning: GEMINI_API_KEY is not set but OPENAI_API_KEY is. Falling back to OpenAI nano.")
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4.1-nano", temperature=0.0)
            else:
                raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is set.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(google_api_key=GEMINI_API_KEY, model="gemini-2.5-flash", temperature=0.0)
