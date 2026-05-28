# Intraday Cross-Impact Catalyst Briefings Demo

This repository contains the interactive demo for the **Intraday Cross-Impact Catalyst Briefings** capstone project. It implements a Python backend utilizing LangGraph and Arize Phoenix tracing, alongside a Vite + React frontend dashboard.

---

## Repository Structure

```text
d:\git\problem-first-AI-capstone-team13/
├── backend/
│   ├── requirements.txt      # Python dependencies
│   ├── .env.example          # Environment variables template
│   ├── main.py               # FastAPI server and routes
│   ├── config.py             # App configurations & Phoenix tracing
│   ├── ingestion.py          # API clients and scenario replay engine
│   ├── routing.py            # Exposure graph path traversal
│   ├── memory.py             # Catalyst ledger memory
│   ├── graph.py              # LangGraph pipeline definition
│   └── seed_data.py          # Seeded exposure graph and replay articles
├── frontend/
│   ├── package.json          # Node dependencies
│   ├── vite.config.ts        # Vite configuration & proxy settings
│   ├── index.html            # Entry HTML page
│   └── src/
│       ├── main.tsx          # React initialization
│       ├── App.tsx           # Dashboard logic & controls
│       ├── index.css         # Dark-themed custom stylesheet
│       └── components/       # Component modular layout files
├── README.md                 # Setup and run guide
└── implementation_plan.md    # Original technical design plan
```

---

## Setup & Running the Application

### 1. Python Backend
1. Initialize a Python virtual environment:
   ```bash
   python -m venv backend/.venv
   ```
2. Activate the virtual environment:
   * **Windows (PowerShell):** `.\backend\.venv\Scripts\Activate.ps1`
   * **Windows (CMD):** `backend\.venv\Scripts\activate.bat`
   * **macOS/Linux:** `source backend/.venv/bin/activate`
3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
4. Setup environment keys:
   * Copy `backend/.env.example` to `backend/.env`.
   * (Optional) Enter `GEMINI_API_KEY` or `OPENAI_API_KEY` for live LLM workflows. If keys are omitted, the application will run in a **No-Key Replay Mode** using high-fidelity rules-based mocks for seed scenarios.
5. Start the backend server:
   ```bash
   python -m backend.main
   ```
   * FastAPI backend will run on **`http://localhost:8000`**.
   * Arize Phoenix dashboard will run on **`http://localhost:6006`**.

### 2. React Frontend
1. Open a new terminal and navigate to the `frontend/` folder:
   ```bash
   cd frontend
   ```
2. Install package manager dependencies:
   ```bash
   npm install
   ```
3. Start the dev server:
   ```bash
   npm run dev
   ```
4. Open your browser to **`http://localhost:5173/`**.

### Running with VS Code

To make running and debugging easy, we have pre-configured VS Code tasks and debug launches under the `.vscode/` directory:

1. **Install Dependencies:**
   - Run task `Install Backend Requirements` to set up python packages.
   - Run task `Install Frontend Dependencies` to set up frontend node modules.
2. **Run the Whole App:**
   - Go to the **Run and Debug** panel in VS Code (`Ctrl+Shift+D`).
   - Select **`Full Application (Backend + Frontend)`** from the dropdown.
   - Click the green play button. This launches Uvicorn (FastAPI) and Vite (React) concurrently and opens the terminals.
3. **Run Tests:**
   - Select **`Backend: Run Unit Tests`** from the Run and Debug dropdown and press play.

---

## Running Verification Tests

To verify that the LangGraph workflow, duplicate suppression, and cross-impact routing function correctly, run the unit test suite:
```bash
backend\.venv\Scripts\python -m unittest backend/run_tests.py
```

---

## Demonstrating the Three Iterations

The React interface allows you to run all three pipeline flows described in the system design:

1. **Iteration 1: Direct News Synthesis**
   * Select `Iteration 1` and `Replay Scenario 1: Direct Announcements`.
   * Click **Fetch Catalysts**. Direct company news is extracted and synthesized directly.
2. **Iteration 2: Catalyst Memory Dedup**
   * Select `Iteration 2` and `Replay Scenario 2: Duplicate Articles`.
   * Click **Fetch Catalysts**. The ledger correctly detects duplicates (suppressed) and updates (emits an update card).
3. **Iteration 3: Graph Cross-Impact Routing**
   * Select `Iteration 3` and `Replay Scenario 3: Untickered Geopolitical/Tech`.
   * Click **Fetch Catalysts**. The system queries broad news and traverses the exposure graph. Hovering over a card highlights its path (e.g., `Taiwan` -> `TSMC` -> `AAPL`) in the SVG Graph!
