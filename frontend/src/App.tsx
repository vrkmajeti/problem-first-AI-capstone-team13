import React, { useState, useEffect } from 'react';
import { Play, RotateCcw, Plus, Trash2, ExternalLink, Network, Database, ShieldAlert, Cpu, Layers } from 'lucide-react';

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

export default function App() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [iteration, setIteration] = useState<number>(3);
  const [scenarioId, setScenarioId] = useState<string>('cross_impact');
  const [activeTicker, setActiveTicker] = useState<string>('AAPL');
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [graphData, setGraphData] = useState<ExposureGraph>({ nodes: [], edges: [] });
  const [ledgerEntries, setLedgerEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [phoenixStatus, setPhoenixStatus] = useState<any>({ running: false, dashboardUrl: '' });
  const [selectedCatalystPath, setSelectedCatalystPath] = useState<string[] | null>(null);

  // Fetch initial configuration
  useEffect(() => {
    fetchWatchlist();
    fetchGraph();
    fetchLedger();
    fetchPhoenixStatus();
  }, []);

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
          simulated_now: '2026-05-28T17:25:00Z'
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Pipeline execution failed');
      }
      const data = await res.json();
      setRunResult(data);
      fetchLedger();
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

  // SVG Coordinates for Exposure Graph Layout
  // Layout from left to right: Source factors (Geopolitical/Regions/Routes) -> Themes/Companies -> Target Tickers
  const getNodeCoordinates = (nodeId: string, nodeType: string, index: number, total: number) => {
    const spacing = 220 / (total + 1 || 2);
    const y = 30 + (index + 1) * spacing;
    
    switch (nodeType) {
      case 'ticker':
        return { x: 330, y: 40 + (index * 45) };
      case 'technology_theme':
      case 'private_company':
      case 'sector':
        return { x: 190, y: 50 + (index * 50) };
      default: // geopolitical, region, risk_factor, shipping_route
        return { x: 45, y: 35 + (index * 40) };
    }
  };

  // Group nodes by visual columns
  const column1 = graphData.nodes.filter(n => n.nodeType !== 'ticker' && n.nodeType !== 'technology_theme' && n.nodeType !== 'private_company' && n.nodeType !== 'sector');
  const column2 = graphData.nodes.filter(n => n.nodeType === 'technology_theme' || n.nodeType === 'private_company' || n.nodeType === 'sector');
  const column3 = graphData.nodes.filter(n => n.nodeType === 'ticker');

  const nodePositions = new Map<string, { x: number, y: number }>();
  column1.forEach((n, idx) => nodePositions.set(n.nodeId, getNodeCoordinates(n.nodeId, n.nodeType, idx, column1.length)));
  column2.forEach((n, idx) => nodePositions.set(n.nodeId, getNodeCoordinates(n.nodeId, n.nodeType, idx, column2.length)));
  column3.forEach((n, idx) => nodePositions.set(n.nodeId, getNodeCoordinates(n.nodeId, n.nodeType, idx, column3.length)));

  const getNodeColor = (nodeType: string, isHighlighted: boolean) => {
    if (isHighlighted) return 'var(--accent-purple)';
    switch (nodeType) {
      case 'ticker':
        return 'var(--accent-purple)';
      case 'technology_theme':
        return 'var(--accent-blue)';
      case 'private_company':
        return 'var(--accent-cyan)';
      default:
        return 'var(--accent-orange)';
    }
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
            <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Network size={14} /> Causal Exposure Graph
            </h2>
            <div className="graph-container">
              {graphData.nodes.length > 0 ? (
                <svg width="100%" height="100%" viewBox="0 0 380 250" style={{ background: '#07080d' }}>
                  {/* Edges */}
                  {graphData.edges.map((edge, idx) => {
                    const fromPos = nodePositions.get(edge.fromNodeId);
                    const toPos = nodePositions.get(edge.toNodeId);
                    if (!fromPos || !toPos) return null;

                    // Check if edge is part of the highlighted hover path
                    let isHighlighted = false;
                    if (selectedCatalystPath) {
                      const fromNode = graphData.nodes.find(n => n.nodeId === edge.fromNodeId);
                      const toNode = graphData.nodes.find(n => n.nodeId === edge.toNodeId);
                      if (fromNode && toNode) {
                        const fromIdx = selectedCatalystPath.indexOf(fromNode.name);
                        const toIdx = selectedCatalystPath.indexOf(toNode.name);
                        if (fromIdx !== -1 && toIdx !== -1 && Math.abs(fromIdx - toIdx) === 1) {
                          isHighlighted = true;
                        }
                      }
                    }

                    return (
                      <line 
                        key={idx}
                        x1={fromPos.x}
                        y1={fromPos.y}
                        x2={toPos.x}
                        y2={toPos.y}
                        stroke={isHighlighted ? 'var(--accent-cyan)' : '#27272a'}
                        strokeWidth={isHighlighted ? 2.5 : 1}
                        strokeDasharray={edge.edgeType.includes('exposure') ? '3,3' : 'none'}
                        opacity={selectedCatalystPath && !isHighlighted ? 0.25 : 0.8}
                      />
                    );
                  })}

                  {/* Nodes */}
                  {graphData.nodes.map((node) => {
                    const pos = nodePositions.get(node.nodeId);
                    if (!pos) return null;

                    const isHighlighted = selectedCatalystPath?.includes(node.name) || false;
                    const r = node.nodeType === 'ticker' ? 6 : 4.5;
                    const labelOffset = node.nodeType === 'ticker' ? 8 : -8;
                    const textAnchor = node.nodeType === 'ticker' ? 'start' : 'end';

                    return (
                      <g 
                        key={node.nodeId}
                        opacity={selectedCatalystPath && !isHighlighted ? 0.35 : 1}
                        style={{ cursor: 'help' }}
                      >
                        <circle 
                          cx={pos.x}
                          cy={pos.y}
                          r={r}
                          fill={getNodeColor(node.nodeType, isHighlighted)}
                          stroke={isHighlighted ? 'white' : 'transparent'}
                          strokeWidth={1}
                        />
                        <text
                          x={pos.x + labelOffset}
                          y={pos.y + 3}
                          fill={isHighlighted ? 'white' : 'var(--text-secondary)'}
                          fontSize="6.5px"
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
              ) : (
                <div className="canvas-placeholder">Loading graph nodes...</div>
              )}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '-0.3rem' }}>
              Hover over indirect cards to highlight impact pathways.
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

        </aside>

      </div>
    </div>
  );
}
