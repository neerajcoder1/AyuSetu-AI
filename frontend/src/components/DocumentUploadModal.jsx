import React, { useState } from 'react';
import { FileText, Upload, CheckCircle2, AlertCircle, RefreshCw, X, FileCheck } from 'lucide-react';
import { api } from '../services/api';

export default function DocumentUploadModal({
  sessionId,
  isOpen,
  onClose,
  onDocumentProcessed,
}) {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setUploadResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file || !sessionId) return;

    setIsUploading(true);
    setError(null);
    try {
      const res = await api.uploadDocument(sessionId, file);
      setUploadResult(res);
      if (onDocumentProcessed) {
        onDocumentProcessed(res);
      }
    } catch (err) {
      console.error('Failed to upload document:', err);
      setError(err.message || 'Failed to process document through Document AI.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-sky-100 text-sky-700 rounded-xl">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm sm:text-base">Document AI — File Upload</h3>
              <p className="text-xs text-slate-500">OCR & Entity Extraction into Session Memory</p>
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
                  Supports TXT, PDF, PNG, JPG (Mock OCR Parser)
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
                    <span>Extracting...</span>
                  </>
                ) : (
                  <span>Process Document</span>
                )}
              </button>
            </div>
          )}

          {/* Upload Result / Entities */}
          {uploadResult && (
            <div className="space-y-3">
              <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs rounded-xl flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span className="font-semibold">
                    Extracted {uploadResult.extracted_entities_count} Clinical Entities
                  </span>
                </div>
                <span className="text-[10px] bg-emerald-200 text-emerald-900 font-bold px-2 py-0.5 rounded-md">
                  OCR 90% Conf.
                </span>
              </div>

              {/* Entity List */}
              <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                {uploadResult.entities.map((ent, i) => (
                  <div
                    key={i}
                    className="p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="font-bold uppercase text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded">
                        {ent.entity_type}
                      </span>
                      <span className="font-medium text-slate-800">{ent.raw_text}</span>
                    </div>
                    <span className="text-[10px] text-slate-400">Page {ent.page_no}</span>
                  </div>
                ))}
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => {
                    setFile(null);
                    setUploadResult(null);
                  }}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Upload Another
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
