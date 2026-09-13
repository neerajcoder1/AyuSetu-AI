// src/hooks/usePatientFlow.js

/**
 * Hook to manage the patient dashboard flow state on the frontend.
 * Persists the current step in localStorage scoped to the session/encounter ID.
 * Does NOT modify any backend schema.
 */
import { useState, useEffect, useCallback } from "react";

export const PatientFlowStep = Object.freeze({
  BODY_MAP: "BODY_MAP",
  DOCUMENTS: "DOCUMENTS",
  VOICE: "VOICE",
  REVIEW: "REVIEW",
  SUBMITTED: "SUBMITTED",
});

/** Generates the localStorage key for a given session ID. */
const storageKey = (sessionId) => `ayusetu_patient_flow_${sessionId}`;

/** Load persisted flow state from localStorage. */
const loadState = (sessionId) => {
  if (!sessionId) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Object.values(PatientFlowStep).includes(parsed.currentStep)) {
      return null;
    }
    return parsed;
  } catch (e) {
    console.warn("Failed to load patient flow state", e);
    return null;
  }
};

/** Persist the flow state to localStorage. */
const saveState = (sessionId, state) => {
  if (!sessionId) return;
  try {
    window.localStorage.setItem(storageKey(sessionId), JSON.stringify(state));
  } catch (e) {
    console.warn("Failed to save patient flow state", e);
  }
};

export const usePatientFlow = (sessionId) => {
  const [currentStep, setCurrentStep] = useState(PatientFlowStep.BODY_MAP);
  const [bodyMapSkipped, setBodyMapSkipped] = useState(false);
  const [documentsSkipped, setDocumentsSkipped] = useState(false);

  // Initialise from storage on mount or when sessionId changes
  useEffect(() => {
    if (!sessionId) return;
    const persisted = loadState(sessionId);
    if (persisted) {
      setCurrentStep(persisted.currentStep);
      setBodyMapSkipped(!!persisted.bodyMapSkipped);
      setDocumentsSkipped(!!persisted.documentsSkipped);
    } else {
      const init = {
        currentStep: PatientFlowStep.BODY_MAP,
        bodyMapSkipped: false,
        documentsSkipped: false,
      };
      saveState(sessionId, init);
    }
  }, [sessionId]);

  const persist = useCallback(
    (step, skipBody, skipDocs) => {
      if (!sessionId) return;
      const state = {
        currentStep: step,
        bodyMapSkipped: !!skipBody,
        documentsSkipped: !!skipDocs,
      };
      saveState(sessionId, state);
    },
    [sessionId]
  );

  const goToNextStep = useCallback(() => {
    const order = [
      PatientFlowStep.BODY_MAP,
      PatientFlowStep.DOCUMENTS,
      PatientFlowStep.VOICE,
      PatientFlowStep.REVIEW,
      PatientFlowStep.SUBMITTED,
    ];
    const idx = order.indexOf(currentStep);
    if (idx >= 0 && idx < order.length - 1) {
      const next = order[idx + 1];
      setCurrentStep(next);
      persist(next, bodyMapSkipped, documentsSkipped);
    }
  }, [currentStep, bodyMapSkipped, documentsSkipped, persist]);

  const goToPreviousStep = useCallback(() => {
    const order = [
      PatientFlowStep.BODY_MAP,
      PatientFlowStep.DOCUMENTS,
      PatientFlowStep.VOICE,
      PatientFlowStep.REVIEW,
      PatientFlowStep.SUBMITTED,
    ];
    const idx = order.indexOf(currentStep);
    if (idx > 0) {
      const prev = order[idx - 1];
      setCurrentStep(prev);
      persist(prev, bodyMapSkipped, documentsSkipped);
    }
  }, [currentStep, bodyMapSkipped, documentsSkipped, persist]);

  const setSkipBodyMap = useCallback(() => {
    setBodyMapSkipped(true);
    persist(currentStep, true, documentsSkipped);
  }, [currentStep, documentsSkipped, persist]);

  const setSkipDocuments = useCallback(() => {
    setDocumentsSkipped(true);
    persist(currentStep, bodyMapSkipped, true);
  }, [currentStep, bodyMapSkipped, persist]);

  return {
    currentStep,
    setCurrentStep,
    goToNextStep,
    goToPreviousStep,
    bodyMapSkipped,
    documentsSkipped,
    setSkipBodyMap,
    setSkipDocuments,
    PatientFlowStep,
  };
};
