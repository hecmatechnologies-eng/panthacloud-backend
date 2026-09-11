'use client';

import React from 'react';
import { History, GitCommit, GitBranch, ExternalLink, Eye, X, AlertCircle } from 'lucide-react';
import { IntegrationRun, RunDiffPayload } from '@/lib/api/integration';

interface IntegrationHistoryProps {
  runs: IntegrationRun[];
  selectedDiff: RunDiffPayload | null;
  onViewDiff: (runId: string) => void;
  onCancelRun: (runId: string) => void;
  onCloseDiff: () => void;
}

export const IntegrationHistory: React.FC<IntegrationHistoryProps> = ({
  runs,
  selectedDiff,
  onViewDiff,
  onCancelRun,
  onCloseDiff,
}) => {
  return (
    <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <History className="w-4 h-4 text-zinc-300" />
            Integration Run History
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5">
            Audit log of all isolated sandbox integration attempts and Pull Requests.
          </p>
        </div>
        <span className="text-xs text-zinc-500 font-mono font-semibold">
          {runs.length} run(s)
        </span>
      </div>

      {runs.length === 0 ? (
        <div className="text-center py-8 bg-zinc-950/40 border border-dashed border-zinc-800 rounded-xl">
          <p className="text-xs text-zinc-500">No integration runs recorded yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-400 text-[11px] uppercase tracking-wider">
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Branch</th>
                <th className="py-2.5 px-3">Commit</th>
                <th className="py-2.5 px-3">Pull Request</th>
                <th className="py-2.5 px-3">Changes</th>
                <th className="py-2.5 px-3">Date</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 font-mono text-[12px]">
              {runs.map((run) => (
                <tr key={run.id} className="hover:bg-zinc-950/40 transition-colors">
                  {/* Status */}
                  <td className="py-3 px-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        run.status === 'PR_CREATED'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : run.status === 'FAILED'
                          ? 'bg-rose-950 text-rose-300 border border-rose-800'
                          : run.status === 'CANCELLED'
                          ? 'bg-zinc-800 text-zinc-400'
                          : 'bg-indigo-950 text-indigo-300 border border-indigo-800 animate-pulse'
                      }`}
                    >
                      {run.status}
                    </span>
                  </td>

                  {/* Branch */}
                  <td className="py-3 px-3 text-zinc-300 truncate max-w-[160px]">
                    <span className="flex items-center gap-1">
                      <GitBranch className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                      {run.branch_name}
                    </span>
                  </td>

                  {/* Commit */}
                  <td className="py-3 px-3 text-zinc-400 truncate max-w-[120px]">
                    {run.commit_sha ? (
                      <span className="flex items-center gap-1">
                        <GitCommit className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                        {run.commit_sha.slice(0, 10)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>

                  {/* PR */}
                  <td className="py-3 px-3">
                    {run.pull_request_url ? (
                      <a
                        href={run.pull_request_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 underline flex items-center gap-1 font-semibold"
                      >
                        <span>PR #{run.pull_request_number}</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <span className="text-zinc-500">—</span>
                    )}
                  </td>

                  {/* Changes */}
                  <td className="py-3 px-3 text-zinc-300">
                    +{run.generated_files_count} / ~{run.modified_files_count}
                  </td>

                  {/* Date */}
                  <td className="py-3 px-3 text-zinc-400 font-sans text-xs">
                    {new Date(run.created_at).toLocaleDateString()}{' '}
                    <span className="text-zinc-500 text-[11px]">
                      {new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </td>

                  {/* Actions */}
                  <td className="py-3 px-3 text-right space-x-2">
                    <button
                      type="button"
                      onClick={() => onViewDiff(run.id)}
                      className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] font-sans font-semibold transition-colors inline-flex items-center gap-1"
                    >
                      <Eye className="w-3 h-3 text-zinc-400" />
                      <span>Diff</span>
                    </button>

                    {(run.status === 'RUNNING' || run.status === 'PENDING') && (
                      <button
                        type="button"
                        onClick={() => onCancelRun(run.id)}
                        className="px-2.5 py-1 rounded bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 text-[11px] font-sans font-semibold transition-colors inline-flex items-center gap-1"
                      >
                        <span>Cancel</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Diff Inspection Modal */}
      {selectedDiff && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-zinc-800">
              <div>
                <h4 className="text-sm font-bold text-white">Generated Artifact Diff Inspection</h4>
                <p className="text-xs text-zinc-400 font-mono mt-0.5">{selectedDiff.summary}</p>
              </div>
              <button
                type="button"
                onClick={onCloseDiff}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4 font-mono text-xs">
              {selectedDiff.files.map((file, idx) => (
                <div key={idx} className="bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden">
                  <div className="bg-zinc-900/80 px-4 py-2 border-b border-zinc-800 flex items-center justify-between">
                    <span className="font-semibold text-zinc-200">{file.path}</span>
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                        file.action === 'create'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                      }`}
                    >
                      {file.action}
                    </span>
                  </div>
                  <pre className="p-4 text-[11px] leading-relaxed text-zinc-300 overflow-x-auto whitespace-pre">
                    {file.diff}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
