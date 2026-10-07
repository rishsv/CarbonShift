import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Leaf, Zap, Globe, Server, TrendingDown } from 'lucide-react';

export default function CommandCenter({ metrics, runs, jobs, sites, greenWindows }: any) {
  // Use latest run for stats
  const latestRun = runs?.[0];
  const pendingJobs = jobs?.filter((j: any) => j.status === 'PENDING') || [];
  
  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <div className="p-8 pb-20 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1">Command Center</h1>
          <p className="text-muted-foreground">Real-time overview of your computational fleet and grid carbon intensity.</p>
        </div>
        <div className="flex items-center gap-3 bg-card border border-border px-4 py-2 rounded-xl shadow-sm">
          <div className="w-2.5 h-2.5 bg-chart-1 rounded-full animate-pulse"></div>
          <span className="text-sm font-semibold">Grid Link Active</span>
        </div>
      </div>

      <motion.div 
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
      >
        <motion.div variants={item} className="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-black/5 hover:shadow-xl transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <TrendingDown className="w-24 h-24" />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-chart-1/15 text-chart-1 rounded-xl"><Leaf className="w-5 h-5" /></div>
            <h3 className="font-semibold text-muted-foreground">Carbon Saved</h3>
          </div>
          <p className="text-4xl font-black">{metrics?.carbon_saved_kg ? Math.round(metrics.carbon_saved_kg) : (latestRun?.savings_pct ? Math.round(latestRun.savings_pct) : 0)}<span className="text-xl text-muted-foreground ml-1">kg</span></p>
          <p className="text-sm text-chart-1 font-medium mt-2">Last 30 Days</p>
        </motion.div>

        <motion.div variants={item} className="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-black/5 hover:shadow-xl transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Zap className="w-24 h-24" />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-chart-2/15 text-chart-2 rounded-xl"><Zap className="w-5 h-5" /></div>
            <h3 className="font-semibold text-muted-foreground">Active Workloads</h3>
          </div>
          <p className="text-4xl font-black">{pendingJobs.length}</p>
          <p className="text-sm text-muted-foreground mt-2">Awaiting Optimization</p>
        </motion.div>

        <motion.div variants={item} className="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-black/5 hover:shadow-xl transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Globe className="w-24 h-24" />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-chart-3/15 text-chart-3 rounded-xl"><Globe className="w-5 h-5" /></div>
            <h3 className="font-semibold text-muted-foreground">Green Windows</h3>
          </div>
          <p className="text-4xl font-black">{greenWindows?.length || 0}</p>
          <p className="text-sm text-muted-foreground mt-2">Next 12 Hours</p>
        </motion.div>

        <motion.div variants={item} className="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-black/5 hover:shadow-xl transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Server className="w-24 h-24" />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 bg-chart-4/15 text-chart-4 rounded-xl"><Server className="w-5 h-5" /></div>
            <h3 className="font-semibold text-muted-foreground">Datacenters</h3>
          </div>
          <p className="text-4xl font-black">{sites?.length || 0}</p>
          <p className="text-sm text-chart-1 font-medium mt-2">Online</p>
        </motion.div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <motion.div variants={item} initial="hidden" animate="show" className="lg:col-span-2 bg-card border border-border rounded-2xl shadow-lg p-6 flex flex-col">
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2"><Activity className="w-5 h-5" /> Recent Scheduler Runs</h2>
          {runs && runs.length > 0 ? (
            <div className="space-y-4">
              {runs.slice(0, 5).map((run: any) => (
                <div key={run.run_id} className="p-4 border border-border rounded-xl flex items-center justify-between hover:bg-muted/50 transition-colors">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold uppercase tracking-wider text-xs px-2 py-1 bg-primary text-primary-foreground rounded-md">{run.strategy}</span>
                      <span className="text-sm font-medium">{new Date(run.horizon_start).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">SLA: {run.sla.on_time}/{run.sla.total} jobs met deadline</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-chart-1">-{run.savings_pct?.toFixed(1)}%</p>
                    <p className="text-xs text-muted-foreground uppercase tracking-widest">CO2 Reduced</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center py-12 text-center">
              <Activity className="w-12 h-12 text-muted-foreground mb-4 opacity-50" />
              <h3 className="text-lg font-semibold">No Optimization Runs</h3>
              <p className="text-sm text-muted-foreground">Go to Schedule Studio to run the CP-SAT optimizer.</p>
            </div>
          )}
        </motion.div>

        <motion.div variants={item} initial="hidden" animate="show" className="bg-card border border-border rounded-2xl shadow-lg p-6">
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2"><Zap className="w-5 h-5" /> Grid Status</h2>
          <div className="space-y-4">
            {sites?.map((site: any) => (
              <div key={site.id} className="p-4 bg-muted/30 rounded-xl border border-border/50">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-semibold">{site.name}</span>
                  <span className="text-xs font-bold px-2 py-1 rounded bg-background border border-border">{site.region}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">PUE:</span>
                  <span className="font-medium">{site.pue_base.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm mt-1">
                  <span className="text-muted-foreground">GPUs:</span>
                  <span className="font-medium">{site.compute_capacity_gpus}</span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
