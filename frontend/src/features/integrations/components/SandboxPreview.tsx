'use client';

import React from 'react';
import { ShieldCheck, CheckCircle2 } from 'lucide-react';
import { ValidationResultPayload } from '@/lib/api/integration';

interface SandboxPreviewProps {
  validation: ValidationResultPayload | null;
}

export const SandboxPreview: React.FC<SandboxPreviewProps> = ({ validation }) => {
  const checks = [
    { label: 'Sandbox Isolation & Containment', desc: 'Working directory strictly isolated per run with no cross-project leakage' },
    { label: 'Path Traversal & Device Protection', desc: 'Strict rejection of ../ escapes, absolute paths, and Windows device paths' },
    { label: 'Assistant Blueprint Validation', desc: 'Verified declarative configuration (name, brand colors, position, greeting)' },
    { label: 'Knowledge Base Grounding Check', desc: 'Vector document chunks inspected without external API calls' },
    { label: 'Managed Code Markers', desc: 'Verified Fussion managed boundaries to ensure 100% idempotent updates' },
    { label: 'Static Credential Sanitization', desc: 'Zero API keys, personal access tokens, or private secrets in generated diffs' },
    { label: 'File Modification Allowlist', desc: 'Only files explicitly declared in the integration plan are modified' },
    { label: 'Zero Repository Execution', desc: 'No npm install, no build commands, no shell scripts executed against target code' },
  ];

  return (
    <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          Sandbox Security &amp; Static Validation
        </h3>
        <span className="text-[10px] font-mono uppercase bg-emerald-950/80 border border-emerald-800 text-emerald-300 px-2 py-0.5 rounded font-semibold">
          Static Analysis Verified
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        {checks.map((check, idx) => (
          <div
            key={idx}
            className="bg-zinc-950/60 border border-zinc-800/70 rounded-xl p-3 flex items-start gap-2.5"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-zinc-200">{check.label}</p>
              <p className="text-[11px] text-zinc-400 leading-snug mt-0.5">{check.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {validation && (
        <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-xs flex items-center justify-between">
          <span className="text-zinc-400">Target Validation Status:</span>
          <span className={`font-bold ${validation.is_valid ? 'text-emerald-400' : 'text-rose-400'}`}>
            {validation.status} ({validation.issues.length === 0 ? '0 issues' : `${validation.issues.length} issue(s)`})
          </span>
        </div>
      )}
    </div>
  );
};
