import React from 'react';
import { CheckCircle2, Circle, Sparkles } from 'lucide-react';

const REQUIRED_SLOTS = [
  { key: 'chief_complaint', label: 'Chief Complaint', category: 'Primary' },
  { key: 'onset', label: 'Onset', category: 'History' },
  { key: 'duration', label: 'Duration', category: 'History' },
  { key: 'location', label: 'Location / Radiation', category: 'Physical' },
  { key: 'severity', label: 'Severity Scale (1-10)', category: 'Physical' },
  { key: 'symptoms', label: 'Associated Symptoms', category: 'Clinical' },
  { key: 'past_medical_history', label: 'Past Medical History', category: 'Background' },
  { key: 'medications', label: 'Current Medications', category: 'Background' },
  { key: 'allergies', label: 'Known Allergies', category: 'Safety' },
  { key: 'lifestyle', label: 'Lifestyle / Habits', category: 'Background' },
];

export default function SlotChecklist({ dialogueState, isCompact = false }) {
  const collectedInfo = dialogueState?.collected_info || {};

  const totalSlots = REQUIRED_SLOTS.length;
  const collectedCount = REQUIRED_SLOTS.filter(
    (slot) => collectedInfo[slot.key] !== undefined && collectedInfo[slot.key] !== null
  ).length;

  const percentage = Math.round((collectedCount / totalSlots) * 100);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-card p-4 sm:p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-teal-50 text-teal-700 rounded-xl">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-sm sm:text-base">
              Clinical Memory Slots
            </h3>
            <p className="text-xs text-slate-500">Session slot elicitation progress</p>
          </div>
        </div>
        <span className="text-xs font-bold text-teal-900 bg-teal-50 px-2.5 py-1 rounded-full border border-teal-200">
          {collectedCount} / {totalSlots} Elicited
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
        <div
          className="bg-gradient-to-r from-medical-600 to-teal-500 h-full transition-all duration-300 rounded-full"
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Slot Grid */}
      <div className={`grid gap-2 ${isCompact ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2'}`}>
        {REQUIRED_SLOTS.map((slot) => {
          const isCollected = collectedInfo[slot.key] !== undefined && collectedInfo[slot.key] !== null;
          const value = collectedInfo[slot.key];

          return (
            <div
              key={slot.key}
              className={`flex items-start justify-between p-2.5 rounded-xl text-xs transition-all border ${
                isCollected
                  ? 'bg-teal-50/50 border-teal-200 text-teal-950 shadow-sm'
                  : 'bg-slate-50/60 border-slate-200/80 text-slate-500'
              }`}
            >
              <div className="flex items-start space-x-2 min-w-0 pr-2">
                {isCollected ? (
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0 mt-0.5" />
                ) : (
                  <Circle className="w-4 h-4 text-slate-300 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0">
                  <span className={`font-bold block ${isCollected ? 'text-slate-900' : 'text-slate-700'}`}>
                    {slot.label}
                  </span>
                  {isCollected ? (
                    <span className="font-medium text-teal-800 block truncate max-w-[180px]">
                      {String(value)}
                    </span>
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">Not elicited yet</span>
                  )}
                </div>
              </div>

              <span
                className={`text-[9px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider shrink-0 ${
                  isCollected ? 'bg-teal-100 text-teal-900 font-bold' : 'bg-slate-200 text-slate-600'
                }`}
              >
                {slot.category}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
