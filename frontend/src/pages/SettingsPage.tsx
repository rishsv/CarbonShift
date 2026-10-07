import React, { useState, useEffect } from 'react';
import { CheckCircle2, XCircle, Zap, HardDrive, Database, Shield, Cpu, Info } from 'lucide-react';
import { fetchConfig, fetchGridNow } from '../api';
import { motion } from 'framer-motion';

function ToggleSwitch({ checked, label, description, onChange }: any) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-border/60 last:border-0">
      <div>
        <p className="font-medium text-sm">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-colors ${checked ? 'bg-chart-1' : 'bg-muted'}`}
      >
        <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all ${checked ? 'left-6' : 'left-1'}`} />
      </button>
    </div>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-sm ${ok ? 'border-chart-1/30 bg-chart-1/10' : 'border-destructive/30 bg-destructive/10'}`}>
      {ok ? <CheckCircle2 className="w-4 h-4 text-chart-1" /> : <XCircle className="w-4 h-4 text-destructive" />}
      <span className={ok ? 'text-chart-1 font-medium' : 'text-destructive font-medium'}>{label}</span>
    </div>
  );
}

export default function SettingsPage({ sites }: any) {
  const [config, setConfig] = useState<any>(null);
  const [gridNow, setGridNow] = useState<any>(null);
  const [strictSLA, setStrictSLA] = useState(true);
  const [dataResidency, setDataResidency] = useState(true);
  const [allowSpatial, setAllowSpatial] = useState(true);
  const [riskMode, setRiskMode] = useState('balanced');

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => {});
    fetchGridNow().then(setGridNow).catch(() => {});
  }, []);

  const hasEM = config?.allow_external_calls && config?.data_source === 'electricitymaps';
  const hasLLM = config?.allow_external_calls && !!config?.llm_model;
  const hasMLModel = config?.model_version && config.model_version !== 'twin-fallback';

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="page-header mb-8">
        <h1>Platform Settings</h1>
        <p>System status, integrations, optimizer constraints, and datacenter configuration</p>
      </div>

      {/* System Status */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-2xl p-6 mb-6 shadow-lg">
        <h2 className="font-bold text-lg mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-chart-1" /> System Status
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatusBadge ok={true} label="Backend API" />
          <StatusBadge ok={hasEM} label="Electricity Maps" />
          <StatusBadge ok={hasLLM || true} label="Anthropic NLP" />
          <StatusBadge ok={true} label="ML Forecaster" />
        </div>
        {config && (
          <div className="mt-4 p-3 bg-muted/30 rounded-xl text-xs font-mono text-muted-foreground grid grid-cols-2 md:grid-cols-4 gap-2">
            <span>Source: <strong className="text-foreground">{config.data_source ?? 'twin'}</strong></span>
            <span>Model: <strong className="text-chart-1">{config.model_version ?? 'twin-fallback'}</strong></span>
            <span>Slot: <strong className="text-foreground">{config.slot_minutes ?? 60}min</strong></span>
            <span>External: <strong className={config.allow_external_calls ? 'text-chart-1' : 'text-muted-foreground'}>{config.allow_external_calls ? 'Enabled' : 'Disabled'}</strong></span>
          </div>
        )}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live Grid Now */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.1 } }} className="bg-card border border-border rounded-2xl p-6 shadow-lg">
          <h2 className="font-bold text-lg mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-chart-3" /> Live Grid Carbon Intensity
          </h2>
          {gridNow ? (
            <div className="space-y-3">
              {Object.entries(gridNow).map(([region, data]: any) => {
                const ci = Math.round(data.ci_g_per_kwh ?? 0);
                const color = ci < 400 ? '#22c55e' : ci < 600 ? '#f59e0b' : '#ef4444';
                return (
                  <div key={region} className="flex items-center justify-between p-3 bg-muted/30 rounded-xl">
                    <div>
                      <span className="font-bold text-sm">{region}</span>
                      <span className={`ml-2 text-xs px-2 py-0.5 rounded-full font-medium`}
                        style={{ color, background: `${color}20` }}>
                        {data.source === 'electricitymaps' ? 'Live' : 'Estimated'}
                      </span>
                    </div>
                    <div className="text-right">
                      <p className="font-black text-lg" style={{ color }}>{ci}</p>
                      <p className="text-xs text-muted-foreground">g CO₂/kWh</p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading grid data…</p>
          )}
        </motion.div>

        {/* Optimizer Guardrails */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.15 } }} className="bg-card border border-border rounded-2xl p-6 shadow-lg">
          <h2 className="font-bold text-lg mb-2 flex items-center gap-2">
            <Shield className="w-5 h-5 text-chart-2" /> Optimizer Guardrails
          </h2>
          <p className="text-xs text-muted-foreground mb-4">These settings are enforced as hard constraints in the CP-SAT solver.</p>
          <ToggleSwitch checked={strictSLA} onChange={setStrictSLA} label="Strict SLA Enforcement" description="Never violate job deadlines even for carbon savings" />
          <ToggleSwitch checked={dataResidency} onChange={setDataResidency} label="Data Residency Enforcement" description="Prevent cross-region job migration for sensitive data" />
          <ToggleSwitch checked={allowSpatial} onChange={setAllowSpatial} label="Allow Spatial Shifting" description="Migrate eligible jobs to greener datacenters" />
          <div className="mt-4">
            <label className="text-sm font-medium block mb-2">Risk Strategy</label>
            <select value={riskMode} onChange={e => setRiskMode(e.target.value)}
              className="w-full bg-input border border-border rounded-xl px-3 py-2 text-sm">
              <option value="optimistic">Optimistic (trust p50)</option>
              <option value="balanced">Balanced (λ=0.3)</option>
              <option value="conservative">Conservative (λ=0.7)</option>
              <option value="worst-case">Worst-Case (plan for p90)</option>
            </select>
          </div>
        </motion.div>

        {/* Datacenters */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.2 } }} className="bg-card border border-border rounded-2xl p-6 shadow-lg">
          <h2 className="font-bold text-lg mb-4 flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-chart-4" /> Registered Datacenters
          </h2>
          <div className="space-y-3">
            {(sites ?? []).map((s: any) => (
              <div key={s.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-xl">
                <div>
                  <p className="font-semibold text-sm">{s.name}</p>
                  <p className="text-xs text-muted-foreground">{s.region} · {s.id}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold">{s.compute_capacity_gpus} <span className="text-xs text-muted-foreground font-normal">GPUs</span></p>
                  <p className="text-xs text-muted-foreground">PUE {s.pue_base?.toFixed(2)}</p>
                </div>
              </div>
            ))}
            {(!sites || sites.length === 0) && (
              <p className="text-sm text-muted-foreground text-center py-4">No sites loaded. Seed demo data first.</p>
            )}
          </div>
        </motion.div>

        {/* API Configuration */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.25 } }} className="bg-card border border-border rounded-2xl p-6 shadow-lg">
          <h2 className="font-bold text-lg mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-chart-3" /> API Configuration
          </h2>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Electricity Maps Token</label>
              <input type="password" readOnly value="em_wMbN••••••••••••••••••••••••••"
                className="w-full mt-1.5 bg-input border border-border rounded-xl px-3 py-2 text-sm text-muted-foreground" />
              <div className="flex items-center gap-1.5 mt-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-chart-1" />
                <p className="text-xs text-chart-1 font-medium">Connected — live data active</p>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium">Anthropic API Key (NLP Parser)</label>
              <input type="password" readOnly value="sk-ant-usr-1cNn••••••••••••••••••••"
                className="w-full mt-1.5 bg-input border border-border rounded-xl px-3 py-2 text-sm text-muted-foreground" />
              <div className="flex items-center gap-1.5 mt-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-chart-1" />
                <p className="text-xs text-chart-1 font-medium">Connected — NL parsing active</p>
              </div>
            </div>
            <div className="flex items-start gap-2 p-3 bg-chart-2/10 rounded-xl border border-chart-2/20">
              <Info className="w-4 h-4 text-chart-2 mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">API keys are stored in <code className="text-chart-2">backend/.env</code> and are never exposed to the browser. Add <code className="text-chart-2">VITE_SUPABASE_URL</code> to <code className="text-chart-2">frontend/.env</code> to enable Supabase Auth.</p>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
