import { useState } from 'react';
import { postJson, type Substation } from '../lib/api';

const SCENARIOS = [
  { id: 'nerc-question', label: 'NERC CIP Question', agent: 'cwm-compliance-doc-retrieval', hint: 'What does CIP-013-2 say about supply-chain risk?' },
  { id: 'violation-draft', label: 'Self-Report Draft', agent: 'cwm-violation-report-creation', hint: 'Draft a self-report for the PRC-005 missed maintenance' },
  { id: 'outage-report', label: 'PUC Outage Report', agent: 'cwm-outage-regulatory-reporting', hint: 'Generate the May major-event-day filing for PUC' },
  { id: 'code-conflict', label: 'Code Conflict', agent: 'cwm-codes-standards-interpretation', hint: 'Reconcile NESC vs IEEE 516 on hot-stick clearance' },
  { id: 'crew-question', label: 'Crew Q&A', agent: 'cwm-virtual-training-assistant', hint: 'How do I isolate a faulted feeder during back-feed conditions?' },
  { id: 'course-create', label: 'Build Training Course', agent: 'cwm-training-course-creation', hint: 'Build a 4-hour course on URD splicing from manual M-118' },
  { id: 'safety-pattern', label: 'Safety Pattern', agent: 'cwm-safety-report-analysis', hint: 'Find recurring near-miss patterns in last 90 days' },
  { id: 'storm-deploy', label: 'Storm Deployment Plan', agent: 'cwm-post-storm-crew-deployment', hint: 'Plan crew deployment for 380 outages across 14 districts' },
];

export function ScenarioPanel({ onRan, substations }: { onRan: () => void; substations: Substation[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string>('');
  const sub = substations[0]?.substation_id ?? '';

  async function run(id: string) {
    setBusy(id); setLast('');
    try {
      const body: any = id === 'storm-outage' ? { substation_id: sub, feeder_index: 7 }
                       : id === 'theft'       ? { substation_id: sub, count: 3 }
                       : id === 'heat-wave'   ? {}
                       : { substation_id: sub };
      const r = await postJson<any>(`/api/scenarios/${id}`, body);
      setLast(`✓ ${id} → ${r.agent_dispatched ?? 'dispatched'}`);
      onRan();
    } catch (e: any) { setLast(`error: ${e.message}`); }
    finally { setBusy(null); }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">SCENARIOS</h2>
        <span className="text-xs text-slate-500">click to inject + auto-dispatch agent</span>
      </div>
      <div className="grid grid-cols-4 gap-1.5 flex-1 overflow-y-auto">
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            disabled={!!busy}
            onClick={() => run(s.id)}
            className="text-left p-1.5 rounded-lg bg-grid-bg border border-grid-border hover:border-grid-accent disabled:opacity-50 transition group"
            title={s.hint}
          >
            <div className="text-xs font-medium text-grid-accent leading-tight">{busy === s.id ? '⏳' : s.label}</div>
            <div className="text-xs text-grid-info font-mono mt-0.5">→ {s.agent}</div>
            <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{s.hint}</div>
          </button>
        ))}
      </div>
      {last && <div className="text-xs text-grid-ok mt-1 truncate font-mono">{last}</div>}
    </div>
  );
}
