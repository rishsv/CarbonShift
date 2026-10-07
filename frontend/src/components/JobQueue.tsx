import React, { useState } from 'react';
import { triggerSchedule } from '../api';
import { Play, RotateCcw } from 'lucide-react';
import JobSubmit from './JobSubmit';

export default function JobQueue({ runs, onRefresh }: { runs: any[], onRefresh: () => void }) {
  const [running, setRunning] = useState(false);
  const latestRun = runs?.[0];

  const handleRun = async () => {
    setRunning(true);
    try {
      await triggerSchedule('cpsat', 'balanced');
      onRefresh();
    } catch (e) {
      console.error(e);
    }
    setRunning(false);
  };

  return (
    <div className="space-y-6">
      <header className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold">Job Queue & Scheduler</h2>
          <p className="text-muted-foreground mt-2">
            Manage workloads and trigger the CP-SAT optimizer.
          </p>
        </div>
        <div className="flex gap-4">
          <button 
            onClick={onRefresh}
            className="px-4 py-2 bg-secondary text-secondary-foreground hover:bg-muted transition-colors rounded-md flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" /> Refresh
          </button>
          <button 
            onClick={handleRun}
            disabled={running}
            className="px-4 py-2 bg-chart-1 text-white hover:bg-chart-1/90 transition-colors rounded-md flex items-center gap-2 font-medium"
          >
            {running ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
            {running ? 'Optimizing...' : 'Run Scheduler'}
          </button>
        </div>
      </header>

      {/* Natural Language Job Submission */}
      <JobSubmit onJobAdded={onRefresh} />

      {/* Basic Gantt / Item List */}
      <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
        <h3 className="text-lg font-bold mb-4">Latest Schedule ({latestRun?.status || 'No runs'})</h3>
        
        {latestRun?.items && latestRun.items.length > 0 ? (
          <div className="space-y-4">
            {latestRun.items.map((item: any) => (
              <div key={item.job_id} className="p-4 border border-border/50 rounded-lg bg-background">
                <div className="flex justify-between mb-2">
                  <h4 className="font-bold">{item.job_name}</h4>
                  <span className="text-xs px-2 py-1 bg-chart-2/10 text-chart-2 rounded-full font-medium">
                    {item.site_id}
                  </span>
                </div>
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>Carbon: {item.planned_carbon_g.toFixed(0)}g</span>
                  <span>Energy: {item.planned_energy_kwh.toFixed(1)} kWh</span>
                </div>
                <div className="mt-3 text-xs text-muted-foreground flex gap-4">
                  {item.segments.map((seg: any, idx: number) => (
                    <div key={idx} className="bg-muted px-2 py-1 rounded">
                      {new Date(seg.start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} - {new Date(seg.end).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            No scheduled jobs. Click 'Run Scheduler' to optimize pending queue.
          </div>
        )}
      </div>
    </div>
  );
}
