import React, { useState } from 'react';
import { Clock, Plus, Trash2, Cpu, CheckCircle2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { createJob, deleteJob, parseNLJob } from '../api';

export default function JobQueuePage({ jobs, onRefresh }: any) {
  const [nlPrompt, setNlPrompt] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmitNL = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nlPrompt.trim()) return;
    setLoading(true);
    try {
      await parseNLJob(nlPrompt);
      setNlPrompt('');
      await onRefresh();
    } catch (e: any) {
      alert('Failed to parse prompt: ' + e.message);
    }
    setLoading(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteJob(id);
      await onRefresh();
    } catch (e: any) {
      alert('Delete failed: ' + e.message);
    }
  };

  const pending = jobs?.filter((j: any) => j.status === 'PENDING') || [];
  const completed = jobs?.filter((j: any) => j.status === 'SCHEDULED' || j.status === 'COMPLETED') || [];

  const item = {
    hidden: { opacity: 0, x: -20 },
    show: { opacity: 1, x: 0 }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto h-full flex flex-col">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Job Queue & Scheduler</h1>
        <p className="text-muted-foreground">Manage workloads and submit natural language prompts.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 min-h-0">
        <div className="lg:col-span-2 flex flex-col h-full bg-card border border-border rounded-2xl shadow-lg p-6">
          <div className="mb-6 flex justify-between items-end">
            <div>
              <h2 className="text-xl font-bold">Pending Jobs</h2>
              <p className="text-sm text-muted-foreground">Waiting for optimization run</p>
            </div>
            <div className="bg-chart-2/10 text-chart-2 px-3 py-1 rounded-full text-sm font-bold">
              {pending.length} Pending
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto space-y-3 pr-2">
            {pending.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                <CheckCircle2 className="w-12 h-12 mb-4 opacity-20" />
                <p>Queue is empty. Submit a new job!</p>
              </div>
            ) : (
              pending.map((job: any) => (
                <motion.div variants={item} initial="hidden" animate="show" key={job.id} className="p-4 border border-border rounded-xl bg-background flex items-center justify-between group hover:border-chart-2/50 transition-colors">
                  <div>
                    <h3 className="font-semibold text-lg">{job.name}</h3>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                      <span className="flex items-center gap-1"><Cpu className="w-4 h-4" /> {job.gpus_required} GPU</span>
                      <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> {job.duration_hours}h</span>
                      <span>Priority: {job.priority}</span>
                    </div>
                  </div>
                  <button onClick={() => handleDelete(job.id)} className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100">
                    <Trash2 className="w-5 h-5" />
                  </button>
                </motion.div>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-col gap-6 h-full">
          {/* Smart Submit */}
          <div className="bg-card border border-border rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-bold mb-2">Smart Submission</h2>
            <p className="text-sm text-muted-foreground mb-4">Use natural language to submit a job.</p>
            <form onSubmit={handleSubmitNL} className="flex flex-col gap-3">
              <textarea
                value={nlPrompt}
                onChange={(e) => setNlPrompt(e.target.value)}
                className="w-full h-32 bg-input border border-border rounded-xl p-3 text-sm focus:outline-none focus:border-chart-1 resize-none transition-colors"
                placeholder="e.g. Train an ML model on 8 A100 GPUs for 12 hours. High priority, keep it green."
              />
              <button
                type="submit"
                disabled={loading || !nlPrompt.trim()}
                className="flex items-center justify-center gap-2 w-full py-3 bg-chart-1 text-white font-semibold rounded-xl hover:bg-chart-1/90 transition-all disabled:opacity-50"
              >
                {loading ? 'Processing AI...' : <><Plus className="w-5 h-5" /> Submit Job</>}
              </button>
            </form>
          </div>

          {/* Scheduled */}
          <div className="bg-card border border-border rounded-2xl shadow-lg p-6 flex-1 flex flex-col min-h-0">
            <h2 className="text-xl font-bold mb-4">Recently Scheduled</h2>
            <div className="flex-1 overflow-y-auto space-y-3">
              {completed.slice(0, 5).map((job: any) => (
                <div key={job.id} className="p-3 border border-border rounded-xl bg-background/50">
                  <h3 className="font-semibold text-sm truncate">{job.name}</h3>
                  <div className="flex justify-between mt-2 text-xs text-muted-foreground">
                    <span>{job.duration_hours}h</span>
                    <span className="text-chart-1 font-medium">{job.status}</span>
                  </div>
                </div>
              ))}
              {completed.length === 0 && (
                <p className="text-sm text-muted-foreground text-center mt-8">No scheduled jobs.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
