import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Leaf, Clock, Zap, Database, BarChart2, Settings, Sliders, TrendingUp, RefreshCw } from 'lucide-react';
import {
  fetchMetrics, fetchRuns, resetDemo, fetchJobs, fetchSites, fetchGreenWindows
} from './api';

// Pages
import CommandCenter from './pages/CommandCenter';
import JobQueuePage from './pages/JobQueuePage';
import ScheduleStudio from './pages/ScheduleStudio';
import GridForecastPage from './pages/GridForecastPage';
import SimulatorPage from './pages/SimulatorPage';
import ImpactLedger from './pages/ImpactLedger';
import SettingsPage from './pages/SettingsPage';
import AuthPage from './pages/AuthPage';
import { supabase } from './lib/supabase';
import { motion, AnimatePresence } from 'framer-motion';

type Tab = 'home' | 'jobs' | 'schedule' | 'forecast' | 'simulator' | 'impact' | 'settings';

const NAV: { id: Tab; label: string; icon: React.FC<any> }[] = [
  { id: 'home', label: 'Command Center', icon: Activity },
  { id: 'jobs', label: 'Job Queue', icon: Clock },
  { id: 'schedule', label: 'Schedule Studio', icon: BarChart2 },
  { id: 'forecast', label: 'Grid Forecast', icon: Zap },
  { id: 'simulator', label: 'What-If Simulator', icon: Sliders },
  { id: 'impact', label: 'Impact Ledger', icon: TrendingUp },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [metrics, setMetrics] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [sites, setSites] = useState<any[]>([]);
  const [greenWindows, setGreenWindows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [user, setUser] = useState<any>(null);

  // Check auth on load
  useEffect(() => {
    if (import.meta.env.VITE_SUPABASE_URL) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        setUser(session?.user ?? null);
      });
      supabase.auth.onAuthStateChange((_event, session) => {
        setUser(session?.user ?? null);
      });
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        fetchMetrics(),
        fetchRuns(),
        fetchJobs(),
        fetchSites(),
        fetchGreenWindows(undefined, 12),
      ]);
      if (results[0].status === 'fulfilled') setMetrics(results[0].value);
      if (results[1].status === 'fulfilled') setRuns(results[1].value);
      if (results[2].status === 'fulfilled') setJobs(results[2].value);
      if (results[3].status === 'fulfilled') setSites(results[3].value);
      if (results[4].status === 'fulfilled') setGreenWindows(results[4].value);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleDemoReset = async () => {
    setResetting(true);
    try {
      await resetDemo();
      await loadData();
    } catch (e: any) {
      alert('Reset failed: ' + e.message);
    } finally {
      setResetting(false);
    }
  };

  const sharedProps = { metrics, runs, jobs, sites, greenWindows, onRefresh: loadData, user };

  if (!user) {
    return <AuthPage onLogin={setUser} />;
  }

  const handleLogout = async () => {
    if (import.meta.env.VITE_SUPABASE_URL) {
      await supabase.auth.signOut();
    }
    setUser(null);
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-background text-foreground flex font-sans selection:bg-chart-1/30">
      {/* Sidebar */}
      <aside className="w-60 border-r border-border bg-card flex flex-col shrink-0">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 py-5 border-b border-border">
          <Leaf className="w-7 h-7 text-chart-1 shrink-0" />
          <div>
            <h1 className="text-lg font-black tracking-tight leading-none">CarbonShift</h1>
            <p className="text-[10px] text-muted-foreground font-medium tracking-widest uppercase">India · AI</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 p-3 flex-1">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-left ${
                activeTab === id
                  ? 'bg-chart-1/15 text-chart-1 shadow-sm'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-border flex flex-col gap-2">
          <button
            onClick={loadData}
            className="flex items-center justify-center gap-2 px-3 py-2 w-full rounded-lg text-xs font-medium border border-border hover:bg-muted transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          
          <div className="pt-2 mt-2 border-t border-border flex items-center justify-between px-1">
            <div className="truncate text-xs font-medium text-muted-foreground">{user?.email}</div>
            <button onClick={handleLogout} className="text-xs text-chart-1 font-bold hover:underline">Logout</button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-background relative">
        {loading && activeTab === 'home' ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Leaf className="w-12 h-12 text-chart-1 mx-auto mb-4 animate-pulse" />
              <p className="text-muted-foreground">Loading CarbonShift AI…</p>
            </div>
          </div>
        ) : (
          <>
            {activeTab === 'home' && <CommandCenter {...sharedProps} />}
            {activeTab === 'jobs' && <JobQueuePage {...sharedProps} />}
            {activeTab === 'schedule' && <ScheduleStudio {...sharedProps} />}
            {activeTab === 'forecast' && <GridForecastPage {...sharedProps} />}
            {activeTab === 'simulator' && <SimulatorPage {...sharedProps} />}
            {activeTab === 'impact' && <ImpactLedger {...sharedProps} />}
            {activeTab === 'settings' && <SettingsPage {...sharedProps} />}
          </>
        )}
      </main>
    </div>
  );
}
