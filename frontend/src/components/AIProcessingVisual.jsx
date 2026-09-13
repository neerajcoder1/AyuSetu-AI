import React from 'react';
import { Sparkles, Activity, ShieldCheck } from 'lucide-react';

export default function AIProcessingVisual({ message = "AyuSetu AI is analyzing your response..." }) {
  return (
    <div className="w-full bg-gradient-to-b from-sky-50/90 via-white to-slate-50/80 border border-sky-200/90 rounded-2xl p-6 sm:p-7 shadow-sm text-center space-y-4 my-4 animate-in fade-in duration-300">
      {/* Central Clinical AI Visualization Container */}
      <div className="relative flex items-center justify-center h-28 w-28 mx-auto">
        {/* Outer Pulsing Medical Ring */}
        <div
          className="absolute inset-0 rounded-full border-2 border-sky-400/40 animate-ping motion-reduce:animate-none"
          style={{ animationDuration: '3s' }}
        />

        {/* Orbiting Ring with Subtle Rotation */}
        <div
          className="absolute -inset-2 rounded-full border border-dashed border-teal-500/50 animate-spin motion-reduce:animate-none"
          style={{ animationDuration: '8s' }}
        />

        {/* Secondary Concentric Wave Ring */}
        <div className="absolute inset-2 rounded-full bg-gradient-to-tr from-sky-200/50 via-teal-100/30 to-sky-100/60 animate-pulse motion-reduce:animate-none" />

        {/* Central Core Clinical Node */}
        <div className="relative z-10 w-16 h-16 rounded-full bg-gradient-to-tr from-sky-600 via-sky-700 to-teal-600 text-white flex items-center justify-center shadow-md border-2 border-white/80">
          <Activity className="w-8 h-8 text-sky-100 animate-pulse motion-reduce:animate-none" />
        </div>

        {/* Floating Sparkle Nodes */}
        <div className="absolute -top-1 -right-1 p-1 bg-teal-500 text-white rounded-full shadow-sm animate-bounce motion-reduce:animate-none">
          <Sparkles className="w-3.5 h-3.5" />
        </div>
      </div>

      {/* Clinical Processing Status Text */}
      <div className="space-y-1.5 max-w-md mx-auto">
        <div className="inline-flex items-center space-x-1.5 px-3 py-0.5 rounded-full bg-sky-100/80 border border-sky-200/90 text-sky-800 text-[11px] font-extrabold uppercase tracking-wider">
          <ShieldCheck className="w-3.5 h-3.5 text-sky-600 shrink-0" />
          <span>AyuSetu Clinical AI Active</span>
        </div>

        <h4 className="text-sm sm:text-base font-extrabold text-slate-900 tracking-tight">
          {message}
        </h4>

        <p className="text-xs text-slate-500 font-medium leading-relaxed">
          Transcribing audio, evaluating clinical slots, and preparing Spoken Response...
        </p>
      </div>

      {/* Subdued Progress Bar Indicator */}
      <div className="w-48 h-1.5 bg-slate-200/70 rounded-full mx-auto overflow-hidden">
        <div className="h-full bg-gradient-to-r from-sky-600 to-teal-500 rounded-full animate-pulse motion-reduce:animate-none" />
      </div>
    </div>
  );
}
