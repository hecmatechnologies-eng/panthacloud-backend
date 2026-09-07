'use client';

import { useEffect, useState } from 'react';
import { fetchHealth, HealthResponse } from '@/lib/api';
import {
  CheckCircle2,
  XCircle,
  RefreshCw,
  Server,
  Database,
  Layout,
  Layers,
  ArrowRight,
} from 'lucide-react';

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string>('');

  const checkConnectivity = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to connect to backend API');
      setHealth(null);
    } finally {
      setLoading(false);
      setLastChecked(new Date().toLocaleTimeString());
    }
  };

  useEffect(() => {
    checkConnectivity();
  }, []);

  const isBackendHealthy = health?.status === 'healthy';
  const isDatabaseHealthy = health?.database?.status === 'connected';

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6 antialiased">
      <main className="w-full max-w-4xl bg-zinc-900 border border-zinc-800 rounded-2xl p-8 shadow-2xl space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-zinc-800 pb-6 gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Layers className="w-6 h-6 text-indigo-400" />
              <h1 className="text-2xl font-bold tracking-tight text-white">Fussion</h1>
              <span className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-xs px-2.5 py-0.5 rounded-full font-medium">
                Phase 01
              </span>
            </div>
            <p className="text-zinc-400 text-sm">
              Repository &amp; Development Foundation
            </p>
          </div>

          <button
            onClick={checkConnectivity}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-600 text-zinc-200 transition-colors border border-zinc-700/60 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Re-check Status
          </button>
        </div>

        {/* Connectivity Flow Diagram */}
        <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-4">
          <p className="text-xs uppercase tracking-wider font-semibold text-zinc-400 mb-3">
            System Connectivity Pipeline
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
            <span className="px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-200 border border-zinc-700">
              Browser Client
            </span>
            <ArrowRight className="w-4 h-4 text-zinc-500" />
            <span className="px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-200 border border-zinc-700">
              Next.js Frontend
            </span>
            <ArrowRight className="w-4 h-4 text-zinc-500" />
            <span className={`px-3 py-1.5 rounded-md border ${isBackendHealthy ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800' : 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
              FastAPI Backend
            </span>
            <ArrowRight className="w-4 h-4 text-zinc-500" />
            <span className={`px-3 py-1.5 rounded-md border ${isDatabaseHealthy ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800' : 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
              PostgreSQL / Database
            </span>
          </div>
        </div>

        {/* Live Operational Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Frontend Card */}
          <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400 border border-indigo-500/20">
                  <Layout className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Frontend</h2>
                  <p className="text-xs text-zinc-400">Next.js App Router</p>
                </div>
              </div>
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between text-xs">
              <span className="text-zinc-400">Status:</span>
              <span className="text-emerald-400 font-medium">Operational</span>
            </div>
          </div>

          {/* Backend Card */}
          <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400 border border-blue-500/20">
                  <Server className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Backend API</h2>
                  <p className="text-xs text-zinc-400">FastAPI &amp; Uvicorn</p>
                </div>
              </div>
              {isBackendHealthy ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <XCircle className="w-5 h-5 text-rose-400" />
              )}
            </div>
            <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between text-xs">
              <span className="text-zinc-400">Status:</span>
              <span className={`font-medium ${isBackendHealthy ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isBackendHealthy ? 'Operational' : loading ? 'Checking...' : 'Offline'}
              </span>
            </div>
          </div>

          {/* Database Card */}
          <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-amber-500/10 rounded-lg text-amber-400 border border-amber-500/20">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Database</h2>
                  <p className="text-xs text-zinc-400">
                    {health?.database?.type || 'PostgreSQL'}
                  </p>
                </div>
              </div>
              {isDatabaseHealthy ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <XCircle className="w-5 h-5 text-amber-400" />
              )}
            </div>
            <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between text-xs">
              <span className="text-zinc-400">Status:</span>
              <span className={`font-medium ${isDatabaseHealthy ? 'text-emerald-400' : 'text-amber-400'}`}>
                {isDatabaseHealthy ? 'Operational' : loading ? 'Checking...' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>

        {/* Diagnostics & Detail Box */}
        {error && (
          <div className="bg-rose-950/30 border border-rose-800/60 rounded-xl p-4 text-xs text-rose-300">
            <span className="font-semibold">Backend Connection Notice: </span>
            {error}. Ensure the FastAPI server is running on port 8000.
          </div>
        )}

        {/* Phase 01 Checklist Status */}
        <div className="border-t border-zinc-800 pt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-3">
            Phase 01 Foundation Verification
          </h3>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-zinc-400">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              Clean repository structure &amp; governance
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              FastAPI backend with Python 3.13 venv
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              Next.js 16 + TypeScript + Tailwind CSS
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              SQLAlchemy 2.0 &amp; Alembic baseline migration
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              Pytest &amp; Vitest automated test runners
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              Strict production database validation
            </li>
          </ul>
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800/80 pt-4 flex flex-col sm:flex-row items-center justify-between text-xs text-zinc-500 gap-2">
          <span>Last checked: {lastChecked || 'Initial check'}</span>
          <span className="text-zinc-400 font-mono">Next: Phase 02 — Backend Core &amp; Identity</span>
        </div>
      </main>
    </div>
  );
}
