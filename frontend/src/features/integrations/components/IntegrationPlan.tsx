'use client';

import React from 'react';
import { FileCode, PlusCircle, Edit3, AlertTriangle, FilePlus } from 'lucide-react';
import { IntegrationPlanPayload } from '@/lib/api/integration';

interface IntegrationPlanProps {
  plan: IntegrationPlanPayload | null;
  onGeneratePlan: () => void;
  isPlanning: boolean;
}

export const IntegrationPlan: React.FC<IntegrationPlanProps> = ({
  plan,
  onGeneratePlan,
  isPlanning,
}) => {
  return (
    <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <FileCode className="w-4 h-4 text-indigo-400" />
            Deterministic Integration Plan
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5">
            Explicit breakdown of files to create and modify before any Git branch is pushed.
          </p>
        </div>
        <button
          type="button"
          onClick={onGeneratePlan}
          disabled={isPlanning}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-300 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          <FilePlus className="w-3.5 h-3.5 text-indigo-400" />
          {isPlanning ? 'Analyzing...' : plan ? 'Refresh Plan' : 'Generate Plan'}
        </button>
      </div>

      {!plan ? (
        <div className="text-center py-8 bg-zinc-950/40 border border-dashed border-zinc-800 rounded-xl space-y-2">
          <p className="text-xs text-zinc-500">No integration plan generated yet.</p>
          <button
            type="button"
            onClick={onGeneratePlan}
            disabled={isPlanning}
            className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold underline"
          >
            Click here to preview planned file changes
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Files to Create */}
          <div className="space-y-2">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <PlusCircle className="w-3.5 h-3.5" />
              Files to Create ({plan.files_to_create.length})
            </h4>
            <div className="space-y-1.5">
              {plan.files_to_create.map((file) => (
                <div
                  key={file}
                  className="bg-zinc-950/60 border border-emerald-950/80 rounded-lg px-3 py-2 text-xs font-mono text-emerald-200 flex items-center gap-2"
                >
                  <span className="text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 px-1.5 py-0.5 rounded">
                    CREATE
                  </span>
                  <span>{file}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Files to Modify */}
          <div className="space-y-2">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
              <Edit3 className="w-3.5 h-3.5" />
              Files to Modify ({plan.files_to_modify.length})
            </h4>
            <div className="space-y-1.5">
              {plan.files_to_modify.map((file) => (
                <div
                  key={file}
                  className="bg-zinc-950/60 border border-indigo-950/80 rounded-lg px-3 py-2 text-xs font-mono text-indigo-200 flex items-center gap-2"
                >
                  <span className="text-[10px] font-bold bg-indigo-950 text-indigo-400 border border-indigo-800 px-1.5 py-0.5 rounded">
                    MODIFY
                  </span>
                  <span>{file}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Warnings */}
          {plan.warnings.length > 0 && (
            <div className="space-y-2 pt-2">
              {plan.warnings.map((w, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 bg-amber-950/40 border border-amber-900/60 text-amber-300 p-3 rounded-xl text-xs leading-relaxed"
                >
                  <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          <div className="text-[11px] text-zinc-500 bg-zinc-950/40 border border-zinc-800/60 rounded-lg p-3">
            ℹ️ <strong>Safety Invariant:</strong> This is a deterministic plan. No code has been executed or committed to your production repository yet.
          </div>
        </div>
      )}
    </div>
  );
};
