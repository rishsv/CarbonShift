import { useState } from 'react';
import { Send, Sparkles } from 'lucide-react';
import { API_BASE } from '../api';

export default function JobSubmit({ onJobAdded }: { onJobAdded: () => void }) {
  const [nlPrompt, setNlPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nlPrompt.trim()) return;
    
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      // 1. Call the natural language parser to draft the job
      const parseRes = await fetch(`${API_BASE}/jobs/parse-nl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: nlPrompt })
      });
      
      if (!parseRes.ok) throw new Error('Failed to parse prompt.');
      const draft = await parseRes.json();
      
      // 2. Submit the drafted job
      const submitRes = await fetch(`${API_BASE}/jobs/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft)
      });

      if (!submitRes.ok) throw new Error('Failed to create job.');
      
      setSuccess(`Successfully queued: ${draft.name}`);
      setNlPrompt('');
      onJobAdded(); // refresh parent
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-6 shadow-sm mb-6">
      <h3 className="text-lg font-bold flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-chart-3" />
        Natural Language Job Submission
      </h3>
      <p className="text-sm text-muted-foreground mt-1 mb-4">
        Try: "Train an ML model on 8 A100 GPUs for 12 hours. High priority, keep it green."
      </p>

      <form onSubmit={handleSubmit} className="flex gap-4">
        <input 
          type="text"
          value={nlPrompt}
          onChange={(e) => setNlPrompt(e.target.value)}
          placeholder="Describe your workload requirements..."
          className="flex-1 bg-input border border-border text-foreground rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-chart-1/50"
          disabled={loading}
        />
        <button 
          type="submit"
          disabled={loading || !nlPrompt.trim()}
          className="px-6 py-2 bg-primary text-primary-foreground hover:bg-primary/90 transition-colors rounded-lg flex items-center gap-2 font-medium disabled:opacity-50"
        >
          {loading ? 'Processing...' : 'Submit Job'}
          {!loading && <Send className="w-4 h-4" />}
        </button>
      </form>
      
      {error && <p className="text-destructive text-sm mt-3">{error}</p>}
      {success && <p className="text-chart-1 text-sm mt-3 font-medium">{success}</p>}
    </div>
  );
}
