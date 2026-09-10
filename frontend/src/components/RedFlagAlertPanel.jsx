import React from 'react';
import { AlertOctagon, ShieldAlert, AlertTriangle, ArrowUpRight } from 'lucide-react';

export default function RedFlagAlertPanel({ redFlags }) {
  if (!redFlags || redFlags.length === 0) {
    return (
      <div className="bg-emerald-50/60 border border-emerald-200/80 rounded-2xl p-4 flex items-center space-x-3 text-xs text-emerald-800">
        <div className="p-2 bg-emerald-100 rounded-xl text-emerald-600 shrink-0">
          <ShieldAlert className="w-5 h-5" />
        </div>
        <div>
          <span className="font-semibold text-emerald-950 block">No Active Red Flags Detected</span>
          <span className="text-emerald-700">Live safety evaluation running continuously on turn input.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-rose-50 border-2 border-rose-300 rounded-2xl p-4 sm:p-5 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-rose-900">
          <AlertOctagon className="w-5 h-5 text-rose-600 animate-pulse" />
          <h3 className="font-bold text-sm sm:text-base">
            Safety Intercept Alerts ({redFlags.length})
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-wider font-bold bg-rose-200 text-rose-900 px-2.5 py-1 rounded-full">
          Physician Review Required
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
                  ? 'bg-white border-rose-400 shadow-sm'
                  : 'bg-rose-100/50 border-rose-200'
              }`}
            >
              <div className="flex items-start justify-between mb-1.5">
                <span className="font-bold text-slate-900 text-sm">
                  {rf.title || rf.category || 'Red Flag Event'}
                </span>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${
                    isTier1
                      ? 'bg-rose-600 text-white'
                      : tier === 2
                      ? 'bg-amber-500 text-white'
                      : 'bg-slate-700 text-white'
                  }`}
                >
                  Tier {tier}
                </span>
              </div>

              {rf.trigger_text && (
                <div className="text-rose-950 font-medium bg-rose-50 border border-rose-200 rounded-lg p-2 mb-2 font-mono text-[11px]">
                  Trigger context: "{rf.trigger_text}"
                </div>
              )}

              <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                <span>Rule ID: {rf.rule_id || 'RF-DETECTED'}</span>
                <span>Category: {rf.category || 'Clinical Triage'}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
