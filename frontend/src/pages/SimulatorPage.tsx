import React, { useState } from 'react';
import { Sliders, Play, RefreshCw } from 'lucide-react';
import { runWhatIf } from '../api';

function SliderField({ label, min, max, step, value, onChange, format }: any) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <label className="text-muted-foreground">{label}</label>
        <span className="font-mono font-bold">{format ? format(value) : value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-chart-1" />
      <div className="flex justify-between text-xs text-muted-foreground mt-0.5">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  );
}

export default function SimulatorPage({ runs }: any) {
  const [solarMult, setSolarMult] = useState(1.0);
  const [windMult, setWindMult] = useState(1.0);
  const [deadlineExt, setDeadlineExt] = useState(0);
  const [capacityChange, setCapacityChange] = useState(0);
  const [preemptShare, setPreemptShare] = useState(0.5);
  const [riskLambda, setRiskLambda] = useState(0.3);
  const [carbonBudget, setCarbonBudget] = useState(0);
  const [spatialOn, setSpatialOn] = useState(true);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const latestRunId = runs?.[0]?.run_id;

  const handleRun = async () => {
    if (!latestRunId) { setError('Run the scheduler first to have a baseline.'); return; }
    setRunning(true); setError('');
    try {
      const res = await runWhatIf({
        base_run_id: latestRunId,
        solar_multiplier: solarMult,
        wind_multiplier: windMult,
        deadline_extension_h: deadlineExt,
        capacity_change_pct: capacityChange,
        preemptible_share: preemptShare,
        risk_lambda: riskLambda,
        carbon_budget_kg: carbonBudget > 0 ? carbonBudget : null,
        allow_spatial: spatialOn,
      });
      setResult(res);
    } catch (e: any) { setError(e.message); }
    finally { setRunning(false); }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">What-If Simulator</h2>
          <p className="text-muted-foreground text-sm mt-1">
            Adjust parameters to see how the optimizer responds — without committing the plan
          </p>
        </div>
        <button onClick={handleRun} disabled={running}
          className="flex items-center gap-2 px-5 py-2.5 bg-chart-1 text-black font-bold rounded-xl hover:bg-chart-1/90 disabled:opacity-50 shadow-lg shadow-chart-1/20">
          <Play className="w-4 h-4" />{running ? 'Simulating…' : 'Run Scenario'}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-red-400 text-sm">{error}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sliders */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Sliders className="w-4 h-4" /> Scenario Parameters
          </h3>
          <SliderField label="Solar Generation Multiplier" min={0} max={2} step={0.1}
            value={solarMult} onChange={setSolarMult} format={(v: number) => `${v.toFixed(1)}×`} />
          <SliderField label="Wind Generation Multiplier" min={0} max={2} step={0.1}
            value={windMult} onChange={setWindMult} format={(v: number) => `${v.toFixed(1)}×`} />
          <SliderField label="Deadline Extension" min={0} max={24} step={1}
            value={deadlineExt} onChange={setDeadlineExt} format={(v: number) => v === 0 ? 'None' : `+${v}h`} />
          <SliderField label="Capacity Change %" min={-50} max={50} step={5}
            value={capacityChange} onChange={setCapacityChange} format={(v: number) => `${v > 0 ? '+' : ''}${v}%`} />
          <SliderField label="Preemptible Job Share" min={0} max={1} step={0.1}
            value={preemptShare} onChange={setPreemptShare} format={(v: number) => `${(v * 100).toFixed(0)}%`} />
          <SliderField label="Risk Aversion λ" min={0} max={1} step={0.1}
            value={riskLambda} onChange={setRiskLambda} format={(v: number) => v.toFixed(1)} />
          <SliderField label="Carbon Budget (kg, 0 = off)" min={0} max={500} step={10}
            value={carbonBudget} onChange={setCarbonBudget} format={(v: number) => v === 0 ? 'Off' : `${v} kg`} />
          <div className="flex items-center justify-between">
            <label className="text-sm text-muted-foreground">Spatial Shifting (Multi-site)</label>
            <button onClick={() => setSpatialOn(!spatialOn)}
              className={`relative w-12 h-6 rounded-full transition-colors ${spatialOn ? 'bg-chart-1' : 'bg-muted'}`}>
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${spatialOn ? 'translate-x-6' : ''}`} />
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-muted-foreground mb-4">Scenario Results</h3>
          {result ? (
            <div className="space-y-4">
              <div className="text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2">
                Comparing against base run: <span className="font-mono">{latestRunId?.slice(-8)}</span>
              </div>
              {[
                { label: 'Carbon Change', value: result.delta_carbon_kg != null ? `${result.delta_carbon_kg > 0 ? '+' : ''}${result.delta_carbon_kg.toFixed(2)} kg` : '—', positive: (result.delta_carbon_kg ?? 0) < 0 },
                { label: 'Renewable Share Change', value: result.delta_renewable != null ? `${result.delta_renewable > 0 ? '+' : ''}${(result.delta_renewable * 100).toFixed(1)}%` : '—', positive: (result.delta_renewable ?? 0) > 0 },
                { label: 'SLA Compliance', value: result.sla_pct != null ? `${result.sla_pct.toFixed(0)}%` : '—', positive: (result.sla_pct ?? 100) >= 100 },
                { label: 'Jobs Shifted', value: result.jobs_shifted ?? '—', positive: true },
              ].map(({ label, value, positive }) => (
                <div key={label} className="flex justify-between items-center py-2 border-b border-border last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className={`font-bold ${positive ? 'text-chart-1' : 'text-red-400'}`}>{value}</span>
                </div>
              ))}
              {result.message && (
                <div className="bg-muted rounded-lg p-3 text-xs text-muted-foreground">{result.message}</div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <Sliders className="w-10 h-10 text-muted-foreground mb-3" />
              <p className="text-muted-foreground text-sm">Adjust the sliders and click <strong>Run Scenario</strong> to see the impact.</p>
              {!latestRunId && <p className="text-amber-400 text-xs mt-2">⚠ Run the scheduler first to create a baseline run.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
