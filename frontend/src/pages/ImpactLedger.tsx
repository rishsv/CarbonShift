import React, { useState, useEffect } from 'react';
import { Download, Leaf, Zap, Clock, TrendingDown, Award, BarChart3, TreePine, Car, Smartphone, Recycle } from 'lucide-react';
import { motion } from 'framer-motion';

function EquivCard({ icon: Icon, label, value, color }: any) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="stat-card group"
    >
      <div className={`absolute top-4 right-4 opacity-10 group-hover:opacity-20 transition-opacity`}>
        <Icon className="w-20 h-20" />
      </div>
      <div className={`inline-flex p-2.5 rounded-xl mb-3`} style={{ background: `${color}20` }}>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <p className="text-3xl font-black" style={{ color }}>{value}</p>
      <p className="text-sm text-muted-foreground mt-1">{label}</p>
    </motion.div>
  );
}

export default function ImpactLedger({ metrics, runs }: any) {
  const [downloading, setDownloading] = useState(false);

  // Compute totals from runs
  const totalCarbon = runs?.reduce((sum: number, r: any) => sum + (r.planned_carbon_kg ?? 0), 0) ?? 0;
  const totalSaved = runs?.reduce((sum: number, r: any) => sum + ((r.baseline_carbon_kg ?? 0) - (r.planned_carbon_kg ?? 0)), 0) ?? 0;
  const avgRenewable = runs?.length
    ? runs.reduce((sum: number, r: any) => sum + (r.renewable_share?.plan ?? 0), 0) / runs.length
    : 0;
  const totalJobs = runs?.reduce((sum: number, r: any) => sum + (r.sla?.total ?? 0), 0) ?? 0;

  // Equivalents
  const treeDays = (totalSaved * 1000 / 21.77).toFixed(0);       // 21.77 g/day per tree
  const kmDriven = (totalSaved / 0.21 * 1000).toFixed(0);        // 210 g/km for avg car
  const smartphoneCharges = (totalSaved * 1000 / 0.009).toFixed(0); // 9g per charge

  const handleDownload = () => {
    setDownloading(true);
    const rows = [
      ['Run ID', 'Strategy', 'Planned kg CO2', 'Baseline kg CO2', 'Saved kg CO2', 'Savings %', 'Renewable %', 'SLA On-time', 'SLA Total'],
      ...(runs ?? []).map((r: any) => [
        r.run_id,
        r.strategy,
        r.planned_carbon_kg?.toFixed(3) ?? 0,
        r.baseline_carbon_kg?.toFixed(3) ?? 0,
        ((r.baseline_carbon_kg ?? 0) - (r.planned_carbon_kg ?? 0)).toFixed(3),
        r.savings_pct?.toFixed(2) ?? 0,
        ((r.renewable_share?.plan ?? 0) * 100).toFixed(1),
        r.sla?.on_time ?? 0,
        r.sla?.total ?? 0,
      ])
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `carbonshift-impact-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    setTimeout(() => setDownloading(false), 800);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div className="page-header mb-0">
          <h1>Impact Ledger</h1>
          <p>Verifiable record of carbon savings and green compute equivalents</p>
        </div>
        <button onClick={handleDownload} disabled={downloading} className="btn-secondary">
          <Download className="w-4 h-4" /> {downloading ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* Top KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <EquivCard icon={Leaf} label="Total CO₂ Saved (kg)" value={totalSaved.toFixed(1)} color="#22c55e" />
        <EquivCard icon={TrendingDown} label="Total CO₂ Planned (kg)" value={totalCarbon.toFixed(1)} color="#3b82f6" />
        <EquivCard icon={Zap} label="Avg Renewable Share" value={`${(avgRenewable * 100).toFixed(0)}%`} color="#f59e0b" />
        <EquivCard icon={Clock} label="Total Jobs Scheduled" value={totalJobs} color="#a855f7" />
      </div>

      {/* Equivalents */}
      <div className="bg-card border border-border rounded-2xl p-6 mb-8 shadow-lg">
        <h2 className="text-lg font-bold mb-6 flex items-center gap-2">
          <Award className="w-5 h-5 text-chart-3" /> Your Savings in Real-World Terms
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="flex items-center gap-4">
            <div className="text-chart-1 opacity-80"><TreePine className="w-12 h-12" /></div>
            <div>
              <p className="text-3xl font-black text-chart-1">{treeDays}</p>
              <p className="text-sm text-muted-foreground">Tree-days of carbon absorption</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-chart-2 opacity-80"><Car className="w-12 h-12" /></div>
            <div>
              <p className="text-3xl font-black text-chart-2">{Number(kmDriven).toLocaleString('en-IN')}</p>
              <p className="text-sm text-muted-foreground">km not driven (petrol car)</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-chart-4 opacity-80"><Smartphone className="w-12 h-12" /></div>
            <div>
              <p className="text-3xl font-black text-chart-4">{Number(smartphoneCharges).toLocaleString('en-IN')}</p>
              <p className="text-sm text-muted-foreground">smartphone charges powered</p>
            </div>
          </div>
        </div>
      </div>

      {/* Run-by-run table */}
      <div className="bg-card border border-border rounded-2xl shadow-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center gap-2">
          <BarChart3 className="w-5 h-5" />
          <h2 className="font-bold">All Optimization Runs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {['Run ID', 'Strategy', 'Planned CO₂', 'Saved CO₂', 'Savings %', 'RE Share', 'SLA'].map(h => (
                  <th key={h} className="text-left px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {h === 'RE Share' ? <span className="flex items-center gap-1"><Recycle className="w-3 h-3" /> RE Share</span> : h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs && runs.length > 0 ? runs.map((r: any, i: number) => {
                const saved = (r.baseline_carbon_kg ?? 0) - (r.planned_carbon_kg ?? 0);
                return (
                  <tr key={r.run_id} className={`border-b border-border/50 hover:bg-muted/30 transition-colors ${i % 2 === 0 ? '' : 'bg-muted/10'}`}>
                    <td className="px-6 py-4 font-mono text-xs text-muted-foreground">{r.run_id?.slice(-8)}</td>
                    <td className="px-6 py-4">
                      <span className="badge-blue uppercase">{r.strategy}</span>
                    </td>
                    <td className="px-6 py-4 font-mono">{r.planned_carbon_kg?.toFixed(2)} kg</td>
                    <td className="px-6 py-4 font-mono text-chart-1 font-bold">+{saved.toFixed(2)} kg</td>
                    <td className="px-6 py-4">
                      <span className="badge-green">-{r.savings_pct?.toFixed(1)}%</span>
                    </td>
                    <td className="px-6 py-4 font-mono">{((r.renewable_share?.plan ?? 0) * 100).toFixed(0)}%</td>
                    <td className="px-6 py-4">{r.sla?.on_time}/{r.sla?.total} on-time</td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center text-muted-foreground">
                    No runs yet. Go to Schedule Studio and click <strong>Run CP-SAT</strong> to generate entries.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs text-muted-foreground mt-4 text-center">
        Methodology: Carbon savings = FIFO baseline − CP-SAT optimized. Emission factors from CEA national grid average. Energy from GPU TDP × PUE.
      </p>
    </div>
  );
}
