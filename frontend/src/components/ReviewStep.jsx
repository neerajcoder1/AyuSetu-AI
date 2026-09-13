// frontend/src/components/ReviewStep.jsx
import React from 'react';

/**
 * ReviewStep UI for patient flow.
 * Props:
 * - dialogueState: object containing collected_info and missing_slots.
 * - sessionDocuments: array of document objects.
 * - goToPreviousStep: function to go back one step.
 * - onGoToDoctorDashboard: callback to submit to physician.
 */
export default function ReviewStep({
  dialogueState,
  sessionDocuments,
  goToPreviousStep,
  onGoToDoctorDashboard,
  setCurrentStep,
  PatientFlowStep,
}) {
  const collectedInfo = dialogueState?.collected_info || {};
  const patientDocs = sessionDocuments.filter(
    (d) => d.uploaderRole === 'patient' || d.confirmedByPatient
  );
  const goToVoice = () => {
    if (setCurrentStep && PatientFlowStep) {
      setCurrentStep(PatientFlowStep.VOICE);
    }
  };
  const goToDocuments = () => {
    if (setCurrentStep && PatientFlowStep) {
      setCurrentStep(PatientFlowStep.DOCUMENTS);
    }
  };


  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Review Your Information</h2>
      <div className="border p-4 bg-gray-50 rounded">
        <h3 className="font-medium mb-2">Collected Information</h3>
        <pre className="text-xs overflow-auto max-h-48 bg-white p-2 rounded border">
{JSON.stringify(collectedInfo, null, 2)}
        </pre>
        <button
          onClick={goToVoice}
          className="mt-2 text-sky-600 underline"
        >
          Edit Voice Answers
        </button>
      </div>
      <div className="border p-4 bg-gray-50 rounded">
        <h3 className="font-medium mb-2">Uploaded Documents</h3>
        {patientDocs.length > 0 ? (
          <ul className="list-disc list-inside text-sm">
            {patientDocs.map((doc, idx) => (
              <li key={idx}>{doc.filename}</li>
            ))}
          </ul>
        ) : (
          <p className="text-gray-600 text-sm">No documents uploaded.</p>
        )}
        <button
          onClick={goToDocuments}
          className="mt-2 text-sky-600 underline"
        >
          Edit Documents
        </button>
      </div>
      <div className="flex space-x-2 mt-4">
        <button
          onClick={goToPreviousStep}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded"
        >
          Back
        </button>
        <button
          onClick={onGoToDoctorDashboard}
          className="px-4 py-2 bg-sky-600 text-white rounded"
        >
          Submit to Physician
        </button>
      </div>
    </div>
  );
}
