// frontend/src/components/SubmittedStep.jsx
import React from 'react';
import { CheckCircle2 } from 'lucide-react';

/**
 * Simple success UI after submission.
 */
export default function SubmittedStep() {
  return (
    <div className="flex flex-col items-center justify-center py-12 space-y-4">
      <CheckCircle2 className="w-12 h-12 text-emerald-600" />
      <h2 className="text-xl font-semibold text-emerald-700">Your information has been submitted</h2>
      <p className="text-gray-600">A physician will review your case shortly.</p>
    </div>
  );
}
