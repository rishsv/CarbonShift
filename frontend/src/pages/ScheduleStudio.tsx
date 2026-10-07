import React, { useState, useEffect } from 'react';
import { Play, RefreshCw, Info } from 'lucide-react';
import { triggerSchedule, compareStrategies, fetchRun } from '../api';

// ── Gantt Chart ───────────────────────────────────────────────────────────────
const SITE_COLORS: Record<string, string> = {
  'chn-1': '#22c55e',
  'mum-1': '#3b82f6',
  'hyd-1': '#f59e0b',
  'nda-1': '#a855f7',
  'kol-1': '#ef4444',
};

const PRIORITY_COLORS: Record<number, string> = {
  5: '#ef4444', 4: '#f97316', 3: '#f59e0b', 2: '#3b82f6', 1: '#6b7280',
};

function GanttChart({ run, horizonStart }: { run: any; horizonStart: Date }) {
  if (!run?.items?.length) return (
    <div className="h-64 flex items-center justify-center text-muted-foreground text-sm">
      No schedule items. Run the optimizer first.
    </div>
  );

  const horizonEnd = new Date(horizonStart.getTime() + 48 * 3600000);
  const totalMs = horizonEnd.getTime() - horizonStart.getTime();

  // Group items by site
  const bySite: Record<string, any[]> = {};
  for (const item of run.items) {
    if (!bySite[item.site_id]) bySite[item.site_id] = [];
    bySite[item.site_id].push(item);
  }

  const sites = Object.keys(bySite);
  const rowH = 48;
  const labelW = 80;
  const totalH = sites.length * rowH + 40;

  // Time ticks every 6 hours
  const ticks = [];
  for (let h = 0; h <= 48; h += 6) {
    ticks.push(h);
  }

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 800 ${totalH}`} className="w-full" style={{ minWidth: 600 }}>
        {/* Header ticks */}
        {ticks.map(h => {
          const x = labelW + (h / 48) * (800 - labelW);
          const ts = new Date(horizonStart.getTime() + h * 3600000);
          const label = ts.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
          return (
            <g key={h}>
              <line x1={x} y1={20} x2={x} y2={totalH} stroke="#1f2937" strokeWidth={0.5} />
              <text x={x} y={14} textAnchor="middle" fill="#6b7280" fontSize={8}>{label}</text>
            </g>
          );
        })}

        {/* "Now" line */}
        {(() => {
          const now = Date.now();
          const nowX = labelW + ((now - horizonStart.getTime()) / totalMs) * (800 - labelW);
          if (nowX < labelW || nowX > 800) return null;
          return <line x1={nowX} y1={20} x2={nowX} y2={totalH} stroke="#22c55e" strokeWidth={1.5} strokeDasharray="4,2" />;
        })()}

        {/* Rows */}
        {sites.map((siteId, si) => {
          const y = 24 + si * rowH;
          return (
            <g key={siteId}>
              <rect x={0} y={y} width={800} height={rowH - 2} fill={si % 2 === 0 ? '#111c18' : '#0d1612'} />
              <text x={labelW - 4} y={y + rowH / 2 + 4} textAnchor="end" fill="#8fa79c" fontSize={9} fontWeight="bold">
                {siteId.toUpperCase()}
              </text>
              {bySite[siteId].map((item: any, ii: number) => {
                const segs = item.segments ?? [];
                return segs.map((seg: any, si2: number) => {
                  const startMs = new Date(seg.start).getTime();
                  const endMs = new Date(seg.end).getTime();
                  const x = labelW + Math.max(0, (startMs - horizonStart.getTime()) / totalMs) * (800 - labelW);
                  const w = Math.max(4, ((endMs - startMs) / totalMs) * (800 - labelW));
                  const color = SITE_COLORS[siteId] || '#22c55e';
                  return (
                    <g key={`${ii}-${si2}`}>
                      <rect x={x} y={y + 4} width={w} height={rowH - 12} rx={3}
                        fill={color} opacity={0.85} />
                      {w > 40 && (
                        <text x={x + 4} y={y + rowH / 2 + 3} fill="white" fontSize={7} fontWeight="bold">
                          {item.job_name?.slice(0, 12) ?? 'Job'}
                        </text>
                      )}
                    </g>
                  );
                });
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Strategy comparison bars ──────────────────────────────────────────────────
function CompareBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-mono uppercase text-muted-foreground">{label}</span>
        <span className="font-bold">{value.toFixed(2)} kg</span>
      </div>
      <div className="h-5 bg-muted rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function ScheduleStudio({ runs, jobs, onRefresh }: any) {
  const [scheduling, setScheduling] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [strategy, setStrategy] = useState('cpsat');
  const [riskLambda, setRiskLambda] = useState(0.3);
  const [horizonH, setHorizonH] = useState(48);
  const [compareData, setCompareData] = useState<any>(null);
  const [selectedRun, setSelectedRun] = useState<any>(runs?.[0] ?? null);

  useEffect(() => {
    if (runs?.[0]) setSelectedRun(runs[0]);
  }, [runs]);

  const handleRun = async () => {
    setScheduling(true);
    try {
      const result = await triggerSchedule({ strategy, horizon_hours: horizonH, risk_lambda: riskLambda });
      await onRefresh();
      setSelectedRun(result);
    } catch (e: any) { alert(e.message); }
    finally { setScheduling(false); }
  };

  const handleCompare = async () => {
    setComparing(true);
    try { setCompareData(await compareStrategies(horizonH)); }
    catch (e: any) { alert(e.message); }
    finally { setComparing(false); }
  };

  const horizonStart = new Date();
  horizonStart.setMinutes(0, 0, 0);

  const maxCarbon = compareData
    ? Math.max(...Object.values(compareData.strategies ?? {}).map((s: any) => s.carbon_kg ?? 0))
    : 0;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Schedule Studio</h2>
          <p className="text-muted-foreground text-sm mt-1">Gantt view with carbon heat-strip · Strategy comparison</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleCompare} disabled={comparing}
            className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-muted transition-all disabled:opacity-50">
            {comparing ? 'Comparing…' : 'Compare Strategies'}
          </button>
          <button onClick={handleRun} disabled={scheduling}
            className="flex items-center gap-2 px-5 py-2 bg-chart-1 text-black font-bold rounded-lg text-sm hover:bg-chart-1/90 disabled:opacity-50 shadow-lg shadow-chart-1/20">
            <Play className="w-4 h-4" />{scheduling ? 'Solving…' : `Run ${strategy.toUpperCase()}`}
          </button>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-card border border-border rounded-xl p-4 mb-5 flex flex-wrap gap-5 items-center">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Strategy</label>
          <select value={strategy} onChange={e => setStrategy(e.target.value)}
            className="bg-input border border-border rounded-lg px-3 py-1.5 text-sm">
            <option value="cpsat">CP-SAT (Optimal)</option>
            <option value="greedy">Greedy Carbon</option>
            <option value="fifo">FIFO (Baseline)</option>
            <option value="edf">EDF</option>
          </select>
        </div>
        <div className="flex-1 min-w-48">
          <label className="text-xs text-muted-foreground block mb-1">Risk Aversion λ = {riskLambda.toFixed(1)}</label>
          <input type="range" min={0} max={1} step={0.1} value={riskLambda}
            onChange={e => setRiskLambda(Number(e.target.value))}
            className="w-full accent-chart-1" />
          <div className="flex justify-between text-xs text-muted-foreground mt-0.5">
            <span>0 = Trust median</span><span>1 = Plan for worst</span>
          </div>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Horizon</label>
          <select value={horizonH} onChange={e => setHorizonH(Number(e.target.value))}
            className="bg-input border border-border rounded-lg px-3 py-1.5 text-sm">
            <option value={24}>24 hours</option>
            <option value={48}>48 hours</option>
            <option value={72}>72 hours</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Gantt */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-sm text-muted-foreground uppercase tracking-wider">
            Gantt Chart — {selectedRun ? `Run ${selectedRun.run_id?.slice(-6)} · ${selectedRun.strategy?.toUpperCase()}` : 'No run selected'}
          </h3>
          <GanttChart run={selectedRun} horizonStart={horizonStart} />
          {selectedRun && (
            <div className="mt-4 pt-4 border-t border-border grid grid-cols-3 gap-3 text-center">
              <div>
                <p className="text-chart-1 font-bold text-lg">{selectedRun.savings_pct?.toFixed(1)}%</p>
                <p className="text-xs text-muted-foreground">Carbon Saved</p>
              </div>
              <div>
                <p className="text-blue-400 font-bold text-lg">{selectedRun.sla?.on_time}/{selectedRun.sla?.total}</p>
                <p className="text-xs text-muted-foreground">SLA On-Time</p>
              </div>
              <div>
                <p className="text-foreground font-bold text-lg font-mono">{selectedRun.gap?.toFixed(4) ?? '—'}</p>
                <p className="text-xs text-muted-foreground">Optimality Gap</p>
              </div>
            </div>
          )}
        </div>

        {/* Right panel */}
        <div className="flex flex-col gap-4">
          {/* Strategy comparison */}
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider mb-4">Strategy Comparison</h3>
            {compareData ? (
              <div className="space-y-3">
                {Object.entries(compareData.strategies ?? {}).map(([name, s]: any) => (
                  <CompareBar key={name} label={name} value={s.carbon_kg ?? 0} max={maxCarbon}
                    color={name === 'cpsat' ? '#22c55e' : name === 'greedy' ? '#f59e0b' : name === 'edf' ? '#3b82f6' : '#6b7280'} />
                ))}
                <p className="text-xs text-muted-foreground text-center mt-2">Lower carbon = better</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">Click "Compare Strategies" to see FIFO vs EDF vs Greedy vs CP-SAT</p>
            )}
          </div>

          {/* Recent runs list */}
          <div className="bg-card border border-border rounded-xl p-5 flex-1">
            <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider mb-3">Run History</h3>
            {runs && runs.length > 0 ? (
              <div className="space-y-2">
                {runs.slice(0, 8).map((r: any) => (
                  <button key={r.run_id} onClick={() => setSelectedRun(r)}
                    className={`w-full text-left p-2.5 rounded-lg text-sm transition-all ${
                      selectedRun?.run_id === r.run_id ? 'bg-chart-1/15 border border-chart-1/30' : 'hover:bg-muted'
                    }`}>
                    <div className="flex justify-between">
                      <span className="font-mono text-xs uppercase">{r.strategy}</span>
                      <span className={`text-xs px-1.5 rounded ${r.status === 'OPTIMAL' ? 'text-chart-1' : 'text-blue-400'}`}>{r.status}</span>
                    </div>
                    <div className="flex justify-between mt-0.5 text-muted-foreground text-xs">
                      <span>Saved {r.savings_pct?.toFixed(1)}%</span>
                      <span>{r.sla?.on_time}/{r.sla?.total} SLA</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No runs yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
