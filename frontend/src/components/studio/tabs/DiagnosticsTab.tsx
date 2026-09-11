'use client';

import React, { useState } from 'react';
import {
  DiscoveryRun,
  ApiContract,
  IntegrationPlan,
  IntegrationAdapter,
  ExecutionPlan,
  RepositorySnapshot,
} from '@/lib/api';
import {
  Activity,
  Route,
  FileCheck,
  KeyRound,
  Workflow,
  ListOrdered,
  Lock,
  Ban,
  Shield,
  RefreshCw,
  Plug,
  AlertTriangle,
  FileCode,
  Binary,
  CheckCircle2,
} from 'lucide-react';

interface DiagnosticsTabProps {
  selectedSnapshotId: string;
  snapshots: RepositorySnapshot[];
  discoveries: DiscoveryRun[];
  selectedDiscovery: DiscoveryRun | null;
  isRunningDiscovery: boolean;
  onRunDiscovery: (snap: RepositorySnapshot) => void;
  contracts: ApiContract[];
  selectedContract: ApiContract | null;
  isNormalizingContract: boolean;
  onNormalizeContract: (snap: RepositorySnapshot) => void;
  integrationPlans: IntegrationPlan[];
  selectedPlan: IntegrationPlan | null;
  isGeneratingPlan: boolean;
  onGeneratePlan: (snap: RepositorySnapshot) => void;
  adapters: IntegrationAdapter[];
  selectedAdapter: IntegrationAdapter | null;
  onSelectAdapter: (adapter: IntegrationAdapter) => void;
  isPlanningAdapters: boolean;
  onPlanAdapters: (snap: RepositorySnapshot) => void;
  executionPlans: ExecutionPlan[];
  selectedExecutionPlan: ExecutionPlan | null;
  isGeneratingExecutionPlan: boolean;
  onGenerateExecutionPlan: (snap: RepositorySnapshot) => void;
}

export const DiagnosticsTab: React.FC<DiagnosticsTabProps> = ({
  selectedSnapshotId,
  snapshots,
  discoveries,
  selectedDiscovery,
  isRunningDiscovery,
  onRunDiscovery,
  contracts,
  selectedContract,
  isNormalizingContract,
  onNormalizeContract,
  integrationPlans,
  selectedPlan,
  isGeneratingPlan,
  onGeneratePlan,
  adapters,
  selectedAdapter,
  onSelectAdapter,
  isPlanningAdapters,
  onPlanAdapters,
  executionPlans,
  selectedExecutionPlan,
  isGeneratingExecutionPlan,
  onGenerateExecutionPlan,
}) => {
  const [diagSection, setDiagSection] = useState<
    'discovery' | 'contracts' | 'planning' | 'adapters'
  >('discovery');

  // Discovery internal sub-tabs
  const [activeDiscTab, setActiveDiscTab] = useState<
    'overview' | 'frameworks' | 'entrypoints' | 'routes' | 'dependencies'
  >('overview');

  // Contract internal sub-tabs
  const [contractTab, setContractTab] = useState<
    'reconciliation' | 'operations' | 'auth' | 'schemas'
  >('reconciliation');

  const currentSnapshot = snapshots.find((s) => s.id === selectedSnapshotId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-amber-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">
              Technical Details &amp; Engineering Diagnostics
            </h1>
            <span className="text-[10px] font-mono uppercase bg-amber-950/80 border border-amber-800 text-amber-300 px-2 py-0.5 rounded font-semibold">
              Post-MVP / Diagnostic Tooling
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Low-level repository AST inspection, contract reconciliation, credential cataloging,
            and declarative adapter models.
          </p>
        </div>
      </div>

      {/* Sub-Navigation for Diagnostics */}
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 overflow-x-auto text-xs">
        <button
          onClick={() => setDiagSection('discovery')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-colors ${
            diagSection === 'discovery'
              ? 'bg-zinc-800 text-white border border-zinc-700'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          <Route className="w-3.5 h-3.5" />
          <span>Architecture Discovery</span>
        </button>

        <button
          onClick={() => setDiagSection('contracts')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-colors ${
            diagSection === 'contracts'
              ? 'bg-zinc-800 text-white border border-zinc-700'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          <FileCheck className="w-3.5 h-3.5" />
          <span>API Contracts &amp; Reconciliation</span>
        </button>

        <button
          onClick={() => setDiagSection('planning')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-colors ${
            diagSection === 'planning'
              ? 'bg-zinc-800 text-white border border-zinc-700'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          <KeyRound className="w-3.5 h-3.5" />
          <span>Integration Planning &amp; Credentials</span>
        </button>

        <button
          onClick={() => setDiagSection('adapters')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-colors ${
            diagSection === 'adapters'
              ? 'bg-zinc-800 text-white border border-zinc-700'
              : 'text-zinc-400 hover:text-white'
          }`}
        >
          <Workflow className="w-3.5 h-3.5" />
          <span>Adapters &amp; Execution Plans</span>
        </button>
      </div>

      {/* SECTION 1: ARCHITECTURE DISCOVERY */}
      {diagSection === 'discovery' && (
        <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
            <div>
              <h2 className="text-sm font-semibold text-white">Static Architecture Discovery</h2>
              <p className="text-xs text-zinc-400">
                AST parsing, entrypoint detection, routes, and dependency manifests.
              </p>
            </div>
            {currentSnapshot && (
              <button
                onClick={() => onRunDiscovery(currentSnapshot)}
                disabled={isRunningDiscovery}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600/90 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isRunningDiscovery ? 'animate-spin' : ''}`} />
                <span>{isRunningDiscovery ? 'Discovering...' : 'Run Discovery'}</span>
              </button>
            )}
          </div>

          {selectedDiscovery && (
            <div className="space-y-4">
              {/* Internal Tab Bar */}
              <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 text-xs font-mono">
                {(['overview', 'frameworks', 'entrypoints', 'routes', 'dependencies'] as const).map(
                  (tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveDiscTab(tab)}
                      className={`px-2.5 py-1 rounded uppercase ${
                        activeDiscTab === tab
                          ? 'bg-zinc-800 text-indigo-300 font-bold'
                          : 'text-zinc-400 hover:text-white'
                      }`}
                    >
                      {tab}
                    </button>
                  )
                )}
              </div>

              {activeDiscTab === 'overview' && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                    <span className="text-zinc-400 block text-[10px]">FRAMEWORKS</span>
                    <span className="text-white font-bold text-sm">
                      {selectedDiscovery.metadata.frameworks?.length || 0}
                    </span>
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                    <span className="text-zinc-400 block text-[10px]">ROUTES</span>
                    <span className="text-white font-bold text-sm">
                      {selectedDiscovery.metadata.routes?.length || 0}
                    </span>
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                    <span className="text-zinc-400 block text-[10px]">DEPENDENCIES</span>
                    <span className="text-white font-bold text-sm">
                      {selectedDiscovery.metadata.dependencies?.length || 0}
                    </span>
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg">
                    <span className="text-zinc-400 block text-[10px]">ENTRYPOINTS</span>
                    <span className="text-white font-bold text-sm">
                      {selectedDiscovery.metadata.entrypoints?.length || 0}
                    </span>
                  </div>
                </div>
              )}

              {activeDiscTab === 'frameworks' && (
                <div className="space-y-2 text-xs">
                  {selectedDiscovery.metadata.frameworks?.map((fw, idx) => (
                    <div
                      key={idx}
                      className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg flex items-center justify-between"
                    >
                      <span className="font-bold text-white">{fw.name}</span>
                      <span className="font-mono text-zinc-400">{fw.version || 'detected'}</span>
                    </div>
                  ))}
                </div>
              )}

              {activeDiscTab === 'entrypoints' && (
                <div className="space-y-2 text-xs font-mono">
                  {selectedDiscovery.metadata.entrypoints?.map((ep, idx) => (
                    <div
                      key={idx}
                      className="bg-zinc-900 border border-zinc-800 p-3 rounded-lg flex items-center justify-between"
                    >
                      <span className="text-indigo-300 font-bold">{ep.path}</span>
                      <span className="text-zinc-400">{ep.framework}</span>
                    </div>
                  ))}
                </div>
              )}

              {activeDiscTab === 'routes' && (
                <div className="space-y-2 text-xs font-mono">
                  {selectedDiscovery.metadata.routes?.map((r, idx) => (
                    <div
                      key={idx}
                      className="bg-zinc-900 border border-zinc-800 p-2.5 rounded-lg flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-bold">{r.method}</span>
                        <span className="text-white">{r.path}</span>
                      </div>
                      <span className="text-zinc-500 text-[11px]">{r.source_file}</span>
                    </div>
                  ))}
                </div>
              )}

              {activeDiscTab === 'dependencies' && (
                <div className="space-y-1.5 text-xs font-mono">
                  {selectedDiscovery.metadata.dependencies?.map((dep, idx) => (
                    <div
                      key={idx}
                      className="bg-zinc-900 border border-zinc-800 p-2 rounded flex items-center justify-between"
                    >
                      <span className="text-white">{dep.name}</span>
                      <span className="text-zinc-400">{dep.version_spec}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* SECTION 2: API CONTRACTS & RECONCILIATION */}
      {diagSection === 'contracts' && (
        <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
            <div>
              <h2 className="text-sm font-semibold text-white">
                API Contracts &amp; 4-Bucket Route Reconciliation
              </h2>
              <p className="text-xs text-zinc-400">
                Reconciliation between documented OpenAPI endpoints and static code routes.
              </p>
            </div>
            {currentSnapshot && (
              <button
                onClick={() => onNormalizeContract(currentSnapshot)}
                disabled={isNormalizingContract}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/90 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isNormalizingContract ? 'animate-spin' : ''}`} />
                <span>{isNormalizingContract ? 'Normalizing...' : 'Normalize Contract'}</span>
              </button>
            )}
          </div>

          {selectedContract && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="bg-emerald-950/30 border border-emerald-800/60 p-3 rounded-lg">
                  <span className="text-emerald-400 block text-[10px]">MATCHED</span>
                  <span className="text-emerald-200 font-bold text-base">
                    {selectedContract.reconciliation?.matched_count || 0}
                  </span>
                </div>
                <div className="bg-sky-950/30 border border-sky-800/60 p-3 rounded-lg">
                  <span className="text-sky-400 block text-[10px]">DOCS ONLY</span>
                  <span className="text-sky-200 font-bold text-base">
                    {selectedContract.reconciliation?.documented_only_count || 0}
                  </span>
                </div>
                <div className="bg-amber-950/30 border border-amber-800/60 p-3 rounded-lg">
                  <span className="text-amber-400 block text-[10px]">CODE ONLY</span>
                  <span className="text-amber-200 font-bold text-base">
                    {selectedContract.reconciliation?.implemented_only_count || 0}
                  </span>
                </div>
                <div className="bg-rose-950/30 border border-rose-800/60 p-3 rounded-lg">
                  <span className="text-rose-400 block text-[10px]">CONFLICT</span>
                  <span className="text-rose-200 font-bold text-base">
                    {selectedContract.reconciliation?.conflict_count || 0}
                  </span>
                </div>
              </div>

              {/* Findings list */}
              <div className="space-y-1.5 text-xs font-mono">
                {selectedContract.reconciliation?.findings?.map((f, idx) => (
                  <div
                    key={idx}
                    className="bg-zinc-900 border border-zinc-800 p-2.5 rounded-lg flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase font-bold text-emerald-400 bg-emerald-950 px-1.5 py-0.5 rounded border border-emerald-800">
                        {f.category}
                      </span>
                      <span className="text-white font-bold">{f.method}</span>
                      <span className="text-zinc-300">{f.path}</span>
                    </div>
                    <span className="text-zinc-500 text-[11px] font-sans">{f.details}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* SECTION 3: INTEGRATION PLANNING & CREDENTIALS */}
      {diagSection === 'planning' && (
        <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
            <div>
              <h2 className="text-sm font-semibold text-white">
                Integration Planning &amp; Credential Safety
              </h2>
              <p className="text-xs text-zinc-400">
                Identified backend cloud dependencies (Postgres, Redis, Stripe, S3) and required variable names.
              </p>
            </div>
            {currentSnapshot && (
              <button
                onClick={() => onGeneratePlan(currentSnapshot)}
                disabled={isGeneratingPlan}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600/90 hover:bg-violet-500 text-white rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingPlan ? 'animate-spin' : ''}`} />
                <span>{isGeneratingPlan ? 'Generating...' : 'Generate Plan'}</span>
              </button>
            )}
          </div>

          {selectedPlan && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {selectedPlan.candidates?.map((cand, idx) => (
                  <div key={idx} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 space-y-1 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white">{cand.name}</span>
                      <span className="text-[10px] font-mono bg-violet-950 text-violet-300 border border-violet-800 px-2 py-0.5 rounded uppercase">
                        {cand.type}
                      </span>
                    </div>
                    <p className="text-zinc-400 text-[11px]">{cand.description}</p>
                  </div>
                ))}
              </div>

              {/* Required Credentials Table */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider block">
                  Cataloged Configuration Variable Keys (Zero Secrets Persisted)
                </span>
                <div className="divide-y divide-zinc-800/60 font-mono text-xs">
                  {selectedPlan.required_credentials?.map((cred, idx) => (
                    <div key={idx} className="py-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Lock className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-white font-bold">{cred.name}</span>
                      </div>
                      <span className="text-zinc-400 text-[11px] font-sans">{cred.service}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SECTION 4: ADAPTERS & EXECUTION PLANS */}
      {diagSection === 'adapters' && (
        <div className="space-y-6">
          {/* Adapters Panel */}
          <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <h2 className="text-sm font-semibold text-white">Declarative Integration Adapters</h2>
              {currentSnapshot && (
                <button
                  onClick={() => onPlanAdapters(currentSnapshot)}
                  disabled={isPlanningAdapters}
                  className="flex items-center gap-1.5 px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${isPlanningAdapters ? 'animate-spin' : ''}`} />
                  <span>Plan Adapters</span>
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {adapters.map((adp) => (
                <div
                  key={adp.id}
                  onClick={() => onSelectAdapter(adp)}
                  className={`border rounded-lg p-3 text-xs cursor-pointer transition-colors ${
                    selectedAdapter?.id === adp.id
                      ? 'bg-indigo-950/40 border-indigo-500'
                      : 'bg-zinc-900 border-zinc-800 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">{adp.name}</span>
                    <span className="text-[10px] font-mono uppercase bg-indigo-950 text-indigo-300 border border-indigo-800 px-1.5 py-0.5 rounded">
                      {adp.adapter_type}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-1 font-mono">
                    Provider: {adp.provider || 'none'} | {adp.operations?.length || 0} operations
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Execution Plan Panel */}
          <div className="bg-zinc-950/40 border border-zinc-800/90 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Execution Plan DAG &amp; Safety</h2>
                <p className="text-xs text-zinc-400">
                  Deterministic prerequisite sequence with strictly blocked external boundary.
                </p>
              </div>
              {currentSnapshot && (
                <button
                  onClick={() => onGenerateExecutionPlan(currentSnapshot)}
                  disabled={isGeneratingExecutionPlan}
                  className="flex items-center gap-1.5 px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${isGeneratingExecutionPlan ? 'animate-spin' : ''}`} />
                  <span>Generate Plan</span>
                </button>
              )}
            </div>

            {/* Non-execution notice */}
            <div className="bg-amber-950/30 border border-amber-800/60 rounded-lg p-3 text-xs text-amber-200 flex items-start gap-2">
              <Ban className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <span>
                <strong className="text-amber-300">Strict Non-Execution Invariant:</strong> External
                actions remain safely blocked. No external systems are called and zero repository code is executed.
              </span>
            </div>

            {selectedExecutionPlan && (
              <div className="space-y-2 font-mono text-xs">
                {selectedExecutionPlan.steps?.map((st) => (
                  <div
                    key={st.step_id}
                    className="bg-zinc-900 border border-zinc-800 rounded-lg p-2.5 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-amber-400 font-bold">{st.step_id}</span>
                      <span className="text-white font-sans font-medium">{st.name}</span>
                    </div>
                    <span className="text-[10px] uppercase font-bold text-rose-300 bg-rose-950 border border-rose-800 px-2 py-0.5 rounded">
                      {st.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
