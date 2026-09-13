// frontend/src/components/DocumentStep.jsx

import React from 'react';
import DocumentUploadModal from './DocumentUploadModal';

/**
 * DocumentStep UI.
 * Props:
 * - sessionId: current session identifier.
 * - isDocModalOpen: boolean controlling modal visibility.
 * - setIsDocModalOpen: setter for modal state.
 * - onDocumentProcessed: callback after a document is processed.
 * - patientDocs: array of already uploaded patient documents.
 * - goToNextStep: advance flow.
 * - setSkipDocuments: mark documents as skipped.
 */
export default function DocumentStep({
  sessionId,
  isDocModalOpen,
  setIsDocModalOpen,
  onDocumentProcessed,
  patientDocs,
  goToNextStep,
  setSkipDocuments,
}) {
  return (
    <div className="space-y-4">
      <button
        onClick={() => setIsDocModalOpen(true)}
        className="px-4 py-2 bg-sky-600 text-white rounded"
      >
        Upload Medical Document
      </button>

      {patientDocs.length > 0 && (
        <div className="pt-3 border-t">
          <span className="text-xs font-bold">Attached Documents ({patientDocs.length})</span>
          <ul className="list-disc list-inside mt-1 text-xs">
            {patientDocs.map((doc, idx) => (
              <li key={idx}>{doc.filename}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex space-x-2 mt-2">
        <button
          onClick={setSkipDocuments}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded"
        >
          I don’t have a document
        </button>
        <button
          onClick={goToNextStep}
          className="px-4 py-2 bg-sky-600 text-white rounded"
        >
          Continue
        </button>
      </div>

      <DocumentUploadModal
        sessionId={sessionId}
        isOpen={isDocModalOpen}
        onClose={() => setIsDocModalOpen(false)}
        onDocumentProcessed={onDocumentProcessed}
        uploaderRole="patient"
      />
    </div>
  );
}
