import React, { useState } from 'react';
import { Stethoscope, FileText, Sparkles, Upload, ShieldCheck, AlertCircle, RefreshCw, Layers } from 'lucide-react';
import RedFlagAlertPanel from '../components/RedFlagAlertPanel';
import ClinicalTimelineWidget from '../components/ClinicalTimelineWidget';
import DocumentUploadModal from '../components/DocumentUploadModal';
import SummaryReviewModal from '../components/SummaryReviewModal';
import { api } from '../services/api';

export default function DoctorDashboardScreen({
  sessionId,
  dialogueState,
  redFlags = [],
  onRefreshSessionState,
}) {
  const [summary, setSummary] = useState(null);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [isDocModalOpen, setIsDocModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const [documentEntities, setDocumentEntities] = useState([]);
  const [error, setError] = useState(null);

  // Generate Summary
  const handleGenerateSummary = async () => {
    if (!sessionId) {
      setError('No active session found.');
      return;
    }
    setIsGeneratingSummary(true);
    setError(null);
    try {
      const res = await api.generateSummary(sessionId);
      setSummary(res);
      setIsReviewModalOpen(true);
    } catch (err) {
      console.error('Summary generation error:', err);
      setError(err.message || 'Failed to generate summary');
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleDocumentProcessed = (docRes) => {
    if (docRes && docRes.entities) {
      setDocumentEntities((prev) => [...prev, ...docRes.entities]);
    }
    setTimelineRefreshKey((prev) => prev + 1);
    if (onRefreshSessionState) onRefreshSessionState();
  };

  const handleSummaryUpdated = (updatedSummary) => {
    setSummary(updatedSummary);
    setTimelineRefreshKey((prev) => prev + 1);
  };

  const collectedInfo = dialogueState?.collected_info || {};

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Cockpit Title Header */}
      <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <Stethoscope className="w-5 h-5 text-sky-400" />
            <span className="text-xs font-bold text-sky-400 uppercase tracking-wider">
              Physician Clinical Cockpit
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight">
            Doctor Review & Diagnostic Intelligence
          </h2>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            Real-time session memory, red-flag safety intercepts, document OCR, and evidence-grounded summary sign-off.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setIsDocModalOpen(true)}
            className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-semibold text-xs px-3.5 py-2.5 rounded-xl transition-all"
          >
            <Upload className="w-4 h-4 text-sky-400" />
            <span>Upload Document</span>
          </button>

          <button
            onClick={handleGenerateSummary}
            disabled={isGeneratingSummary || !sessionId}
            className="flex items-center space-x-1.5 bg-gradient-to-r from-medical-600 to-sky-500 hover:from-medical-700 hover:to-sky-600 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-md transition-all disabled:opacity-50"
          >
            {isGeneratingSummary ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            <span>Generate Summary</span>
          </button>

          {summary && (
            <button
              onClick={() => setIsReviewModalOpen(true)}
              className="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-md transition-all"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Review Draft ({summary.status})</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 8 Cols: Red Flags + Live Encounter Summary + Timeline */}
        <div className="lg:col-span-8 space-y-6">
          {/* Red Flag Alert Panel */}
          <RedFlagAlertPanel redFlags={redFlags} />

          {/* Current Session Summary Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-medical-600" />
                <h3 className="font-semibold text-slate-900 text-sm sm:text-base">
                  Session Elicited Information
                </h3>
              </div>
              <span className="text-xs text-slate-500">
                {Object.keys(collectedInfo).length} Slots Elicited
              </span>
            </div>

            {Object.keys(collectedInfo).length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs italic bg-slate-50 rounded-xl">
                No clinical slot values collected in this session yet. Perform patient intake turns to populate memory.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {Object.entries(collectedInfo).map(([key, val]) => (
                  <div key={key} className="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="font-bold text-slate-800 uppercase text-[10px] tracking-wider block mb-0.5">
                      {key.replace('_', ' ')}
                    </span>
                    <span className="text-slate-900 font-medium">{String(val)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Longitudinal Patient Timeline Widget */}
          <ClinicalTimelineWidget sessionId={sessionId} refreshTrigger={timelineRefreshKey} />
        </div>

        {/* Right 4 Cols: Document Entities & Review Summary Preview */}
        <div className="lg:col-span-4 space-y-6">
          {/* Extracted Document Entities */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <Layers className="w-4 h-4 text-sky-600" />
                <h3 className="font-semibold text-slate-900 text-sm">Document AI Entities</h3>
              </div>
              <span className="text-[10px] bg-sky-100 text-sky-800 font-bold px-2 py-0.5 rounded-full">
                {documentEntities.length} Total
              </span>
            </div>

            {documentEntities.length === 0 ? (
              <div className="text-center py-6 text-slate-400 text-xs italic bg-slate-50 rounded-xl">
                No documents uploaded for OCR processing in this session.
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {documentEntities.map((ent, idx) => (
                  <div key={idx} className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[10px] uppercase bg-sky-100 text-sky-800 px-1.5 py-0.5 rounded">
                        {ent.entity_type}
                      </span>
                      <span className="text-[10px] text-slate-400">P.{ent.page_no}</span>
                    </div>
                    <p className="font-medium text-slate-800">{ent.raw_text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Physician Review Card */}
          <div className="bg-gradient-to-br from-slate-900 to-medical-950 text-white rounded-2xl p-5 shadow-lg space-y-4">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h3 className="font-bold text-sm">Physician Sign-Off Workflow</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Once patient intake is complete, generate the evidence-grounded draft summary for sign-off.
            </p>
            <button
              onClick={handleGenerateSummary}
              disabled={isGeneratingSummary || !sessionId}
              className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-600 text-white font-bold text-xs rounded-xl shadow transition-all disabled:opacity-50"
            >
              {summary ? 'View & Edit Draft Summary' : 'Generate Draft Summary'}
            </button>
          </div>
        </div>
      </div>

      {/* Document Upload Modal */}
      <DocumentUploadModal
        sessionId={sessionId}
        isOpen={isDocModalOpen}
        onClose={() => setIsDocModalOpen(false)}
        onDocumentProcessed={handleDocumentProcessed}
      />

      {/* Summary Review Modal */}
      <SummaryReviewModal
        sessionId={sessionId}
        summary={summary}
        isOpen={isReviewModalOpen}
        onClose={() => setIsReviewModalOpen(false)}
        onSummaryUpdated={handleSummaryUpdated}
      />
    </div>
  );
}
