import React, { useState } from 'react';
import { CheckCircle, Edit3, XCircle, ShieldCheck, AlertCircle, RefreshCw, X } from 'lucide-react';
import { api } from '../services/api';

export default function SummaryReviewModal({
  sessionId,
  summary,
  isOpen,
  onClose,
  onSummaryUpdated,
}) {
  const [physicianId, setPhysicianId] = useState('DR-9942');
  const [editingSlot, setEditingSlot] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [editReason, setEditReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('wrong');
  const [rejectDetail, setRejectDetail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen || !summary) return null;

  const status = summary.status || 'PRELIMINARY';
  const isFinal = status === 'FINAL';

  // Handle Sign-off
  const handleSignOff = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const updated = await api.signOffSummary(sessionId, physicianId);
      if (onSummaryUpdated) onSummaryUpdated(updated);
    } catch (err) {
      console.error('Sign-off error:', err);
      setError(err.message || 'Sign-off failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Edit Field
  const handleSaveEdit = async () => {
    if (!editingSlot || !editReason) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.editSummary(sessionId, editingSlot, editValue, editReason, physicianId);
      setEditingSlot(null);
      setEditValue('');
      setEditReason('');
      if (onSummaryUpdated) onSummaryUpdated(res.summary);
    } catch (err) {
      console.error('Edit error:', err);
      setError(err.message || 'Edit failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Reject
  const handleConfirmReject = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await api.rejectSummary(sessionId, rejectReason, rejectDetail, physicianId);
      setIsRejecting(false);
      // Refresh summary from parent
      const freshSummary = await api.generateSummary(sessionId);
      if (onSummaryUpdated) onSummaryUpdated(freshSummary);
    } catch (err) {
      console.error('Reject error:', err);
      setError(err.message || 'Rejection failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-modal w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        
        {/* Modal Header */}
        <div className="p-4 sm:p-5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-teal-50 text-teal-700 rounded-xl border border-teal-200">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-extrabold text-slate-900 text-base sm:text-lg">AI Clinical Summary Verification</h3>
                <span
                  className={`text-xs font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                    isFinal
                      ? 'bg-emerald-100 text-emerald-900 border border-emerald-300'
                      : 'bg-amber-100 text-amber-900 border border-amber-300'
                  }`}
                >
                  {status} DRAFT
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">Encounter ID: {sessionId} — Requires Physician Approval</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-5 text-xs sm:text-sm flex-1">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Preliminary warning notice */}
          {!isFinal && (
            <div className="p-3.5 bg-amber-50 border border-amber-200 text-amber-950 rounded-xl text-xs flex items-center space-x-2.5">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span className="font-medium">
                <strong>Clinical Verification Mandate:</strong> The AI-generated summary is preliminary and non-final. Physician must review, edit any discrepancy, and explicitly sign off before recording into permanent record.
              </span>
            </div>
          )}

          {/* Signed-off Status Badge */}
          {isFinal && summary.physician_sign_off && (
            <div className="p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-950 rounded-xl text-xs flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 text-emerald-600" />
                <span className="font-medium">
                  Signed off by Physician <strong>{summary.physician_sign_off.physician_id}</strong> on{' '}
                  {new Date(summary.physician_sign_off.timestamp).toLocaleString()}
                </span>
              </div>
              <span className="text-[10px] bg-emerald-200 font-extrabold px-2 py-0.5 rounded text-emerald-950">
                FINAL CLINICAL RECORD
              </span>
            </div>
          )}

          {/* HPI Narrative */}
          <div className="bg-slate-50/80 border border-slate-200 rounded-2xl p-4 space-y-2">
            <h4 className="font-extrabold text-slate-900 text-xs uppercase tracking-wider text-teal-800">
              History of Present Illness (HPI Narrative)
            </h4>
            <p className="text-slate-800 leading-relaxed font-sans text-sm font-medium">
              {summary.hpi || 'No HPI narrative generated.'}
            </p>
          </div>

          {/* Structured Collapsible Fields */}
          <div className="space-y-3">
            <h4 className="font-extrabold text-slate-900 text-xs uppercase tracking-wider text-teal-800">
              Structured Clinical Sections & Evidence
            </h4>

            {summary.structured_history &&
              Object.entries(summary.structured_history).map(([slotKey, field]) => (
                <div
                  key={slotKey}
                  className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-start justify-between hover:border-slate-300 transition-colors shadow-sm"
                >
                  <div className="space-y-1 min-w-0 pr-3">
                    <div className="flex items-center space-x-2">
                      <span className="font-extrabold text-slate-900">{field.label || slotKey}</span>
                      {field.elicited === false && (
                        <span className="text-[10px] bg-slate-100 text-slate-500 font-bold px-2 py-0.5 rounded">
                          Not Elicited
                        </span>
                      )}
                    </div>
                    <p className="text-slate-700 text-xs font-medium">{field.rendered || field.value || 'Not reported'}</p>
                    {field.grounding_sources && field.grounding_sources.length > 0 && (
                      <div className="text-[10px] text-slate-400 font-mono">
                        Source: {field.grounding_sources.join(', ')}
                      </div>
                    )}
                  </div>

                  {!isFinal && (
                    <button
                      onClick={() => {
                        setEditingSlot(slotKey);
                        setEditValue(field.rendered || '');
                      }}
                      className="p-2 text-slate-500 hover:text-teal-700 hover:bg-slate-100 rounded-lg transition-colors shrink-0"
                      title="Edit this field"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
          </div>

          {/* Inline Edit Form */}
          {editingSlot && (
            <div className="p-4 bg-teal-50/80 border border-teal-300 rounded-2xl space-y-3 animate-in fade-in duration-150">
              <h5 className="font-extrabold text-teal-950 text-xs uppercase">Editing Field: {editingSlot}</h5>
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">New Field Value</label>
                <input
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-teal-500 focus:outline-none font-medium"
                />
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">Audit Log Reason</label>
                <input
                  type="text"
                  placeholder="Reason for physician override..."
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-teal-500 focus:outline-none font-medium"
                />
              </div>
              <div className="flex justify-end space-x-2 pt-1">
                <button
                  onClick={() => setEditingSlot(null)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveEdit}
                  disabled={isLoading || !editReason}
                  className="px-4 py-1.5 bg-medical-700 text-white font-bold text-xs rounded-xl hover:bg-medical-800 disabled:opacity-50 shadow-sm"
                >
                  Save Override
                </button>
              </div>
            </div>
          )}

          {/* Rejection Form */}
          {isRejecting && (
            <div className="p-4 bg-rose-50 border border-rose-300 rounded-2xl space-y-3 animate-in fade-in duration-150">
              <h5 className="font-extrabold text-rose-950 text-xs uppercase">Reject Summary Draft</h5>
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">Rejection Category</label>
                <select
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-rose-500 focus:outline-none font-bold"
                >
                  <option value="wrong">Wrong / Factually Inaccurate</option>
                  <option value="incomplete">Incomplete / Missing Critical Info</option>
                  <option value="unsafe">Unsafe / Clinical Risk</option>
                  <option value="irrelevant">Irrelevant / Ungrounded Narrative</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">Detail Explanation</label>
                <textarea
                  rows={2}
                  placeholder="Explain why this summary draft was rejected..."
                  value={rejectDetail}
                  onChange={(e) => setRejectDetail(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-rose-500 focus:outline-none font-medium"
                />
              </div>
              <div className="flex justify-end space-x-2 pt-1">
                <button
                  onClick={() => setIsRejecting(false)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmReject}
                  disabled={isLoading}
                  className="px-4 py-1.5 bg-rose-600 text-white font-bold text-xs rounded-xl hover:bg-rose-700 disabled:opacity-50 shadow-sm"
                >
                  Confirm Rejection
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Controls */}
        <div className="p-4 border-t border-slate-200 bg-slate-50/90 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold text-slate-600">Physician ID:</span>
            <input
              type="text"
              value={physicianId}
              onChange={(e) => setPhysicianId(e.target.value)}
              className="px-2.5 py-1 text-xs border border-slate-300 rounded-lg font-mono w-28 focus:outline-none font-bold text-slate-900"
            />
          </div>

          <div className="flex items-center space-x-2">
            {!isFinal && (
              <>
                <button
                  onClick={() => setIsRejecting(true)}
                  disabled={isLoading || isRejecting}
                  className="flex items-center space-x-1 px-3.5 py-2 bg-rose-100 text-rose-900 hover:bg-rose-200 font-bold text-xs rounded-xl transition-all disabled:opacity-50"
                >
                  <XCircle className="w-4 h-4" />
                  <span>Reject Draft</span>
                </button>

                <button
                  onClick={handleSignOff}
                  disabled={isLoading}
                  className="flex items-center space-x-1.5 px-4.5 py-2 bg-medical-700 hover:bg-medical-800 text-white font-bold text-xs rounded-xl shadow-sm transition-all disabled:opacity-50"
                >
                  {isLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle className="w-4 h-4" />
                  )}
                  <span>Sign-Off & Approve Record</span>
                </button>
              </>
            )}

            {isFinal && (
              <button
                onClick={onClose}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-950 text-white font-bold text-xs rounded-xl transition-all"
              >
                Close Record
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
