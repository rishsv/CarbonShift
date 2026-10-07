import React from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { Leaf, Zap, Clock, Server } from 'lucide-react';

interface DashboardProps {
  metrics: any;
  runs: any[];
}

export default function Dashboard({ metrics, runs }: DashboardProps) {
  const latestRun = runs?.[0];
  
  // Fake chart data based on metrics
  const chartData = [
    { name: 'Baseline', carbon: latestRun?.baseline_carbon_kg || 100 },
    { name: 'Planned', carbon: latestRun?.planned_carbon_kg || 80 },
  ];

  return (
    <div className="space-y-6">
      <header className="mb-8">
        <h2 className="text-3xl font-bold">Executive Dashboard</h2>
        <p className="text-muted-foreground mt-2">
          Real-time carbon impact and spatial-temporal scheduler performance.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Leaf className="w-4 h-4 text-chart-1" />
            Total Carbon Saved
          </h3>
          <p className="text-4xl font-bold mt-2">
            {metrics ? Math.round(metrics.total_kg_saved) : '--'}
            <span className="text-xl text-muted-foreground ml-1">kg CO₂e</span>
          </p>
          <p className="text-xs text-chart-1 mt-2 font-medium">
            {metrics ? `~${metrics.equiv_km_driven} km driven` : ''}
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Zap className="w-4 h-4 text-chart-3" />
            Renewable Energy Share
          </h3>
          <p className="text-4xl font-bold mt-2">
            {metrics ? (metrics.renewable_share_avg * 100).toFixed(1) : '--'}
            <span className="text-xl text-muted-foreground ml-1">%</span>
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Clock className="w-4 h-4 text-chart-2" />
            SLA Compliance
          </h3>
          <p className="text-4xl font-bold mt-2">
            {metrics ? metrics.sla_rate.toFixed(1) : '--'}
            <span className="text-xl text-muted-foreground ml-1">%</span>
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Server className="w-4 h-4 text-chart-4" />
            Optimizer Gap
          </h3>
          <p className="text-4xl font-bold mt-2">
            {latestRun?.gap ? (latestRun.gap * 100).toFixed(2) : '0.00'}
            <span className="text-xl text-muted-foreground ml-1">%</span>
          </p>
          <p className="text-xs text-muted-foreground mt-2 font-medium">
            Computed in {latestRun?.solve_seconds?.toFixed(1) || '--'}s
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm h-80">
          <h3 className="text-lg font-bold mb-4">Carbon Footprint Comparison</h3>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" stroke="var(--muted-foreground)" />
              <YAxis stroke="var(--muted-foreground)" />
              <Tooltip 
                cursor={{ fill: 'var(--muted)', opacity: 0.2 }}
                contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
              />
              <Legend />
              <Bar dataKey="carbon" name="Emissions (kg CO₂)" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-lg font-bold mb-4">Recent Scheduler Runs</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs uppercase bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 rounded-tl-lg">Strategy</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Savings</th>
                  <th className="px-4 py-3 rounded-tr-lg">Time</th>
                </tr>
              </thead>
              <tbody>
                {runs?.map((run, i) => (
                  <tr key={run.run_id} className="border-b border-border/50">
                    <td className="px-4 py-3 font-medium">{run.strategy}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 bg-chart-1/10 text-chart-1 rounded-full text-xs">
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-chart-1 font-medium">
                      +{run.savings_pct?.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {run.solve_seconds?.toFixed(2)}s
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
