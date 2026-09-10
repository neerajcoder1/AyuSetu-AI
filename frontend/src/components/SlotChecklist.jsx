import React from 'react';
import { CheckCircle2, Circle, AlertCircle, Sparkles } from 'lucide-react';

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
  const missingSlots = dialogueState?.missing_slots || [];

  const totalSlots = REQUIRED_SLOTS.length;
  const collectedCount = REQUIRED_SLOTS.filter(
    (slot) => collectedInfo[slot.key] !== undefined && collectedInfo[slot.key] !== null
  ).length;

  const percentage = Math.round((collectedCount / totalSlots) * 100);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-medical-600" />
          <h3 className="font-semibold text-slate-900 text-sm sm:text-base">
            Clinical Memory Slots
          </h3>
        </div>
        <span className="text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200">
          {collectedCount} / {totalSlots} Collected
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden mb-4">
        <div
          className="bg-gradient-to-r from-medical-500 to-teal-500 h-full transition-all duration-300 rounded-full"
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
                  ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                  : 'bg-slate-50 border-slate-200 text-slate-500'
              }`}
            >
              <div className="flex items-start space-x-2 min-w-0 pr-2">
                {isCollected ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                ) : (
                  <Circle className="w-4 h-4 text-slate-300 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0">
                  <span className={`font-semibold block ${isCollected ? 'text-emerald-950' : 'text-slate-700'}`}>
                    {slot.label}
                  </span>
                  {isCollected ? (
                    <span className="font-medium text-emerald-700 block truncate max-w-[200px]">
                      {String(value)}
                    </span>
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">Not elicited yet</span>
                  )}
                </div>
              </div>

              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider shrink-0 ${
                  isCollected ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
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
