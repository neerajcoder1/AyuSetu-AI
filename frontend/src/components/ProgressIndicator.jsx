import React from 'react';
import { CheckCircle2 } from 'lucide-react';

/**
 * Horizontal step bar showing patient flow progress.
 * Steps: Body Map, Documents, Voice, Review, Submitted.
 * Completed steps show a checkmark, current step highlighted, upcoming muted.
 * Responsive: stacks vertically on narrow screens.
 */
const steps = [
  { key: 'BODY_MAP', label: 'Body' },
  { key: 'DOCUMENTS', label: 'Documents' },
  { key: 'VOICE', label: 'Voice' },
  { key: 'REVIEW', label: 'Review' },
  { key: 'SUBMITTED', label: 'Submitted' },
];

export default function ProgressIndicator({ currentStep }) {
  return (
    <div className="w-full overflow-x-auto mb-4">
      <ul className="flex flex-wrap justify-between items-center text-sm font-medium">
        {steps.map((step, idx) => {
          const currentIdx = steps.findIndex((s) => s.key === currentStep);
          const isCompleted = currentIdx > idx;
          const isCurrent = step.key === currentStep;
          return (
            <li
              key={step.key}
              className={`flex items-center ${isCompleted ? 'text-emerald-700' : isCurrent ? 'text-sky-600' : 'text-gray-400'} ${idx !== steps.length - 1 ? 'mr-2' : ''}`}
            >
              {isCompleted ? (
                <CheckCircle2 className="w-4 h-4 mr-1" />
              ) : (
                <span className="w-4 h-4 mr-1 border rounded-full" />
              )}
              <span>{step.label}</span>
              {idx < steps.length - 1 && (
                <span className="mx-2 w-4 h-px bg-gray-300 flex-1 hidden sm:inline-block" />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
