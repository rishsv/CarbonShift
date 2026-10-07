import React, { useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import { Leaf, Lock } from 'lucide-react';
import { motion } from 'framer-motion';

export default function AuthPage({ onLogin }: { onLogin: (user: any) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If we are missing real credentials, allow "bypass" for the hackathon demo
  const isMock = import.meta.env.VITE_SUPABASE_URL === undefined;

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (isMock) {
      setTimeout(() => {
        onLogin({ email: email || 'demo@carbonshift.ai', role: 'admin' });
      }, 800);
      return;
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      setLoading(false);
    } else if (data.user) {
      onLogin(data.user);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isMock) {
      setError('Sign up is disabled in demo mode. Just click Sign In.');
      return;
    }
    setLoading(true);
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) setError(error.message);
    else setError('Check your email for the confirmation link.');
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl p-8"
      >
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-chart-1/10 text-chart-1 rounded-full flex items-center justify-center mb-4">
            <Leaf className="w-8 h-8" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">CarbonShift AI</h1>
          <p className="text-muted-foreground text-sm mt-1">Sign in to your organization workspace</p>
        </div>

        <form onSubmit={handleSignIn} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Work Email</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-input border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-chart-1 transition-colors"
              placeholder="you@company.com" 
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input 
              type="password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-input border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-chart-1 transition-colors"
              placeholder="••••••••" 
            />
          </div>

          {error && <p className="text-sm text-destructive font-medium">{error}</p>}
          {isMock && !error && (
            <p className="text-xs text-amber-500 font-medium flex items-center gap-1">
              <Lock className="w-3 h-3" /> Running in Local Demo Mode. Any password works.
            </p>
          )}

          <div className="flex gap-3 pt-4">
            <button 
              type="button" 
              onClick={handleSignUp}
              disabled={loading}
              className="flex-1 py-3 px-4 bg-muted text-foreground font-semibold rounded-xl hover:bg-muted/80 transition-all text-sm disabled:opacity-50"
            >
              Sign Up
            </button>
            <button 
              type="submit" 
              disabled={loading}
              className="flex-1 py-3 px-4 bg-chart-1 text-white font-semibold rounded-xl hover:bg-chart-1/90 transition-all text-sm shadow-lg shadow-chart-1/20 disabled:opacity-50"
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
