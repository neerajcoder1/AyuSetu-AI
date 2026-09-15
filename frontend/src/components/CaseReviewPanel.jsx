// frontend/src/components/CaseReviewPanel.jsx
import React, { useState, useEffect } from 'react';
import {
  Heart, MapPin, Clock, Calendar, Gauge, Stethoscope,
  Pill, AlertTriangle, Users, Activity, FileText,
  Loader2, CheckCircle2, AlertCircle, MessageSquare,
  ChevronLeft, X, ClipboardList, ShieldCheck,
} from 'lucide-react';
import { api } from '../services/api';
import SummaryReviewModal from './SummaryReviewModal';

// Clinical slot config matching ReviewStep.jsx
const SLOT_CONFIG = {
  chief_complaint: { label: 'Chief Complaint', icon: Heart, color: 'text-red-600 bg-red-50 border-red-200' },
  location: { label: 'Location', icon: MapPin, color: 'text-blue-600 bg-blue-50 border-blue-200' },
  onset: { label: 'Onset', icon: Calendar, color: 'text-purple-600 bg-purple-50 border-purple-200' },
  duration: { label: 'Duration', icon: Clock, color: 'text-indigo-600 bg-indigo-50 border-indigo-200' },
  severity: { label: 'Severity', icon: Gauge, color: 'text-orange-600 bg-orange-50 border-orange-200' },
  associated_symptoms: { label: 'Associated Symptoms', icon: Stethoscope, color: 'text-teal-600 bg-teal-50 border-teal-200' },
  aggravating_relieving: { label: 'Aggravating / Relieving Factors', icon: Activity, color: 'text-amber-600 bg-amber-50 border-amber-200' },
  past_medical_history: { label: 'Past Medical History', icon: FileText, color: 'text-slate-600 bg-slate-50 border-slate-200' },
  medications: { label: 'Current Medications', icon: Pill, color: 'text-green-600 bg-green-50 border-green-200' },
  allergies: { label: 'Allergies', icon: AlertTriangle, color: 'text-rose-600 bg-rose-50 border-rose-200' },
  family_history: { label: 'Family History', icon: Users, color: 'text-cyan-600 bg-cyan-50 border-cyan-200' },
  lifestyle: { label: 'Lifestyle', icon: Activity, color: 'text-emerald-600 bg-emerald-50 border-emerald-200' },
};

const STATUS_CONFIG = {
  SUBMITTED: { label: 'New', className: 'bg-blue-100 text-blue-800 border-blue-300' },
  UNDER_REVIEW: { label: 'Under Review', className: 'bg-amber-100 text-amber-800 border-amber-300' },
  REVIEWED: { label: 'Reviewed', className: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, className: 'bg-gray-100 text-gray-700 border-gray-300' };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

function SectionHeader({ icon: Icon, title }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-5 h-5 text-sky-600" />
      <h3 className="text-base font-semibold text-gray-800">{title}</h3>
    </div>
  );
}

/**
 * CaseReviewPanel — Full physician case review view.
 * Opened when the physician clicks "Review Case" in the case queue.
 */
export default function CaseReviewPanel({ caseId, onClose, onCaseUpdated }) {
  const [caseData, setCaseData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isStartingReview, setIsStartingReview] = useState(false);
  const [isSummaryModalOpen, setIsSummaryModalOpen] = useState(false);
  const [localSummary, setLocalSummary] = useState(null);

  useEffect(() => {
    loadCase();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const loadCase = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getCaseDetail(caseId);
      setCaseData(data);
      if (data.summary) setLocalSummary(data.summary);
    } catch (err) {
      setError(err.message || 'Failed to load case.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartReview = async () => {
    setIsStartingReview(true);
    try {
      await api.startCaseReview(caseId);
      setCaseData((prev) => ({ ...prev, status: 'UNDER_REVIEW' }));
      if (onCaseUpdated) onCaseUpdated();
    } catch (err) {
      setError(err.message || 'Failed to start review.');
    } finally {
      setIsStartingReview(false);
    }
  };

  const handleSummaryUpdated = (updatedSummary) => {
    setLocalSummary(updatedSummary);
    setCaseData((prev) => ({ ...prev, summary: updatedSummary }));
    // If summary status is FINAL, the case is REVIEWED
    if (updatedSummary?.status === 'final') {
      setCaseData((prev) => ({ ...prev, status: 'REVIEWED' }));
      if (onCaseUpdated) onCaseUpdated();
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-sky-600" />
        <span className="ml-3 text-gray-600">Loading case…</span>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <AlertCircle className="w-10 h-10 text-red-500" />
        <p className="text-red-700 font-medium">{error || 'Case not found.'}</p>
        <button onClick={onClose} className="text-sky-600 underline">Go back</button>
      </div>
    );
  }

  const collectedInfo = caseData.collected_info || {};
  const redFlags = caseData.red_flags || [];
  const transcript = caseData.transcript || [];
  const documents = caseData.documents || [];
  const summary = localSummary || caseData.summary;
  const status = caseData.status;
  const isReviewed = status === 'REVIEWED';
  const isUnderReview = status === 'UNDER_REVIEW';
  const isSubmitted = status === 'SUBMITTED';

  const submittedAt = caseData.submitted_at ? new Date(caseData.submitted_at).toLocaleString() : '—';
  const reviewedAt = caseData.reviewed_at ? new Date(caseData.reviewed_at).toLocaleString() : null;

  return (
    <div className="space-y-6">
      {/* Case Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <button
            onClick={onClose}
            className="mt-1 p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-xl font-bold text-gray-900 font-mono">{caseData.case_id}</h2>
              <StatusBadge status={status} />
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Submitted: {submittedAt}
              {caseData.reviewed_by && (
                <span className="ml-3">Reviewed by: <span className="font-medium">{caseData.reviewed_by}</span></span>
              )}
              {reviewedAt && <span className="ml-3">at {reviewedAt}</span>}
            </p>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-300 rounded-lg text-red-800 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Clinical Safety Notice */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-900">
        <span className="font-semibold">Clinical Reminder:</span> This history was collected by an AI assistant. All information requires physician verification before clinical use. AI-generated summaries are preliminary and non-diagnostic.
      </div>

      {/* Clinical History */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
          <SectionHeader icon={ClipboardList} title="Clinical History" />
        </div>
        <div className="divide-y divide-gray-100">
          {Object.entries(SLOT_CONFIG).map(([slotKey, config]) => {
            const IconComponent = config.icon;
            const value = collectedInfo[slotKey];
            return (
              <div key={slotKey} className="flex items-start gap-3 px-4 py-3">
                <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center border ${config.color}`}>
                  <IconComponent className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{config.label}</p>
                  {value ? (
                    <p className="text-sm text-gray-900 mt-0.5">{value}</p>
                  ) : (
                    <p className="text-sm text-gray-400 italic mt-0.5">Not elicited</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Red Flags */}
      {redFlags.length > 0 && (
        <div className="border-2 border-rose-300 rounded-lg overflow-hidden bg-rose-50">
          <div className="px-4 py-3 border-b border-rose-200 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-rose-600" />
            <h3 className="font-semibold text-rose-800">Red Flag Alerts ({redFlags.length})</h3>
            <span className="ml-auto text-xs bg-rose-600 text-white px-2 py-0.5 rounded-full font-medium">
              Physician Verification Required
            </span>
          </div>
          <div className="divide-y divide-rose-200">
            {redFlags.map((rf, idx) => (
              <div key={idx} className="px-4 py-3">
                <p className="font-medium text-rose-800 text-sm">{rf.title || rf.category || 'Red Flag'}</p>
                {rf.trigger_text && (
                  <p className="text-xs text-rose-700 mt-1 font-mono bg-rose-100 rounded px-2 py-1">
                    "{rf.trigger_text}"
                  </p>
                )}
                <p className="text-xs text-rose-500 mt-1">Category: {rf.category || '—'} · Rule ID: {rf.rule_id || 'RF-DETECTED'}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Uploaded Documents */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
          <SectionHeader icon={FileText} title="Uploaded Documents" />
        </div>
        <div className="px-4 py-3">
          {documents.length > 0 ? (
            <ul className="space-y-2">
              {documents.map((doc, idx) => (
                <li key={idx} className="flex items-center gap-2 text-sm text-gray-700">
                  <FileText className="w-4 h-4 text-gray-400" />
                  <span>{doc.filename || doc.raw_text || `Document ${idx + 1}`}</span>
                  {doc.entity_type && (
                    <span className="ml-auto text-xs bg-sky-100 text-sky-800 px-2 py-0.5 rounded">{doc.entity_type}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 italic">No documents uploaded.</p>
          )}
        </div>
      </div>

      {/* AI-Generated Clinical Summary */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <SectionHeader icon={ShieldCheck} title="AI-Generated Clinical Summary" />
          <span className="text-xs bg-amber-100 text-amber-800 border border-amber-300 px-2 py-0.5 rounded">
            {summary?.status === 'final' ? 'FINAL — Physician Signed' : 'PRELIMINARY — Awaiting Physician Review'}
          </span>
        </div>
        <div className="px-4 py-4 space-y-3">
          {summary ? (
            <>
              {summary.chief_complaint && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Chief Complaint</p>
                  <p className="text-sm text-gray-900 mt-0.5">{summary.chief_complaint}</p>
                </div>
              )}
              {summary.hpi_narrative && summary.hpi_narrative.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">HPI Narrative</p>
                  <p className="text-sm text-gray-900 mt-0.5 leading-relaxed">
                    {summary.hpi_narrative.map((c) => c.text || c).join(' ')}
                  </p>
                </div>
              )}
              {summary.structured_history && Object.keys(summary.structured_history).length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                  {Object.entries(summary.structured_history).map(([key, field]) => (
                    <div key={key} className="bg-slate-50 rounded p-2 border border-slate-100">
                      <p className="text-xs font-medium text-gray-500 uppercase">{field.label || key.replace(/_/g, ' ')}</p>
                      <p className="text-sm text-gray-800 mt-0.5">
                        {field.value || field.display_value || <span className="italic text-gray-400">Not elicited</span>}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              {summary.signed_by && (
                <div className="mt-2 pt-2 border-t border-gray-200 text-xs text-gray-500">
                  Signed by <span className="font-medium">{summary.signed_by}</span>
                  {summary.signed_at && <> · {new Date(summary.signed_at).toLocaleString()}</>}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-400 italic">No summary generated yet.</p>
          )}
        </div>
      </div>

      {/* Conversation Transcript */}
      {transcript.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
            <SectionHeader icon={MessageSquare} title="Conversation Transcript" />
          </div>
          <div className="px-4 py-3 max-h-64 overflow-y-auto space-y-2">
            {transcript.map((turn, idx) => (
              <div key={idx} className={`flex gap-2 ${turn.speaker === 'system' ? 'justify-start' : 'justify-end'}`}>
                <div
                  className={`max-w-xs rounded-lg px-3 py-2 text-sm ${
                    turn.speaker === 'system'
                      ? 'bg-sky-50 text-sky-900 border border-sky-100'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  <p className="text-xs font-medium mb-0.5 opacity-70">
                    {turn.speaker === 'system' ? 'AyuSetu AI' : 'Patient'}
                  </p>
                  {turn.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Physician Actions */}
      <div className="border border-gray-200 rounded-lg p-4 bg-white space-y-4">
        <SectionHeader icon={ShieldCheck} title="Physician Review" />

        {isReviewed ? (
          <div className="flex items-center gap-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            <div>
              <p className="font-medium text-emerald-800">Case Reviewed</p>
              <p className="text-xs text-emerald-700">
                Reviewed by {caseData.reviewed_by || '—'}{reviewedAt ? ` · ${reviewedAt}` : ''}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {isSubmitted && (
              <button
                onClick={handleStartReview}
                disabled={isStartingReview}
                className={`px-4 py-2.5 rounded-lg flex items-center gap-2 font-medium text-sm transition-colors ${
                  isStartingReview
                    ? 'bg-sky-400 text-white cursor-not-allowed'
                    : 'bg-sky-600 hover:bg-sky-700 text-white'
                }`}
              >
                {isStartingReview ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Starting…</>
                ) : (
                  <><ClipboardList className="w-4 h-4" /> Start Review</>
                )}
              </button>
            )}
            {(isUnderReview || isSubmitted) && (
              <button
                onClick={() => setIsSummaryModalOpen(true)}
                className="px-4 py-2.5 bg-white border-2 border-sky-600 text-sky-700 hover:bg-sky-50 rounded-lg flex items-center gap-2 font-medium text-sm transition-colors"
              >
                <ShieldCheck className="w-4 h-4" />
                {summary?.status === 'final' ? 'View Signed Summary' : 'Review & Sign Off Summary'}
              </button>
            )}
            {!isUnderReview && !isSubmitted && (
              <p className="text-sm text-gray-500 italic">Start the review to access the summary sign-off.</p>
            )}
          </div>
        )}
        <p className="text-xs text-gray-400">
          The physician is the final reviewer. AI summaries are assistive only and do not constitute a clinical diagnosis or approved treatment plan.
        </p>
      </div>

      {/* Summary Review Modal — reuses existing component */}
      {isSummaryModalOpen && (
        <SummaryReviewModal
          sessionId={caseData.session_id}
          summary={summary}
          isOpen={isSummaryModalOpen}
          onClose={() => setIsSummaryModalOpen(false)}
          onSummaryUpdated={handleSummaryUpdated}
        />
      )}
    </div>
  );
}
