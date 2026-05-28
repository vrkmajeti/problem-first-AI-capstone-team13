import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys & Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY", "")

PHOENIX_PORT = int(os.getenv("PHOENIX_PORT", "6006"))
PHOENIX_PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME", "cross-impact-catalysts")

# Global variables to track Phoenix session
phoenix_session = None

def init_phoenix():
    """Initializes Arize Phoenix tracing internally."""
    global phoenix_session
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        import phoenix as px
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor

        # Register the tracing collector
        register(project_name=PHOENIX_PROJECT_NAME)
        
        # Instrument LangChain & LangGraph
        LangChainInstrumentor().instrument()

        # Check if already running or initialize in a background thread
        print(f"Initializing Arize Phoenix on port {PHOENIX_PORT} in background thread...")
        import threading
        def run_phoenix():
            global phoenix_session
            try:
                phoenix_session = px.launch_app(port=PHOENIX_PORT)
                print(f"Arize Phoenix dashboard running at: http://localhost:{PHOENIX_PORT}")
            except Exception as ex:
                print(f"Phoenix background launch error: {ex}")
                
        threading.Thread(target=run_phoenix, daemon=True).start()
    except Exception as e:
        print(f"Warning: Failed to initialize Arize Phoenix: {e}")
        print("Traces will not be captured.")

def get_llm():
    """Returns the configured LLM based on LLM_PROVIDER."""
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in the environment.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini", temperature=0.0)
    else:
        # Default is Gemini
        if not GEMINI_API_KEY:
            # We check if OPENAI_API_KEY is available as a fallback
            if OPENAI_API_KEY:
                print("Warning: GEMINI_API_KEY is not set but OPENAI_API_KEY is. Falling back to OpenAI.")
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini", temperature=0.0)
            else:
                raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is set.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(google_api_key=GEMINI_API_KEY, model="gemini-1.5-flash", temperature=0.0)
