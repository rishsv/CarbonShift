import React, { useState, useEffect } from 'react';
import { fetchForecast, fetchForecastAccuracy } from '../api';
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts';
import { Beaker, PlugZapping } from 'lucide-react';

const REGIONS = ['NR', 'WR', 'SR', 'ER', 'NER'];
const REGION_NAMES: Record<string, string> = {
  NR: 'Northern', WR: 'Western', SR: 'Southern', ER: 'Eastern', NER: 'North-Eastern',
};

function formatIST(ts: string) {
  return new Date(ts).toLocaleString('en-IN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  });
}

function ciColor(ci: number) {
  if (ci < 400) return '#22c55e';
  if (ci < 600) return '#f59e0b';
  return '#ef4444';
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-3 text-xs shadow-xl">
      <p className="font-medium mb-2">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>{p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : p.value}</p>
      ))}
    </div>
  );
};

export default function GridForecastPage() {
  const [region, setRegion] = useState('SR');
  const [hours, setHours] = useState(48);
  const [data, setData] = useState<any[]>([]);
  const [accuracy, setAccuracy] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadForecast = async () => {
    setLoading(true); setError('');
    try {
      const [fcRes, accRes] = await Promise.allSettled([
        fetchForecast(region, hours),
        fetchForecastAccuracy(),
      ]);
      if (fcRes.status === 'fulfilled') {
        const points = fcRes.value.points ?? [];
        setData(points.map((p: any) => ({
          label: formatIST(p.target_ts),
          ci_p50: Math.round(p.ci_p50),
          ci_p10: Math.round(p.ci_p10),
          ci_p90: Math.round(p.ci_p90),
          band: [Math.round(p.ci_p10), Math.round(p.ci_p90)],
          re_pct: Math.round((p.renewable_share_p50 ?? 0) * 100),
        })));
      } else {
        setError('Forecast unavailable: ' + (fcRes as any).reason?.message);
      }
      if (accRes.status === 'fulfilled') setAccuracy(accRes.value);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadForecast(); }, [region, hours]);

  // Computed stats
  const minCi = data.length ? Math.min(...data.map(d => d.ci_p50)) : null;
  const maxCi = data.length ? Math.max(...data.map(d => d.ci_p50)) : null;
  const avgRe = data.length ? data.reduce((a, d) => a + d.re_pct, 0) / data.length : null;
  const greenHours = data.filter(d => d.ci_p50 < 400).length;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Grid Forecast Explorer</h2>
          <p className="text-muted-foreground text-sm mt-1">48h carbon intensity forecast with p10/p50/p90 uncertainty bands</p>
        </div>
        <div className="flex gap-3">
          <select value={region} onChange={e => setRegion(e.target.value)}
            className="bg-card border border-border rounded-lg px-3 py-2 text-sm">
            {REGIONS.map(r => <option key={r} value={r}>{r} — {REGION_NAMES[r]}</option>)}
          </select>
          <select value={hours} onChange={e => setHours(Number(e.target.value))}
            className="bg-card border border-border rounded-lg px-3 py-2 text-sm">
            <option value={24}>24h</option>
            <option value={48}>48h</option>
            <option value={72}>72h</option>
          </select>
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-4 gap-4 mb-5">
        {[
          { label: 'Min CI (Best)', value: minCi != null ? `${minCi} g/kWh` : '—', color: 'text-chart-1' },
          { label: 'Max CI (Worst)', value: maxCi != null ? `${maxCi} g/kWh` : '—', color: 'text-red-400' },
          { label: 'Avg Renewable', value: avgRe != null ? `${avgRe.toFixed(0)}%` : '—', color: 'text-blue-400' },
          { label: 'Green Hours (<400g)', value: greenHours > 0 ? `${greenHours}h` : '—', color: 'text-chart-1' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-card border border-border rounded-xl p-4">
            <p className={`text-xl font-bold ${color}`}>{value}</p>
            <p className="text-xs text-muted-foreground mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Main chart */}
      <div className="bg-card border border-border rounded-xl p-5 mb-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider">
            Carbon Intensity Forecast — {region} · {REGION_NAMES[region]}
          </h3>
          <span className="flex items-center gap-1 text-xs bg-muted px-2 py-1 rounded-full text-muted-foreground">
            <Beaker className="w-3 h-3" /> Grid Digital Twin · Estimated
          </span>
        </div>
        {loading ? (
          <div className="h-64 flex items-center justify-center text-muted-foreground">Loading…</div>
        ) : error ? (
          <div className="h-64 flex items-center justify-center text-red-400">{error}</div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} interval={Math.floor(data.length / 6)} />
              <YAxis yAxisId="ci" tick={{ fontSize: 10, fill: '#6b7280' }} label={{ value: 'gCO₂/kWh', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#6b7280' }} />
              <YAxis yAxisId="re" orientation="right" tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={v => `${v}%`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: '#8fa79c' }} />
              {/* P10-P90 band */}
              <Area yAxisId="ci" type="monotone" dataKey="ci_p90" fill="#ef444420" stroke="#ef444430" name="p90 (pessimistic)" strokeDasharray="3 2" />
              <Area yAxisId="ci" type="monotone" dataKey="ci_p10" fill="#22c55e15" stroke="#22c55e30" name="p10 (optimistic)" strokeDasharray="3 2" />
              {/* P50 line */}
              <Line yAxisId="ci" type="monotone" dataKey="ci_p50" stroke="#22c55e" strokeWidth={2.5} dot={false} name="CI p50 (forecast)" />
              {/* Renewable share */}
              <Line yAxisId="re" type="monotone" dataKey="re_pct" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Renewable %" strokeDasharray="5 3" />
              {/* Thresholds */}
              <ReferenceLine yAxisId="ci" y={400} stroke="#22c55e" strokeDasharray="6 3" label={{ value: '400 (clean)', fontSize: 9, fill: '#22c55e', position: 'right' }} />
              <ReferenceLine yAxisId="ci" y={600} stroke="#ef4444" strokeDasharray="6 3" label={{ value: '600 (heavy)', fontSize: 9, fill: '#ef4444', position: 'right' }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Accuracy card + data source note */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider mb-3">Forecast Accuracy</h3>
          {accuracy ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">MAE (24h)</span><span className="font-mono">{accuracy.mae_24h?.toFixed(1) ?? '—'} g/kWh</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Skill vs Naive</span><span className="font-mono text-chart-1">{accuracy.skill_score?.toFixed(3) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Interval Coverage</span><span className="font-mono">{accuracy.interval_coverage_pct?.toFixed(0) ?? '—'}%</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Model Version</span><span className="font-mono text-xs">{accuracy.model_version ?? 'twin-fallback'}</span></div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Accuracy metrics not available (models not trained yet).</p>
          )}
        </div>
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider mb-3">Data Source</h3>
          <div className="space-y-4 text-sm mt-3">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-amber-500/10 rounded-lg text-amber-500 mt-0.5">
                <Beaker className="w-4 h-4" />
              </div>
              <div>
                <p className="font-medium text-foreground">Grid Digital Twin</p>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">Physics-informed model calibrated to CEA baseline emission factors (~710 gCO₂/kWh national average). Solar, wind, hydro, and thermal dispatch modeled from weather data.</p>
              </div>
            </div>
            <div className="flex items-start gap-3 opacity-60">
              <div className="p-2 bg-blue-500/10 rounded-lg text-blue-500 mt-0.5">
                <PlugZapping className="w-4 h-4" />
              </div>
              <div>
                <p className="font-medium text-foreground">Grid-India API & Electricity Maps</p>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">Live data powered by Grid Controller of India Ltd. and Electricity Maps. Active when token is configured.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
