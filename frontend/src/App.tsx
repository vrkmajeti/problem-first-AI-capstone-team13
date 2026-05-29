import React, { useState, useEffect } from 'react';
import { Play, RotateCcw, Plus, Trash2, ExternalLink, Network, Database, ShieldAlert, Cpu, Layers, Maximize2, X, RefreshCw } from 'lucide-react';

interface Catalyst {
  label: string;
  relationshipType: 'direct' | 'indirect';
  eventType: string;
  possibleInfluence: 'positive' | 'negative' | 'mixed' | 'unclear';
  confidence: 'low' | 'medium' | 'high' | 'tentative';
  impactPath?: string[];
}

interface TickerSummary {
  summaryId: string;
  ticker: string;
  summaryHeadline: string;
  situationSummary: string;
  mainCatalysts: Catalyst[];
  overallPossibleInfluence: 'positive' | 'negative' | 'mixed' | 'unclear';
  confidence: 'low' | 'medium' | 'high' | 'tentative';
  uncertainties: string[];
  watchItems: string[];
  sourceEventIds: string[];
  sourceArticleUrls: string[];
  complianceDisclaimer?: string;
  notFinancialAdvice: boolean;
}

interface EventEntry {
  eventId: string;
  eventType: string;
  headline: string;
  eventSummary: string;
  hardFacts: string[];
  possibleDirectionalPressure: 'positive' | 'negative' | 'mixed' | 'unclear';
  sourceArticleIds: string[];
  sourceUrl?: string;
  impactPath?: string[];
  reasonForRouting?: string;
  pathConfidence?: number;
}

interface TickerBucket {
  ticker: string;
  directEvents: EventEntry[];
  crossImpactEvents: EventEntry[];
  suppressedDuplicateCount: number;
}

interface RunResult {
  runId: string;
  iteration: number;
  watchlist: string[];
  articlesCount: number;
  eventsCount: number;
  routedCount: number;
  duplicateCounts: Record<string, number>;
  tickerSyntheses: Record<string, TickerSummary>;
  rawArticles: any[];
  canonicalEvents: any[];
  routedCandidates: any[];
  tickerBuckets: Record<string, TickerBucket>;
}

interface GraphNode {
  nodeId: string;
  nodeType: string;
  name: string;
  queryTerms: string[];
}

interface GraphEdge {
  fromNodeId: string;
  toNodeId: string;
  edgeType: string;
  strength: string;
  confidence: number;
  notes?: string;
}

interface ExposureGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

type ExpansionStatus = Record<string, { ticker: string; status: string; error?: string; addedNodes?: number; addedEdges?: number; updatedAt?: string }>;

// ---------------------------------------------------------------------------
// Exposure-graph layout + rendering (shared by the sidebar card and the modal)
// ---------------------------------------------------------------------------
const MID_NODE_TYPES = ['technology_theme', 'private_company', 'sector'];

// Evenly distribute nodes into 3 columns (source factors -> themes/companies -> tickers)
// and space them vertically by column count so the canvas never overlaps regardless of size.
function computeLayout(nodes: GraphNode[], width: number, height: number) {
  const padX = Math.max(38, width * 0.1);
  const padY = Math.max(18, height * 0.06);
  const cols: { left: GraphNode[]; mid: GraphNode[]; right: GraphNode[] } = { left: [], mid: [], right: [] };
  for (const n of nodes) {
    if (n.nodeType === 'ticker') cols.right.push(n);
    else if (MID_NODE_TYPES.includes(n.nodeType)) cols.mid.push(n);
    else cols.left.push(n);
  }
  const xs = { left: padX, mid: width / 2, right: width - padX };
  const positions = new Map<string, { x: number; y: number }>();
  (['left', 'mid', 'right'] as const).forEach(col => {
    const arr = cols[col];
    arr.forEach((n, i) => {
      const y = padY + (height - 2 * padY) * (i + 1) / (arr.length + 1);
      positions.set(n.nodeId, { x: xs[col], y });
    });
  });
  return positions;
}

function getNodeColor(nodeType: string, isHighlighted: boolean) {
  if (isHighlighted) return 'var(--accent-purple)';
  switch (nodeType) {
    case 'ticker': return 'var(--accent-purple)';
    case 'technology_theme': return 'var(--accent-blue)';
    case 'private_company': return 'var(--accent-cyan)';
    case 'sector': return 'var(--accent-cyan)';
    default: return 'var(--accent-orange)'; // region, risk_factor, shipping_route, commodity
  }
}

function GraphView({ graphData, width, height, scale = 1, selectedCatalystPath }: {
  graphData: ExposureGraph;
  width: number;
  height: number;
  scale?: number;
  selectedCatalystPath: string[] | null;
}) {
  if (graphData.nodes.length === 0) {
    return <div className="canvas-placeholder">Loading graph nodes...</div>;
  }
  const positions = computeLayout(graphData.nodes, width, height);
  const fontSize = 6.5 * scale;
  const nodeById = new Map(graphData.nodes.map(n => [n.nodeId, n]));

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" style={{ background: '#07080d' }}>
      {/* Edges */}
      {graphData.edges.map((edge, idx) => {
        const fromPos = positions.get(edge.fromNodeId);
        const toPos = positions.get(edge.toNodeId);
        if (!fromPos || !toPos) return null;

        let isHighlighted = false;
        if (selectedCatalystPath) {
          const fromNode = nodeById.get(edge.fromNodeId);
          const toNode = nodeById.get(edge.toNodeId);
          if (fromNode && toNode) {
            const fromIdx = selectedCatalystPath.indexOf(fromNode.name);
            const toIdx = selectedCatalystPath.indexOf(toNode.name);
            if (fromIdx !== -1 && toIdx !== -1 && Math.abs(fromIdx - toIdx) === 1) isHighlighted = true;
          }
        }

        return (
          <line
            key={idx}
            x1={fromPos.x} y1={fromPos.y} x2={toPos.x} y2={toPos.y}
            stroke={isHighlighted ? 'var(--accent-cyan)' : '#27272a'}
            strokeWidth={(isHighlighted ? 2.5 : 1) * scale}
            strokeDasharray={edge.edgeType.includes('exposure') ? `${3 * scale},${3 * scale}` : 'none'}
            opacity={selectedCatalystPath && !isHighlighted ? 0.2 : 0.8}
          />
        );
      })}

      {/* Nodes */}
      {graphData.nodes.map((node) => {
        const pos = positions.get(node.nodeId);
        if (!pos) return null;
        const isHighlighted = selectedCatalystPath?.includes(node.name) || false;
        const r = (node.nodeType === 'ticker' ? 6 : 4.5) * scale;
        const labelOffset = (node.nodeType === 'ticker' ? 8 : -8) * scale;
        const textAnchor = node.nodeType === 'ticker' ? 'start' : 'end';

        return (
          <g key={node.nodeId} opacity={selectedCatalystPath && !isHighlighted ? 0.35 : 1} style={{ cursor: 'help' }}>
            <circle
              cx={pos.x} cy={pos.y} r={r}
              fill={getNodeColor(node.nodeType, isHighlighted)}
              stroke={isHighlighted ? 'white' : 'transparent'} strokeWidth={scale}
            />
            <text
              x={pos.x + labelOffset} y={pos.y + 3 * scale}
              fill={isHighlighted ? 'white' : 'var(--text-secondary)'}
              fontSize={`${fontSize}px`}
              fontWeight={node.nodeType === 'ticker' || isHighlighted ? 'bold' : 'normal'}
              textAnchor={textAnchor}
            >
              {node.name}
            </text>
            <title>{`${node.name} (${node.nodeType})\nQuery terms: ${node.queryTerms.join(', ')}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

export default function App() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [iteration, setIteration] = useState<number>(3);
  const [scenarioId, setScenarioId] = useState<string>('live');
  const [activeTicker, setActiveTicker] = useState<string>('AAPL');
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [graphData, setGraphData] = useState<ExposureGraph>({ nodes: [], edges: [] });
  const [ledgerEntries, setLedgerEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [phoenixStatus, setPhoenixStatus] = useState<any>({ running: false, dashboardUrl: '' });
  const [selectedCatalystPath, setSelectedCatalystPath] = useState<string[] | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<any>(null);
  const [graphModalOpen, setGraphModalOpen] = useState(false);
  const [graphStatus, setGraphStatus] = useState<ExpansionStatus>({});

  // Fetch initial configuration
  useEffect(() => {
    fetchWatchlist();
    fetchGraph();
    fetchGraphStatus();
    fetchLedger();
    fetchPhoenixStatus();
    fetchMemoryStatus();
  }, []);

  // Poll expansion status while any ticker is pending/running, refreshing the graph as
  // edges land. The effect re-arms on each graphStatus change and stops once all settle.
  useEffect(() => {
    const active = Object.values(graphStatus).some(s => s.status === 'pending' || s.status === 'running');
    if (!active) return;
    const t = setTimeout(() => {
      fetchGraphStatus();
      fetchGraph();
    }, 2500);
    return () => clearTimeout(t);
  }, [graphStatus]);

  const fetchWatchlist = async () => {
    try {
      const res = await fetch('/api/watchlist');
      const data = await res.json();
      setWatchlist(data.tickers);
      if (data.tickers.length > 0 && !activeTicker) {
        setActiveTicker(data.tickers[0]);
      }
    } catch (e) {
      console.error('Error fetching watchlist', e);
    }
  };

  const fetchGraph = async () => {
    try {
      const res = await fetch('/api/graph');
      const data = await res.json();
      setGraphData(data);
    } catch (e) {
      console.error('Error fetching graph', e);
    }
  };

  const fetchGraphStatus = async () => {
    try {
      const res = await fetch('/api/graph/status');
      const data = await res.json();
      setGraphStatus(data.status || {});
    } catch (e) {
      console.error('Error fetching graph status', e);
    }
  };

  // Manually (re-)run the LLM exposure-graph expansion for a ticker.
  const triggerExpansion = async (ticker: string) => {
    try {
      const res = await fetch('/api/graph/expand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, force: true })
      });
      const data = await res.json();
      setGraphStatus(data.expansionStatus || {});
    } catch (e) {
      console.error('Error triggering graph expansion', e);
    }
  };

  // Rebuild the whole graph for every watchlist ticker. reset=true restores the curated
  // seed first (dropping accumulated LLM additions); reset=false refreshes additively.
  const rebuildGraph = async (reset: boolean) => {
    if (reset && !confirm('Reset the exposure graph to its curated seed and re-expand every watchlist ticker? This discards all accumulated LLM-generated nodes/edges.')) return;
    try {
      const res = await fetch('/api/graph/rebuild', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset })
      });
      const data = await res.json();
      setGraphStatus(data.expansionStatus || {});
      fetchGraph();
    } catch (e) {
      console.error('Error rebuilding graph', e);
    }
  };

  // Resolves the display status for a ticker: explicit status entry, else "ready" if a
  // node already exists in the graph (seeded), else "none".
  const graphStatusFor = (ticker: string): string => {
    const s = graphStatus[ticker]?.status;
    if (s) return s;
    return graphData.nodes.some(n => n.nodeId === `ticker_${ticker}`) ? 'ready' : 'none';
  };

  const fetchLedger = async () => {
    try {
      const res = await fetch('/api/ledger');
      const data = await res.json();
      setLedgerEntries(data);
    } catch (e) {
      console.error('Error fetching ledger', e);
    }
  };

  const fetchPhoenixStatus = async () => {
    try {
      const res = await fetch('/api/phoenix-status');
      const data = await res.json();
      setPhoenixStatus(data);
    } catch (e) {
      console.error('Error fetching Phoenix status', e);
    }
  };

  const fetchMemoryStatus = async () => {
    try {
      const res = await fetch('/api/memory-status');
      const data = await res.json();
      setMemoryStatus(data);
    } catch (e) {
      console.error('Error fetching memory status', e);
    }
  };

  const addTicker = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTicker) return;
    const cleanTicker = newTicker.trim().toUpperCase();
    if (watchlist.includes(cleanTicker)) return;

    const updated = [...watchlist, cleanTicker];
    try {
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: updated })
      });
      const data = await res.json();
      setWatchlist(data.tickers);
      setNewTicker('');
      setActiveTicker(cleanTicker);
      // The add is immediate; graph expansion runs in the background. Seed the status
      // map so the polling effect starts and the UI shows "pending" right away.
      setGraphStatus(data.expansionStatus || {});
    } catch (e) {
      console.error('Error updating watchlist', e);
    }
  };

  const removeTicker = async (tickerToRemove: string) => {
    const updated = watchlist.filter(t => t !== tickerToRemove);
    try {
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: updated })
      });
      const data = await res.json();
      setWatchlist(data.tickers);
      if (activeTicker === tickerToRemove) {
        setActiveTicker(data.tickers[0] || '');
      }
    } catch (e) {
      console.error('Error removing ticker', e);
    }
  };

  const clearLedgerMemory = async () => {
    if (!confirm('Are you sure you want to clear the Catalyst Ledger memory? This will reset all story updates.')) return;
    try {
      const res = await fetch('/api/ledger/clear', { method: 'POST' });
      await res.json();
      fetchLedger();
      alert('Ledger cleared successfully!');
    } catch (e) {
      console.error('Error clearing ledger', e);
    }
  };

  const runPipeline = async () => {
    setLoading(true);
    setSelectedCatalystPath(null);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          iteration,
          scenario_id: scenarioId,
          simulated_now: scenarioId === 'live' ? new Date().toISOString() : '2026-05-28T17:25:00Z'
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Pipeline execution failed');
      }
      const data = await res.json();
      setRunResult(data);
      fetchLedger();
      fetchGraph();
      fetchMemoryStatus();
    } catch (e: any) {
      alert(`Pipeline execution error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const getActiveSynthesis = (): TickerSummary | null => {
    if (!runResult || !runResult.tickerSyntheses) return null;
    return runResult.tickerSyntheses[activeTicker] || null;
  };

  const getActiveBucket = (): TickerBucket | null => {
    if (!runResult || !runResult.tickerBuckets) return null;
    return runResult.tickerBuckets[activeTicker] || null;
  };

  // Small status pill shown next to each watchlist ticker, reflecting graph expansion.
  const renderGraphStatusPill = (ticker: string) => {
    const status = graphStatusFor(ticker);
    const map: Record<string, { label: string; color: string }> = {
      pending: { label: 'graph: queued', color: 'var(--accent-orange)' },
      running: { label: 'graph: building…', color: 'var(--accent-orange)' },
      done: { label: 'graph: ready', color: 'var(--accent-green)' },
      ready: { label: 'graph: ready', color: 'var(--accent-green)' },
      skipped: { label: 'graph: ready', color: 'var(--accent-green)' },
      failed: { label: 'graph: failed', color: 'var(--accent-red)' },
      none: { label: 'graph: —', color: 'var(--text-muted)' },
    };
    const meta = map[status] || map.none;
    const spinning = status === 'pending' || status === 'running';
    return (
      <span style={{ fontSize: '0.6rem', color: meta.color, display: 'flex', alignItems: 'center', gap: '0.2rem' }} title={graphStatus[ticker]?.error || meta.label}>
        {spinning && <span className="spinner" style={{ width: '8px', height: '8px', borderWidth: '1.5px' }} />}
        {meta.label}
      </span>
    );
  };

  return (
    <div className="app-container">
      {/* Header Panel */}
      <header className="glass">
        <div className="logo-section">
          <h1>⚡ Cross-Impact Catalyst Briefings</h1>
          <p>Deduplicated Geopolitical & Tech Catalyst Synthesizer for Intraday Traders</p>
        </div>

        <div className="header-controls">
          {/* Iteration Selector */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 800 }}>Pipeline Mode</span>
            <select 
              className="custom-select" 
              value={iteration} 
              onChange={(e) => setIteration(Number(e.target.value))}
            >
              <option value={1}>Iteration 1: Direct News Synthesis</option>
              <option value={2}>Iteration 2: Catalyst Memory Dedup</option>
              <option value={3}>Iteration 3: Graph Cross-Impact Routing</option>
            </select>
          </div>

          {/* Scenario Selector */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 800 }}>News Source / Replay</span>
            <select 
              className="custom-select" 
              value={scenarioId} 
              onChange={(e) => setScenarioId(e.target.value)}
            >
              <option value="live">Live Feeds (Finnhub + Currents)</option>
              <option value="direct_news">Replay Scenario 1: Direct Announcements</option>
              <option value="duplicate_news">Replay Scenario 2: Duplicate Articles</option>
              <option value="cross_impact">Replay Scenario 3: Untickered Geopolitical/Tech</option>
            </select>
          </div>

          {/* Ledger Clear Reset */}
          <button 
            className="btn-secondary" 
            onClick={clearLedgerMemory} 
            title="Reset active story thread cache in Ledger"
            style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', height: '38px', marginTop: '14px' }}
          >
            <RotateCcw size={15} />
            <span>Reset Cache</span>
          </button>

          {/* Run Button */}
          <button 
            className="btn-primary" 
            onClick={runPipeline} 
            disabled={loading || watchlist.length === 0}
            style={{ height: '38px', marginTop: '14px' }}
          >
            {loading ? (
              <div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px' }}></div>
            ) : (
              <Play size={16} fill="white" />
            )}
            <span>Fetch Catalysts</span>
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="workspace">
        
        {/* Left Sidebar - Watchlist */}
        <aside className="glass sidebar">
          <div>
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <Layers size={14} /> Watchlist Tickers
            </h2>
            
            {/* Watchlist adder */}
            <form onSubmit={addTicker} className="watchlist-manage">
              <input 
                type="text" 
                placeholder="ADD TICKER (e.g. MSFT)" 
                className="watchlist-input" 
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
              />
              <button type="submit" className="btn-primary" style={{ padding: '0.4rem 0.8rem', boxShadow: 'none' }}>
                <Plus size={16} />
              </button>
            </form>
          </div>

          {/* Ticker List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1, overflowY: 'auto' }}>
            {watchlist.map(ticker => {
              const isActive = activeTicker === ticker;
              const tickerSynthesis = runResult?.tickerSyntheses?.[ticker];
              const influence = tickerSynthesis?.overallPossibleInfluence || 'unclear';
              const hasCatalysts = tickerSynthesis && tickerSynthesis.summaryHeadline !== "No new catalysts detected";

              return (
                <div 
                  key={ticker} 
                  className={`glass glass-hover watchlist-item ${isActive ? 'active' : ''}`}
                  onClick={() => {
                    setActiveTicker(ticker);
                    setSelectedCatalystPath(null);
                  }}
                >
                  <div>
                    <div className="ticker-name">{ticker}</div>
                    <div className="company-name">
                      {ticker === 'AAPL' && 'Apple Inc.'}
                      {ticker === 'MSFT' && 'Microsoft Corp.'}
                      {ticker === 'NVDA' && 'Nvidia Corp.'}
                      {ticker === 'TSM' && 'TSMC'}
                      {ticker === 'DAL' && 'Delta Air'}
                      {!['AAPL','MSFT','NVDA','TSM','DAL'].includes(ticker) && 'Public Company'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.15rem' }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          triggerExpansion(ticker);
                        }}
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                        title="Re-run exposure-graph update for this ticker"
                        disabled={['pending', 'running'].includes(graphStatusFor(ticker))}
                      >
                        <RefreshCw size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeTicker(ticker);
                        }}
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                        title="Remove"
                      >
                        <Trash2 size={13} hover-color="var(--accent-red)" />
                      </button>
                    </div>
                    {renderGraphStatusPill(ticker)}
                    {runResult && (
                      <span className={`badge ${hasCatalysts ? influence : 'unclear'}`} style={{ fontSize: '0.65rem' }}>
                        {hasCatalysts ? influence : 'no change'}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Center Panel - Dashboard and Synthesized briefing */}
        <main className="main-content">
          {loading ? (
            <div className="glass loading-overlay" style={{ flex: 1 }}>
              <div className="spinner"></div>
              <h2>Executing LLM Catalyst Workflow Graph</h2>
              <p style={{ color: 'var(--text-secondary)' }}>
                {iteration === 1 && "Fetching direct articles and executing extraction + synthesis..."}
                {iteration === 2 && "Deduplicating articles using local vector memory ledger..."}
                {iteration === 3 && "Expanding search terms and routing untickered geopolitical shocks..."}
              </p>
            </div>
          ) : (
            <>
              {/* Ticker Synthesis Details */}
              {(() => {
                const synthesis = getActiveSynthesis();
                const bucket = getActiveBucket();
                if (!synthesis) {
                  return (
                    <div className="glass" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)', flex: 1 }}>
                      <h2>No Active Run Data</h2>
                      <p style={{ marginTop: '0.5rem' }}>Select an iteration and news scenario, then click "Fetch Catalysts" to populate briefing cards.</p>
                    </div>
                  );
                }

                const influenceColor = synthesis.overallPossibleInfluence;
                const hasCatalysts = synthesis.summaryHeadline !== "No new catalysts detected";

                return (
                  <div className="glass synthesis-card">
                    <div className="synthesis-header">
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span className={`iteration-indicator it${iteration}`}>Iteration {iteration}</span>
                          <span className={`badge ${hasCatalysts ? influenceColor : 'unclear'}`}>
                            {hasCatalysts ? synthesis.overallPossibleInfluence : 'no catalysts'}
                          </span>
                          <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)' }}>
                            Confidence: {synthesis.confidence}
                          </span>
                        </div>
                        <h2 style={{ marginTop: '0.5rem' }}>{synthesis.summaryHeadline}</h2>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Ticker Focus: {activeTicker}</span>
                      </div>
                      
                      {bucket && bucket.suppressedDuplicateCount > 0 && (
                        <div className="badge" style={{ background: 'rgba(168, 85, 247, 0.12)', color: 'var(--accent-purple)', borderColor: 'rgba(168, 85, 247, 0.2)' }}>
                          {bucket.suppressedDuplicateCount} duplicates suppressed
                        </div>
                      )}
                    </div>

                    <div className="synthesis-summary">
                      {synthesis.situationSummary}
                    </div>

                    {/* Columns: Uncertainties & Watch Items */}
                    <div className="synthesis-details-grid">
                      <div className="details-column">
                        <h3>🔑 Uncertainties / Open Risks</h3>
                        <ul className="details-list">
                          {synthesis.uncertainties.map((u, i) => (
                            <li key={i}>{u}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="details-column">
                        <h3>👀 Trader Watchlist Items</h3>
                        <ul className="details-list">
                          {synthesis.watchItems.map((wi, i) => (
                            <li key={i}>{wi}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Compliance Disclaimer */}
                    <div className="compliance-disclaimer">
                      <ShieldAlert size={16} style={{ color: 'var(--accent-orange)', flexShrink: 0 }} />
                      <p>{synthesis.complianceDisclaimer || "Grounded information only. Not investment advice."}</p>
                    </div>
                  </div>
                );
              })()}

              {/* Supporting Event Cards List */}
              {(() => {
                const bucket = getActiveBucket();
                if (!bucket || (!bucket.directEvents.length && !bucket.crossImpactEvents.length)) return null;

                return (
                  <div className="catalysts-section">
                    <h2 className="section-title">Supporting News Events (Catalysts)</h2>
                    <div className="catalysts-grid">
                      {/* Direct Events */}
                      {bucket.directEvents.map((evt) => (
                        <div key={evt.eventId} className="glass catalyst-card">
                          <div className="catalyst-card-header">
                            <span className="badge" style={{ borderColor: 'rgba(168, 85, 247, 0.3)', color: 'var(--accent-purple)' }}>Direct Company News</span>
                            <span className={`badge ${evt.possibleDirectionalPressure}`}>{evt.possibleDirectionalPressure}</span>
                          </div>
                          <div className="catalyst-title">{evt.headline}</div>
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                            {evt.eventSummary}
                          </p>
                          <div className="catalyst-fact-box">
                            <div className="fact-title">Hard Facts Grounded in Text:</div>
                            {evt.hardFacts.map((fact, index) => (
                              <div key={index} className="catalyst-fact">• {fact}</div>
                            ))}
                          </div>
                        </div>
                      ))}

                      {/* Cross-Impact Events */}
                      {bucket.crossImpactEvents.map((evt) => {
                        const isGraphHovered = selectedCatalystPath && selectedCatalystPath.join(',') === evt.impactPath?.join(',');
                        
                        return (
                          <div 
                            key={evt.eventId} 
                            className="glass catalyst-card"
                            style={{ 
                              borderColor: isGraphHovered ? 'var(--accent-cyan)' : 'var(--border-color)',
                              boxShadow: isGraphHovered ? '0 0 15px rgba(6, 182, 212, 0.15)' : 'none',
                              transition: 'all 0.2s'
                            }}
                            onMouseEnter={() => evt.impactPath && setSelectedCatalystPath(evt.impactPath)}
                            onMouseLeave={() => setSelectedCatalystPath(null)}
                          >
                            <div className="catalyst-card-header">
                              <span className="badge" style={{ borderColor: 'rgba(6, 182, 212, 0.3)', color: 'var(--accent-cyan)' }}>Cross-Impact Event (Indirect)</span>
                              <span className={`badge ${evt.possibleDirectionalPressure}`}>{evt.possibleDirectionalPressure}</span>
                            </div>
                            <div className="catalyst-title">{evt.headline}</div>
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                              {evt.eventSummary}
                            </p>
                            
                            <div className="catalyst-fact-box">
                              <div className="fact-title">Hard Facts Grounded in Text:</div>
                              {evt.hardFacts.map((fact, index) => (
                                <div key={index} className="catalyst-fact">• {fact}</div>
                              ))}
                            </div>

                            {/* Causal Impact Path mapping from Exposure Graph */}
                            {evt.impactPath && (
                              <div>
                                <div className="fact-title" style={{ marginTop: '0.75rem', marginBottom: '0.25rem' }}>Exposure Chain Traversed:</div>
                                <div className="impact-path-display">
                                  {evt.impactPath.map((step, idx) => {
                                    const isFirst = idx === 0;
                                    const isLast = idx === evt.impactPath!.length - 1;
                                    return (
                                      <React.Fragment key={idx}>
                                        <span className={`path-step ${isFirst ? 'source' : ''} ${isLast ? 'ticker' : ''}`}>
                                          {step}
                                        </span>
                                        {!isLast && <span className="path-arrow">→</span>}
                                      </React.Fragment>
                                    );
                                  })}
                                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                                    Path Score: {evt.pathConfidence}
                                  </span>
                                </div>
                                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem', fontStyle: 'italic' }}>
                                  <strong>Causal path:</strong> {evt.reasonForRouting}
                                </p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}
            </>
          )}
        </main>

        {/* Right Sidebar - Exposure Graph & Observability Panel */}
        <aside className="right-panel">
          
          {/* Exposure Graph Viewer Card */}
          <section className="glass panel-card">
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.35rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Network size={14} /> Causal Exposure Graph
              </span>
              <button
                onClick={() => setGraphModalOpen(true)}
                className="btn-secondary"
                style={{ padding: '0.2rem 0.45rem', display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem' }}
                title="Open full-screen graph"
              >
                <Maximize2 size={12} /> Open
              </button>
            </h2>
            <div className="graph-container" style={{ cursor: graphData.nodes.length > 0 ? 'pointer' : 'default' }} onClick={() => graphData.nodes.length > 0 && setGraphModalOpen(true)}>
              <GraphView graphData={graphData} width={380} height={250} scale={1} selectedCatalystPath={selectedCatalystPath} />
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '-0.3rem' }}>
              Click to open. Hover over indirect cards to highlight impact pathways.
            </div>
          </section>

          {/* Trace Panel Card */}
          <section className="glass panel-card">
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Cpu size={14} /> Observability Traces
            </h2>

            <div className="trace-panel-body">
              {/* Tracing Status */}
              <div className="trace-status">
                <span className="metric-label">Arize Phoenix Tracing:</span>
                <span className="status-indicator">
                  <div className={phoenixStatus.running ? 'pulse-dot' : ''} style={{ background: phoenixStatus.running ? 'var(--accent-green)' : 'var(--accent-red)' }} />
                  {phoenixStatus.running ? 'ACTIVE' : 'OFFLINE'}
                </span>
              </div>

              {phoenixStatus.running && (
                <a 
                  href={phoenixStatus.dashboardUrl}
                  target="_blank" 
                  rel="noreferrer"
                  className="btn-secondary"
                  style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.4rem', textDecoration: 'none', padding: '0.45rem', fontSize: '0.85rem' }}
                >
                  <span>Open Phoenix Dashboard</span>
                  <ExternalLink size={13} />
                </a>
              )}

              {/* Stats of last run */}
              <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <h3 className="section-title" style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Workflow Metrics (Last Run)</h3>
                
                <div className="metric-row">
                  <span className="metric-label">Articles Ingested</span>
                  <span className="metric-value">{runResult ? runResult.articlesCount : '-'}</span>
                </div>
                
                <div className="metric-row">
                  <span className="metric-label">Canonical Extractions</span>
                  <span className="metric-value">{runResult ? runResult.eventsCount : '-'}</span>
                </div>
                
                <div className="metric-row">
                  <span className="metric-label">Routed Connections</span>
                  <span className="metric-value">{runResult ? runResult.routedCount : '-'}</span>
                </div>

                <div className="metric-row">
                  <span className="metric-label">Suppressed Duplicates</span>
                  <span className="metric-value">
                    {runResult ? Object.values(runResult.duplicateCounts).reduce((a,b) => a+b, 0) : '-'}
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* Ledger Memory Database Status */}
          <section className="glass panel-card" style={{ flex: 1 }}>
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Database size={14} /> Active Story Ledger
            </h2>
            <div style={{ flex: 1, overflowY: 'auto', maxHeight: '180px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {ledgerEntries.length > 0 ? (
                ledgerEntries.map(entry => (
                  <div key={entry.catalystId} style={{ fontSize: '0.75rem', padding: '0.5rem', background: 'rgba(255,255,255,0.02)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold' }}>
                      <span style={{ color: 'var(--accent-purple)' }}>{entry.ticker}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{entry.eventType}</span>
                    </div>
                    <div style={{ color: 'var(--text-primary)', marginTop: '0.2rem', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                      {entry.canonicalSummary}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.65rem', marginTop: '0.2rem' }}>
                      <span>Facts: {entry.hardFactsSeen.length}</span>
                      <span>Articles: {entry.memberArticleIds.length}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center', padding: '2rem' }}>
                  No active stories tracked in Catalyst Ledger.
                </div>
              )}
            </div>
          </section>

          {/* Embeddings Memory Engine Panel */}
          <section className="glass panel-card">
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Cpu size={14} /> Embeddings Memory Engine
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {memoryStatus ? (
                <>
                  {/* Provider badge row */}
                  <div className="metric-row" style={{ alignItems: 'flex-start' }}>
                    <span className="metric-label">Dedup Engine</span>
                    <span style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.45rem',
                      borderRadius: '4px',
                      background: memoryStatus.isFallbackActive
                        ? 'rgba(234, 88, 12, 0.12)'
                        : 'rgba(6, 182, 212, 0.12)',
                      color: memoryStatus.isFallbackActive
                        ? 'var(--accent-orange)'
                        : 'var(--accent-cyan)',
                      border: `1px solid ${memoryStatus.isFallbackActive ? 'rgba(234,88,12,0.3)' : 'rgba(6,182,212,0.3)'}`
                    }}>
                      {memoryStatus.dedupProvider}
                    </span>
                  </div>

                  <div className="metric-row">
                    <span className="metric-label">Extraction LLM</span>
                    <span className="metric-value" style={{ fontSize: '0.7rem', fontFamily: 'monospace', color: 'var(--accent-green)' }}>{memoryStatus.llmExtractionModel}</span>
                  </div>

                  <div className="metric-row">
                    <span className="metric-label">Synthesis LLM</span>
                    <span className="metric-value" style={{ fontSize: '0.7rem', fontFamily: 'monospace', color: 'var(--accent-purple)' }}>{memoryStatus.llmSynthesisModel}</span>
                  </div>

                  <div className="metric-row">
                    <span className="metric-label">Method</span>
                    <span className="metric-value" style={{ fontSize: '0.7rem', fontFamily: 'monospace' }}>{memoryStatus.dedupModel}</span>
                  </div>

                  {/* Separator */}
                  <div style={{ height: '1px', background: 'var(--border-color)', margin: '0.2rem 0' }} />

                  <div className="metric-row">
                    <span className="metric-label">Cosine Sim Threshold</span>
                    <span className="metric-value" style={{ color: 'var(--accent-purple)' }}>&ge; {memoryStatus.similarityThreshold}</span>
                  </div>

                  <div className="metric-row">
                    <span className="metric-label">Jaccard Fact Threshold</span>
                    <span className="metric-value" style={{ color: 'var(--accent-blue)' }}>&ge; {memoryStatus.jaccardFactThreshold}</span>
                  </div>

                  {/* Separator */}
                  <div style={{ height: '1px', background: 'var(--border-color)', margin: '0.2rem 0' }} />

                  <div className="metric-row">
                    <span className="metric-label">Live Stories</span>
                    <span className="metric-value">{memoryStatus.ledgerLiveEntries} / {memoryStatus.ledgerTotalEntries}</span>
                  </div>

                  <div className="metric-row">
                    <span className="metric-label">Vectors Stored</span>
                    <span className="metric-value" style={{ color: 'var(--accent-green)' }}>{memoryStatus.ledgerEmbeddedEntries}</span>
                  </div>

                  {memoryStatus.isFallbackActive && (
                    <div style={{
                      marginTop: '0.35rem',
                      padding: '0.4rem 0.5rem',
                      background: 'rgba(234, 88, 12, 0.08)',
                      border: '1px solid rgba(234,88,12,0.25)',
                      borderRadius: '5px',
                      fontSize: '0.7rem',
                      color: 'var(--accent-orange)',
                      lineHeight: 1.4
                    }}>
                      ⚠ Local embedding model unavailable. Using deterministic lexical cosine fallback — paraphrase dedup recall is reduced.
                    </div>
                  )}
                </>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center', padding: '1.5rem' }}>
                  Loading engine status...
                </div>
              )}
            </div>
          </section>

        </aside>

      </div>

      {/* Full-screen Exposure Graph Modal */}
      {graphModalOpen && (
        <div
          onClick={() => setGraphModalOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(3, 4, 8, 0.82)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem'
          }}
        >
          <div
            className="glass"
            onClick={(e) => e.stopPropagation()}
            style={{ width: 'min(1200px, 95vw)', height: 'min(800px, 92vh)', display: 'flex', flexDirection: 'column', padding: '1.25rem', gap: '0.75rem' }}
          >
            {/* Modal header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0 }}>
                <Network size={18} /> Causal Exposure Graph
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                  {graphData.nodes.length} nodes · {graphData.edges.length} edges
                </span>
              </h2>
              <button onClick={() => setGraphModalOpen(false)} className="btn-secondary" style={{ padding: '0.35rem 0.6rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <X size={14} /> Close
              </button>
            </div>

            <div style={{ display: 'flex', flex: 1, gap: '1rem', minHeight: 0 }}>
              {/* Large graph canvas */}
              <div style={{ flex: 1, minWidth: 0, border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
                <GraphView graphData={graphData} width={900} height={620} scale={2.2} selectedCatalystPath={selectedCatalystPath} />
              </div>

              {/* Side rail: legend + per-ticker expansion controls */}
              <div style={{ width: '260px', display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto' }}>
                <div>
                  <h3 className="section-title" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Legend</h3>
                  {[
                    ['Ticker (watchlist)', 'var(--accent-purple)'],
                    ['Technology theme', 'var(--accent-blue)'],
                    ['Company / sector', 'var(--accent-cyan)'],
                    ['Region / risk / commodity / route', 'var(--accent-orange)'],
                  ].map(([label, color]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: color, flexShrink: 0 }} />
                      {label}
                    </div>
                  ))}
                  <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                    Dashed edges = exposure links · solid = supplier/competitor/partner. Flow runs left → right into the ticker.
                  </div>
                </div>

                <div style={{ height: '1px', background: 'var(--border-color)' }} />

                <div>
                  <h3 className="section-title" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Global Rebuild</h3>
                  {(() => {
                    const anyBusy = watchlist.some(t => ['pending', 'running'].includes(graphStatusFor(t)));
                    return (
                      <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.75rem' }}>
                        <button
                          onClick={() => rebuildGraph(true)}
                          disabled={anyBusy}
                          className="btn-secondary"
                          style={{ flex: 1, padding: '0.35rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.3rem', fontSize: '0.7rem', opacity: anyBusy ? 0.5 : 1 }}
                          title="Reset to curated seed, then re-expand every watchlist ticker"
                        >
                          <RotateCcw size={12} /> From seed
                        </button>
                        <button
                          onClick={() => rebuildGraph(false)}
                          disabled={anyBusy}
                          className="btn-secondary"
                          style={{ flex: 1, padding: '0.35rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.3rem', fontSize: '0.7rem', opacity: anyBusy ? 0.5 : 1 }}
                          title="Force a fresh expansion for every watchlist ticker on top of the current graph"
                        >
                          <RefreshCw size={12} /> Refresh all
                        </button>
                      </div>
                    );
                  })()}

                  <h3 className="section-title" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Per-Ticker</h3>
                  {watchlist.map(ticker => {
                    const status = graphStatusFor(ticker);
                    const busy = status === 'pending' || status === 'running';
                    return (
                      <div key={ticker} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.4rem', padding: '0.35rem 0', borderBottom: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 700, fontSize: '0.8rem' }}>{ticker}</span>
                          {renderGraphStatusPill(ticker)}
                        </div>
                        <button
                          onClick={() => triggerExpansion(ticker)}
                          disabled={busy}
                          className="btn-secondary"
                          style={{ padding: '0.25rem 0.5rem', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem', opacity: busy ? 0.5 : 1 }}
                          title="Re-run the LLM exposure-graph update for this ticker"
                        >
                          <RefreshCw size={12} /> Update
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
