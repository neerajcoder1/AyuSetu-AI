// frontend/src/components/ReviewStep.jsx
import React, { useState } from 'react';
import {
  Heart,
  MapPin,
  Clock,
  Calendar,
  Gauge,
  Stethoscope,
  Pill,
  AlertTriangle,
  Users,
  Activity,
  FileText,
  Loader2,
  Send,
  ChevronLeft,
  Pencil,
} from 'lucide-react';
import { api } from '../services/api';

/**
 * Human-readable labels and icons for the 12 clinical slots.
 */
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

/** Map enum or raw key to normalized slot key */
function normalizeSlotKey(rawKey) {
  if (typeof rawKey === 'string') return rawKey;
  if (rawKey && rawKey.value) return rawKey.value;
  return String(rawKey);
}

/**
 * ReviewStep — Displays collected clinical info as readable cards
 * and provides a real submit-to-physician button.
 */
export default function ReviewStep({
  dialogueState,
  sessionDocuments,
  sessionId,
  goToPreviousStep,
  goToNextStep,
  onSubmissionComplete,
  setCurrentStep,
  PatientFlowStep,
}) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const rawInfo = dialogueState?.collected_info || {};
  // Normalize keys
  const collectedInfo = {};
  Object.entries(rawInfo).forEach(([k, v]) => {
    collectedInfo[normalizeSlotKey(k)] = typeof v === 'string' ? v : String(v);
  });

  const patientDocs = sessionDocuments.filter(
    (d) => d.uploaderRole === 'patient' || d.confirmedByPatient
  );

  const filledSlots = Object.keys(collectedInfo).filter((k) => collectedInfo[k]);
  const totalSlots = Object.keys(SLOT_CONFIG).length;

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

  const handleSubmit = async () => {
    if (!sessionId) {
      setSubmitError('No active session found.');
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const result = await api.submitToPhysician(sessionId);
      // Pass submission data up and advance to SUBMITTED step
      if (onSubmissionComplete) {
        onSubmissionComplete(result);
      }
      if (goToNextStep) {
        goToNextStep();
      }
    } catch (err) {
      setSubmitError(
        err.message || 'Submission failed. Your information has not been submitted. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Review Your Information</h2>
        <p className="text-sm text-gray-500 mt-1">
          Please review the information below before submitting to a physician.
          {filledSlots.length > 0 && (
            <span className="ml-1 font-medium text-sky-700">
              {filledSlots.length} of {totalSlots} fields collected.
            </span>
          )}
        </p>
      </div>

      {/* Error Banner */}
      {submitError && (
        <div className="p-4 bg-red-50 border border-red-300 text-red-800 rounded-lg flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-medium">Submission Failed</p>
            <p className="text-sm mt-1">{submitError}</p>
          </div>
        </div>
      )}

      {/* Clinical Information Cards */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h3 className="font-medium text-gray-800">Clinical Information</h3>
          <button onClick={goToVoice} className="text-sm text-sky-600 hover:text-sky-800 flex items-center gap-1">
            <Pencil className="w-3.5 h-3.5" />
            Edit Voice Answers
          </button>
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
                    <p className="text-sm text-gray-400 italic mt-0.5">Not yet provided</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Documents Section */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h3 className="font-medium text-gray-800">Uploaded Documents</h3>
          <button onClick={goToDocuments} className="text-sm text-sky-600 hover:text-sky-800 flex items-center gap-1">
            <Pencil className="w-3.5 h-3.5" />
            Edit Documents
          </button>
        </div>
        <div className="px-4 py-3">
          {patientDocs.length > 0 ? (
            <ul className="space-y-2">
              {patientDocs.map((doc, idx) => (
                <li key={idx} className="flex items-center gap-2 text-sm text-gray-700">
                  <FileText className="w-4 h-4 text-gray-400" />
                  {doc.filename}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 italic">No documents uploaded.</p>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={goToPreviousStep}
          className="px-4 py-2.5 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg flex items-center gap-2 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back
        </button>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting}
          className={`px-6 py-2.5 rounded-lg flex items-center gap-2 font-medium transition-colors ${
            isSubmitting
              ? 'bg-sky-400 text-white cursor-not-allowed'
              : 'bg-sky-600 hover:bg-sky-700 text-white'
          }`}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Submitting…
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              Submit to Physician
            </>
          )}
        </button>
      </div>
    </div>
  );
}
