import React, { useState } from 'react';
import {
  Stethoscope,
  FileText,
  Sparkles,
  Upload,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Layers,
  CheckCircle2,
  UserCheck,
  Activity,
  Clock,
  Globe,
  AlertTriangle,
} from 'lucide-react';
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
  sessionDocuments = [],
  onDocumentProcessed: parentOnDocumentProcessed,
  activeSection = 'overview',
}) {
  const [summary, setSummary] = useState(null);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [isDocModalOpen, setIsDocModalOpen] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const [localDocumentEntities, setLocalDocumentEntities] = useState([]);
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
      setLocalDocumentEntities((prev) => [...prev, ...docRes.entities]);
    }
    setTimelineRefreshKey((prev) => prev + 1);
    if (parentOnDocumentProcessed) parentOnDocumentProcessed(docRes);
    if (onRefreshSessionState) onRefreshSessionState();
  };

  const handleSummaryUpdated = (updatedSummary) => {
    setSummary(updatedSummary);
    setTimelineRefreshKey((prev) => prev + 1);
  };

  const collectedInfo = dialogueState?.collected_info || {};
  const preferredLang = dialogueState?.preferred_language || 'hinglish';
  const slotsElicitedCount = Object.keys(collectedInfo).length;
  const totalSlotsCount = 12;

  // Group documents by uploader role
  const patientDocs = sessionDocuments.filter((d) => d.uploaderRole === 'patient' || d.confirmedByPatient);
  const physicianDocs = sessionDocuments.filter((d) => d.uploaderRole === 'physician');

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Section 1: Cockpit Header & Real Metric Bar */}
      <section id="section-overview" className="space-y-6 scroll-mt-20">
        {/* SaaS Header Hero Banner */}
        <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-teal-950 text-white rounded-2xl p-6 sm:p-7 shadow-xl flex flex-col lg:flex-row items-start lg:items-center justify-between gap-5 border border-slate-800">
          <div className="space-y-1.5 max-w-2xl">
            <div className="flex items-center space-x-2">
              <Stethoscope className="w-5 h-5 text-sky-400" />
              <span className="text-xs font-extrabold text-sky-400 uppercase tracking-wider">
                Physician Triage & Case-Taking Cockpit
              </span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
              Clinical Case-Taking & Diagnostic Intelligence
            </h2>
            <p className="text-slate-300 text-xs sm:text-sm leading-relaxed font-normal">
              Real-time clinical memory slots, safety triage alerts, document OCR findings, and evidence-grounded summary sign-off.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => setIsDocModalOpen(true)}
              className="flex items-center space-x-1.5 bg-slate-800/90 hover:bg-slate-700/90 text-slate-100 border border-slate-700/90 font-bold text-xs px-3.5 py-2.5 rounded-xl transition-all shadow-sm"
              title="Upload physician supporting document"
            >
              <Upload className="w-4 h-4 text-sky-400" />
              <span>Upload Supporting Document</span>
            </button>

            <button
              onClick={handleGenerateSummary}
              disabled={isGeneratingSummary || !sessionId}
              className="flex items-center space-x-1.5 bg-sky-600 hover:bg-sky-700 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-md transition-all disabled:opacity-50"
            >
              {isGeneratingSummary ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              <span>Generate AI Summary</span>
            </button>

            {summary && (
              <button
                onClick={() => setIsReviewModalOpen(true)}
                className="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl shadow-md transition-all"
              >
                <ShieldCheck className="w-4 h-4" />
                <span>Review Draft ({summary.status})</span>
              </button>
            )}
          </div>
        </div>

        {/* Dynamic Metric Bar (100% real state) */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="space-y-0.5">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">Session Identifier</span>
            <span className="font-mono text-slate-900 font-bold truncate block">{sessionId || 'No session active'}</span>
          </div>

          <div className="space-y-0.5">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">Intake Language</span>
            <span className="text-slate-900 font-bold capitalize block">{preferredLang}</span>
          </div>

          <div className="space-y-0.5">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">Clinical Slots Elicited</span>
            <span className="text-sky-700 font-bold block">{slotsElicitedCount} / {totalSlotsCount} Collected</span>
          </div>

          <div className="space-y-0.5">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">Safety Triage Status</span>
            <span className={`font-bold block ${redFlags.length > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
              {redFlags.length > 0 ? `${redFlags.length} Alert Intercept(s)` : 'Clear (No Red Flags)'}
            </span>
          </div>
        </div>
      </section>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols): Red Flags + Clinical Info + Timeline */}
        <div className="lg:col-span-8 space-y-6">
          {/* Section 2: Safety Triage & Red Flag Intercepts */}
          <section id="section-red-flags" className="scroll-mt-20">
            <RedFlagAlertPanel redFlags={redFlags} />
          </section>

          {/* Section 3: Clinical Information (12 slots) */}
          <section id="section-clinical-info" className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-4 scroll-mt-20">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-sky-50 text-sky-700 rounded-xl">
                  <FileText className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-sm sm:text-base">
                    Clinical Elicited Information
                  </h3>
                  <p className="text-xs text-slate-500">Extracted slot values & patient-reported history</p>
                </div>
              </div>
              <span className="text-xs font-bold text-sky-700 bg-sky-50 px-2.5 py-1 rounded-full border border-sky-200">
                {slotsElicitedCount} / {totalSlotsCount} Slots Collected
              </span>
            </div>

            {slotsElicitedCount === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs italic bg-slate-50/70 rounded-xl border border-slate-100">
                No clinical slot values collected in this session yet. Perform patient intake turns to populate memory.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {Object.entries(collectedInfo).map(([key, val]) => (
                  <div key={key} className="p-3 bg-slate-50/80 border border-slate-200/90 rounded-xl space-y-1">
                    <span className="font-bold text-sky-900 uppercase text-[10px] tracking-wider block">
                      {key.replace('_', ' ')}
                    </span>
                    <span className="text-slate-900 font-semibold block leading-relaxed">{String(val)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Section 4: Longitudinal Patient Timeline */}
          <section id="section-timeline" className="scroll-mt-20">
            <ClinicalTimelineWidget sessionId={sessionId} refreshTrigger={timelineRefreshKey} />
          </section>
        </div>

        {/* Right Column (4 cols): Patient Documents, Summary & Review */}
        <div className="lg:col-span-4 space-y-6">
          {/* Section 5: Patient Documents & OCR Extractions */}
          <section id="section-documents" className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-4 scroll-mt-20">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-sky-50 text-sky-700 rounded-xl">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-sm">Patient Documents & OCR</h3>
                  <p className="text-[11px] text-slate-500">Document AI extractions</p>
                </div>
              </div>
              <span className="text-[10px] bg-sky-100 text-sky-900 font-bold px-2.5 py-0.5 rounded-full">
                {sessionDocuments.length} File{sessionDocuments.length === 1 ? '' : 's'}
              </span>
            </div>

            {/* Patient Uploaded Documents */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center space-x-1">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Patient Documents</span>
                </span>
                <span className="text-[10px] text-slate-400 font-bold">{patientDocs.length} File(s)</span>
              </div>

              {patientDocs.length === 0 ? (
                <div className="text-center py-4 text-slate-400 text-xs italic bg-slate-50/70 rounded-xl border border-slate-100">
                  No patient documents uploaded for this session yet.
                </div>
              ) : (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {patientDocs.map((doc, idx) => (
                    <div key={idx} className="p-3 bg-emerald-50/60 border border-emerald-200/90 rounded-xl text-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900 flex items-center space-x-1">
                          <FileText className="w-3.5 h-3.5 text-emerald-600" />
                          <span>{doc.filename}</span>
                        </span>
                        <span className="text-[10px] bg-emerald-200 text-emerald-950 font-bold px-2 py-0.5 rounded">
                          Patient Uploaded
                        </span>
                      </div>

                      {doc.entities && doc.entities.length > 0 && (
                        <div className="space-y-1 pt-1 border-t border-emerald-200/80">
                          <span className="text-[10px] font-bold text-slate-600 uppercase block">
                            OCR Extracted Information:
                          </span>
                          <div className="space-y-1">
                            {doc.entities.map((ent, ei) => (
                              <div key={ei} className="p-1.5 bg-white border border-slate-200 rounded-lg flex items-center justify-between text-[11px]">
                                <span className="font-bold text-[9px] uppercase bg-sky-100 text-sky-900 px-1 py-0.5 rounded">
                                  {ent.entity_type}
                                </span>
                                <span className="font-medium text-slate-800 truncate ml-1">{ent.raw_text}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Physician Supporting Documents */}
            {physicianDocs.length > 0 && (
              <div className="pt-2 border-t border-slate-100 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Physician Supporting Documents
                  </span>
                  <span className="text-[10px] text-slate-400 font-bold">{physicianDocs.length} File(s)</span>
                </div>
                <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                  {physicianDocs.map((doc, idx) => (
                    <div key={idx} className="p-2.5 bg-purple-50/60 border border-purple-200/90 rounded-xl text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900">{doc.filename}</span>
                        <span className="text-[10px] bg-purple-200 text-purple-950 font-bold px-2 py-0.5 rounded">
                          Physician Uploaded
                        </span>
                      </div>
                      {doc.entities && doc.entities.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {doc.entities.map((e, ei) => (
                            <span key={ei} className="text-[9px] bg-white border border-slate-200 px-1.5 py-0.5 rounded text-slate-700">
                              <strong className="text-purple-800 uppercase">{e.entity_type}:</strong> {e.raw_text}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Section 6 & 7: AI Clinical Summary & Physician Review Sign-Off Card */}
          <section id="section-summary" className="scroll-mt-20">
            <div id="section-sign-off" className="bg-gradient-to-br from-slate-900 via-sky-950 to-teal-950 text-white rounded-2xl p-5 shadow-lg space-y-4 border border-slate-800 scroll-mt-20">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-sky-400" />
                <h3 className="font-bold text-sm">Physician Review & Sign-Off</h3>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-normal">
                Review AI clinical draft summary, verify grounding evidence, edit any slot, or approve final sign-off.
              </p>
              <button
                onClick={handleGenerateSummary}
                disabled={isGeneratingSummary || !sessionId}
                className="w-full py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-extrabold text-xs rounded-xl shadow transition-all disabled:opacity-50 flex items-center justify-center space-x-1.5"
              >
                {isGeneratingSummary ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4 text-sky-200" />
                )}
                <span>{summary ? 'View & Verify Draft Summary' : 'Generate AI Summary'}</span>
              </button>
            </div>
          </section>
        </div>
      </div>

      {/* Document Upload Modal for Physician */}
      <DocumentUploadModal
        sessionId={sessionId}
        isOpen={isDocModalOpen}
        onClose={() => setIsDocModalOpen(false)}
        onDocumentProcessed={handleDocumentProcessed}
        uploaderRole="physician"
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
