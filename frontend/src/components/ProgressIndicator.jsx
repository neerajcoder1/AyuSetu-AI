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
  const currentIdx = steps.findIndex((s) => s.key === currentStep);

  return (
    <div className="w-full overflow-x-auto mb-4">
      <ul className="flex items-center justify-between text-sm font-medium">
        {steps.map((step, idx) => {
          const isCompleted = currentIdx > idx;
          const isCurrent = step.key === currentStep;
          return (
            <React.Fragment key={step.key}>
              <li className="flex items-center">
                {isCompleted ? (
                  <span className="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center">
                    <CheckCircle2 className="w-4 h-4 text-white" />
                  </span>
                ) : isCurrent ? (
                  <span className="w-6 h-6 rounded-full bg-sky-600 flex items-center justify-center">
                    <span className="w-2 h-2 rounded-full bg-white" />
                  </span>
                ) : (
                  <span className="w-6 h-6 rounded-full border-2 border-gray-300" />
                )}
                <span
                  className={`ml-2 hidden sm:inline ${
                    isCompleted ? 'text-emerald-700' : isCurrent ? 'text-sky-600 font-semibold' : 'text-gray-400'
                  }`}
                >
                  {step.label}
                </span>
              </li>
              {idx < steps.length - 1 && (
                <li className="flex-1 mx-2">
                  <div
                    className={`h-0.5 w-full ${
                      currentIdx > idx ? 'bg-emerald-500' : 'bg-gray-200'
                    }`}
                  />
                </li>
              )}
            </React.Fragment>
          );
        })}
      </ul>
    </div>
  );
}
