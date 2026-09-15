// frontend/src/components/SubmittedStep.jsx
import React from 'react';
import { CheckCircle2, Clock, Shield, FileCheck } from 'lucide-react';

/**
 * Professional success confirmation after patient submits their case.
 * Shows case ID, submission time, and current status.
 */
export default function SubmittedStep({ submissionData }) {
  const caseId = submissionData?.case_id || '—';
  const submittedAt = submissionData?.submitted_at;
  const slotsCount = submissionData?.collected_slots_count;

  let formattedTime = '';
  if (submittedAt) {
    try {
      formattedTime = new Date(submittedAt).toLocaleString();
    } catch {
      formattedTime = submittedAt;
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 space-y-6 max-w-md mx-auto">
      {/* Success Icon */}
      <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
        <CheckCircle2 className="w-10 h-10 text-emerald-600" />
      </div>

      {/* Title */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-semibold text-emerald-700">Case Submitted Successfully</h2>
        <p className="text-gray-600">
          Your medical history has been submitted for physician review.
        </p>
      </div>

      {/* Status Card */}
      <div className="w-full bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
        {/* Case ID */}
        <div className="flex items-center gap-3 px-4 py-3">
          <FileCheck className="w-5 h-5 text-gray-400" />
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Case ID</p>
            <p className="text-sm font-mono font-medium text-gray-900">{caseId}</p>
          </div>
        </div>

        {/* Status */}
        <div className="flex items-center gap-3 px-4 py-3">
          <Clock className="w-5 h-5 text-amber-500" />
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Status</p>
            <p className="text-sm font-medium text-amber-700">Awaiting Physician Review</p>
          </div>
        </div>

        {/* Submitted At */}
        {formattedTime && (
          <div className="flex items-center gap-3 px-4 py-3">
            <Shield className="w-5 h-5 text-gray-400" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Submitted At</p>
              <p className="text-sm text-gray-700">{formattedTime}</p>
            </div>
          </div>
        )}

        {/* Fields Collected */}
        {slotsCount != null && (
          <div className="flex items-center gap-3 px-4 py-3">
            <FileCheck className="w-5 h-5 text-gray-400" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide">Clinical Fields Collected</p>
              <p className="text-sm text-gray-700">{slotsCount} of 12</p>
            </div>
          </div>
        )}
      </div>

      {/* Note */}
      <p className="text-xs text-gray-400 text-center">
        This is a prototype. Case data is stored in-memory for this session only.
      </p>
    </div>
  );
}
