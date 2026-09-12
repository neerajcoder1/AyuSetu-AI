import React from 'react';
import { AlertOctagon, ShieldAlert, AlertTriangle, CheckCircle2 } from 'lucide-react';

export default function RedFlagAlertPanel({ redFlags }) {
  if (!redFlags || redFlags.length === 0) {
    return (
      <div className="bg-teal-50/70 border border-teal-200 rounded-2xl p-4 flex items-center space-x-3 text-xs text-teal-900 shadow-card">
        <div className="p-2.5 bg-teal-100/90 rounded-xl text-teal-700 shrink-0">
          <CheckCircle2 className="w-5 h-5" />
        </div>
        <div>
          <span className="font-extrabold text-teal-950 block text-sm">No Active Red Flags Detected</span>
          <span className="text-teal-700 font-medium">Continuous clinical safety triage running on session turns.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-rose-50/90 border-2 border-rose-300 rounded-2xl p-4 sm:p-5 shadow-card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-rose-950">
          <AlertOctagon className="w-5 h-5 text-rose-600 animate-pulse" />
          <h3 className="font-extrabold text-sm sm:text-base tracking-tight">
            Clinical Safety Intercept Alerts ({redFlags.length})
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-wider font-extrabold bg-rose-600 text-white px-2.5 py-1 rounded-full shadow-sm">
          Physician Verification Mandatory
        </span>
      </div>

      <div className="space-y-2.5">
        {redFlags.map((rf, idx) => {
          const tier = rf.tier || 1;
          const isTier1 = tier === 1;

          return (
            <div
              key={rf.rule_id || idx}
              className={`p-3.5 rounded-xl border text-xs transition-all ${
                isTier1
                  ? 'bg-white border-rose-400 shadow-sm ring-1 ring-rose-200'
                  : 'bg-rose-100/60 border-rose-200'
              }`}
            >
              <div className="flex items-start justify-between mb-1.5">
                <span className="font-extrabold text-slate-900 text-sm">
                  {rf.title || rf.category || 'Red Flag Event'}
                </span>
                <span
                  className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-md uppercase tracking-wider ${
                    isTier1
                      ? 'bg-rose-600 text-white'
                      : tier === 2
                      ? 'bg-amber-500 text-white'
                      : 'bg-slate-700 text-white'
                  }`}
                >
                  Tier {tier} Urgent
                </span>
              </div>

              {rf.trigger_text && (
                <div className="text-rose-950 font-bold bg-rose-50 border border-rose-200/90 rounded-lg p-2 mb-2 font-mono text-[11px]">
                  Trigger context: "{rf.trigger_text}"
                </div>
              )}

              <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                <span className="font-semibold">Rule ID: {rf.rule_id || 'RF-DETECTED'}</span>
                <span className="font-semibold">Category: {rf.category || 'Clinical Triage'}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
