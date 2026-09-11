import React, { useState } from 'react';
import { FileText, Upload, CheckCircle2, AlertCircle, RefreshCw, X, FileCheck, ShieldCheck } from 'lucide-react';
import { api } from '../services/api';

export default function DocumentUploadModal({
  sessionId,
  isOpen,
  onClose,
  onDocumentProcessed,
  uploaderRole = 'patient',
}) {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setUploadResult(null);
      setIsConfirmed(false);
    }
  };

  const handleUpload = async () => {
    if (!file || !sessionId) return;

    setIsUploading(true);
    setError(null);
    try {
      const res = await api.uploadDocument(sessionId, file);
      setUploadResult(res);
      // Auto-confirm for physician role, wait for explicit click for patient role
      if (uploaderRole === 'physician') {
        setIsConfirmed(true);
        if (onDocumentProcessed) {
          onDocumentProcessed({
            ...res,
            uploaderRole: 'physician',
            uploadedAt: new Date().toISOString(),
            confirmedByPatient: false,
          });
        }
      }
    } catch (err) {
      console.error('Failed to upload document:', err);
      setError(err.message || 'Failed to process document through Document AI OCR.');
    } finally {
      setIsUploading(false);
    }
  };

  const handlePatientConfirm = () => {
    setIsConfirmed(true);
    if (onDocumentProcessed && uploadResult) {
      onDocumentProcessed({
        ...uploadResult,
        uploaderRole: 'patient',
        uploadedAt: new Date().toISOString(),
        confirmedByPatient: true,
      });
    }
  };

  const handleReset = () => {
    setFile(null);
    setUploadResult(null);
    setIsConfirmed(false);
    setError(null);
  };

  const isPatient = uploaderRole === 'patient';
  const modalTitle = isPatient ? 'Upload Medical Document' : 'Upload Supporting Document';
  const modalSubtitle = isPatient
    ? 'OCR Scanning & Patient Medical Information Extraction'
    : 'Physician Supporting Document Attachment';

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-sky-100 text-sky-700 rounded-xl">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm sm:text-base">{modalTitle}</h3>
              <p className="text-xs text-slate-500">{modalSubtitle}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {/* Explanation Banner */}
          <div className="p-3 bg-sky-50 border border-sky-200 text-sky-900 rounded-xl text-xs space-y-1">
            <p className="font-semibold">
              {isPatient
                ? '📄 Upload lab reports, prescriptions, or clinical documents.'
                : '📋 Upload supplementary clinical notes or lab references.'}
            </p>
            <p className="text-[11px] text-sky-700">
              Automated OCR will scan the document and extract structured clinical findings for physician review.
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Upload Dropzone */}
          {!uploadResult && (
            <div className="border-2 border-dashed border-slate-300 hover:border-medical-500 rounded-2xl p-6 text-center bg-slate-50/50 transition-colors">
              <input
                type="file"
                id="doc-upload"
                onChange={handleFileChange}
                accept=".txt,.pdf,.png,.jpg,.jpeg"
                className="hidden"
              />
              <label htmlFor="doc-upload" className="cursor-pointer flex flex-col items-center">
                <Upload className="w-10 h-10 text-slate-400 mb-2" />
                <span className="font-semibold text-slate-800 text-xs sm:text-sm">
                  {file ? file.name : 'Choose lab report or medical document'}
                </span>
                <span className="text-[11px] text-slate-400 mt-1">
                  Supports TXT, PDF, PNG, JPG (Automated OCR Parser)
                </span>
              </label>
            </div>
          )}

          {/* File Selected Action */}
          {file && !uploadResult && (
            <div className="flex items-center justify-between bg-sky-50 border border-sky-200 rounded-xl p-3 text-xs">
              <div className="flex items-center space-x-2 text-sky-900 min-w-0">
                <FileCheck className="w-4 h-4 text-sky-600 shrink-0" />
                <span className="font-semibold truncate">{file.name}</span>
                <span className="text-[10px] text-sky-600">
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              </div>
              <button
                onClick={handleUpload}
                disabled={isUploading}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-medical-600 hover:bg-medical-700 text-white font-semibold rounded-lg transition-all disabled:opacity-50"
              >
                {isUploading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Scanning OCR...</span>
                  </>
                ) : (
                  <span>Scan & Extract (OCR)</span>
                )}
              </button>
            </div>
          )}

          {/* Upload Result / OCR Extracted Information */}
          {uploadResult && (
            <div className="space-y-3">
              <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs rounded-xl flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span className="font-bold text-xs">
                    OCR Scan Complete — Found {uploadResult.extracted_entities_count} Items
                  </span>
                </div>
                <span className="text-[10px] bg-emerald-200 text-emerald-900 font-bold px-2 py-0.5 rounded-md">
                  OCR 90% Conf.
                </span>
              </div>

              {/* Explicit Label: OCR Extracted Information */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs font-bold text-slate-800">
                  <span>OCR Extracted Information</span>
                  <span className="text-[10px] text-slate-400 font-normal">
                    File: {uploadResult.filename}
                  </span>
                </div>

                <div className="max-h-44 overflow-y-auto space-y-1.5 pr-1">
                  {uploadResult.entities && uploadResult.entities.length > 0 ? (
                    uploadResult.entities.map((ent, i) => (
                      <div
                        key={i}
                        className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs flex items-center justify-between"
                      >
                        <div className="flex items-center space-x-2">
                          <span className="font-bold uppercase text-[10px] bg-sky-100 text-sky-800 px-1.5 py-0.5 rounded">
                            {ent.entity_type}
                          </span>
                          <span className="font-medium text-slate-800">{ent.raw_text}</span>
                        </div>
                        <span className="text-[10px] text-slate-400">Page {ent.page_no}</span>
                      </div>
                    ))
                  ) : (
                    <div className="p-3 bg-slate-50 text-slate-500 text-xs italic text-center rounded-xl">
                      Text scanned successfully. No discrete clinical entities extracted.
                    </div>
                  )}
                </div>
              </div>

              {/* Patient Confirmation Step */}
              {isPatient && !isConfirmed && (
                <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl text-xs space-y-2">
                  <div className="flex items-start space-x-2">
                    <ShieldCheck className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold">Patient Confirmation</p>
                      <p className="text-[11px] text-amber-800">
                        Confirm this OCR extracted information to attach it as a medical document for your doctor's review.
                      </p>
                      <p className="text-[10px] text-amber-700 italic mt-1">
                        Note: Document extractions serve as supplementary context and do not overwrite active conversation state.
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handlePatientConfirm}
                    className="w-full py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-lg transition-all shadow-sm"
                  >
                    Confirm & Submit to Physician Review
                  </button>
                </div>
              )}

              {/* Confirmation Completed Badge */}
              {isConfirmed && (
                <div className="p-3 bg-emerald-100 border border-emerald-300 text-emerald-900 text-xs rounded-xl flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span className="font-bold">
                    {isPatient
                      ? 'Confirmed by Patient — Attached for Physician Review'
                      : 'Attached to Encounter Record as Supporting Document'}
                  </span>
                </div>
              )}

              <div className="flex justify-between pt-1">
                <button
                  onClick={handleReset}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Upload Another Document
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white font-semibold text-xs rounded-xl transition-all"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

