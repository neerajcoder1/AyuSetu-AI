// frontend/src/pages/PatientInterviewScreen.jsx

import React, { useState, useRef, useEffect } from 'react';
import {
  Bot,
  User,
  Volume2,
  Play,
  Pause,
  RotateCcw,
  ArrowRight,
  MessageSquare,
  AlertCircle,
  Globe,
  FileText,
  Upload,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import AudioRecorder from '../components/AudioRecorder';
import SlotChecklist from '../components/SlotChecklist';
import DocumentUploadModal from '../components/DocumentUploadModal';
import BodyMapSelector from '../components/BodyMapSelector';
import AIProcessingVisual from '../components/AIProcessingVisual';
import { api } from '../services/api';
import { usePatientFlow, PatientFlowStep } from '../hooks/usePatientFlow';
import ProgressIndicator from '../components/ProgressIndicator';
import BodyMapStep from '../components/BodyMapStep';
import DocumentStep from '../components/DocumentStep';
import VoiceStep from '../components/VoiceStep';
import ReviewStep from '../components/ReviewStep';
import SubmittedStep from '../components/SubmittedStep';

export default function PatientInterviewScreen({
  sessionId,
  dialogueState,
  preferredLanguage = 'hinglish',
  onLanguageChange,
  onTurnCompleted,
  onGoToDoctorDashboard,
  sessionDocuments = [],
  onDocumentProcessed,
}) {
  // UI flow hook
  const {
    currentStep,
    setCurrentStep,
    goToNextStep,
    goToPreviousStep,
    setSkipBodyMap,
    setSkipDocuments,
  } = usePatientFlow(sessionId);

  // Shared state for voice step
  const [turns, setTurns] = useState([]);
  const [isSendingTurn, setIsSendingTurn] = useState(false);
  const [lowConfidenceWarning, setLowConfidenceWarning] = useState(false);
  const [activeAudioState, setActiveAudioState] = useState({ index: null, status: 'idle' });
  const [autoPlayNotice, setAutoPlayNotice] = useState(null);
  const [isDocModalOpen, setIsDocModalOpen] = useState(false);
  const [bodyMapSummary, setBodyMapSummary] = useState('');
  const [error, setError] = useState(null);

  const currentAudioRef = useRef(null);
  const currentAudioUrlRef = useRef(null);
  const primedAudioRef = useRef(null);

  // ----- Handlers -----
  const handleBodyMapLocationChange = (locations, summaryString) => {
    setBodyMapSummary(summaryString);
    if (dialogueState && summaryString) {
      dialogueState.collected_info = dialogueState.collected_info || {};
      dialogueState.collected_info.location = summaryString;
      if (dialogueState.missing_slots) {
        dialogueState.missing_slots = dialogueState.missing_slots.filter((s) => s !== 'location');
      }
    }
  };

  const handleSendTurn = async (audioBlob) => {
    if (!sessionId) {
      setError('No active session. Please start a session first.');
      return;
    }
    // Pause any playing audio
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    setActiveAudioState({ index: null, status: 'idle' });
    // Prime audio element to satisfy user gesture
    try {
      if (!primedAudioRef.current) {
        primedAudioRef.current = new Audio();
      }
      const primedAudio = primedAudioRef.current;
      primedAudio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
      const playPromise = primedAudio.play();
      if (playPromise !== undefined) {
        playPromise.then(() => primedAudio.pause()).catch(() => {});
      }
    } catch (e) {}
    setIsSendingTurn(true);
    setError(null);
    setLowConfidenceWarning(false);
    try {
      const turnRes = await api.sendTurn(sessionId, audioBlob);
      if (turnRes.low_confidence) setLowConfidenceWarning(true);
      const newTurn = {
        id: Date.now(),
        patientText: turnRes.transcribed_text,
        language: turnRes.detected_language,
        confidence: turnRes.asr_confidence,
        lowConfidence: turnRes.low_confidence,
        aiResponseText: turnRes.response_text || 'Samajh gaya, kripya aage batayein.',
        aiAudioB64: turnRes.response_audio,
        redFlags: turnRes.red_flags || [],
        preferredLanguage: turnRes.preferred_language || preferredLanguage,
      };
      setTurns((prev) => [...prev, newTurn]);
      if (turnRes.response_audio) playTurnAudio(turnRes.response_audio, turns.length, true);
      if (onTurnCompleted) onTurnCompleted(turnRes);
    } catch (err) {
      setError(err.message || 'Failed to process voice turn.');
    } finally {
      setIsSendingTurn(false);
    }
  };

  const playTurnAudio = (audioB64, index, isAutoPlay = false) => {
    if (!audioB64) {
      setActiveAudioState({ index, status: 'error' });
      return;
    }
    // Cleanup previous audio
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    if (currentAudioUrlRef.current) {
      URL.revokeObjectURL(currentAudioUrlRef.current);
      currentAudioUrlRef.current = null;
    }
    try {
      const binaryString = window.atob(audioB64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = binaryString.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      currentAudioUrlRef.current = blobUrl;
      const audio = primedAudioRef.current || new Audio();
      currentAudioRef.current = audio;
      setActiveAudioState({ index, status: 'playing' });
      const cleanup = (finalStatus = 'idle') => {
        setActiveAudioState({ index, status: finalStatus });
        if (audio) {
          audio.onended = audio.onerror = null;
        }
        if (currentAudioUrlRef.current === blobUrl) {
          URL.revokeObjectURL(blobUrl);
          currentAudioUrlRef.current = null;
        }
        if (currentAudioRef.current === audio) {
          currentAudioRef.current = null;
        }
      };
      audio.onended = () => cleanup('ended');
      audio.onerror = () => cleanup('error');
      let hasTriggeredPlay = false;
      const triggerPlay = () => {
        if (hasTriggeredPlay) return;
        hasTriggeredPlay = true;
        const playPromise = audio.play();
        if (playPromise !== undefined) {
          playPromise
            .then(() => setAutoPlayNotice(null))
            .catch(() => {
              cleanup('idle');
              if (isAutoPlay) setAutoPlayNotice('Tap "Listen to response" below to hear the AI response.');
            });
        }
      };
      audio.oncanplay = triggerPlay;
      audio.pause();
      audio.src = blobUrl;
      audio.load();
      if (audio.readyState >= 3 && !hasTriggeredPlay) triggerPlay();
    } catch (e) {
      setActiveAudioState({ index, status: 'error' });
    }
  };

  const handleToggleAudio = (turn, index) => {
    const isCurrent = activeAudioState.index === index;
    const status = isCurrent ? activeAudioState.status : 'idle';
    if (!turn.aiAudioB64) {
      setActiveAudioState({ index, status: 'error' });
      return;
    }
    if (isCurrent && status === 'playing') {
      currentAudioRef.current?.pause();
      setActiveAudioState({ index, status: 'paused' });
    } else if (isCurrent && status === 'paused') {
      currentAudioRef.current
        ?.play()
        .then(() => setActiveAudioState({ index, status: 'playing' }))
        .catch(() => playTurnAudio(turn.aiAudioB64, index, false));
    } else {
      playTurnAudio(turn.aiAudioB64, index, false);
    }
  };

  const patientDocs = sessionDocuments.filter((d) => d.uploaderRole === 'patient' || d.confirmedByPatient);

  // Render step-specific UI
  const renderCurrentStep = () => {
    switch (currentStep) {
      case PatientFlowStep.BODY_MAP:
        return (
          <BodyMapStep
            handleBodyMapLocationChange={handleBodyMapLocationChange}
            dialogueState={dialogueState}
            goToNextStep={goToNextStep}
            setSkipBodyMap={setSkipBodyMap}
          />
        );
      case PatientFlowStep.DOCUMENTS:
        return (
          <DocumentStep
            sessionId={sessionId}
            isDocModalOpen={isDocModalOpen}
            setIsDocModalOpen={setIsDocModalOpen}
            onDocumentProcessed={onDocumentProcessed}
            patientDocs={patientDocs}
            goToNextStep={goToNextStep}
            setSkipDocuments={setSkipDocuments}
          />
        );
      case PatientFlowStep.VOICE:
        return (
          <VoiceStep
            handleSendTurn={handleSendTurn}
            turns={turns}
            isSendingTurn={isSendingTurn}
            lowConfidenceWarning={lowConfidenceWarning}
            activeAudioState={activeAudioState}
            handleToggleAudio={handleToggleAudio}
            goToNextStep={goToNextStep}
            dialogueState={dialogueState}
            preferredLanguage={preferredLanguage}
          />
        );
      case PatientFlowStep.REVIEW:
        return (
          <ReviewStep
            dialogueState={dialogueState}
            sessionDocuments={sessionDocuments}
            goToPreviousStep={goToPreviousStep}
            onGoToDoctorDashboard={onGoToDoctorDashboard}
            setCurrentStep={setCurrentStep}
            PatientFlowStep={PatientFlowStep}
          />
        );
      case PatientFlowStep.SUBMITTED:
        return <SubmittedStep />;
      default:
        return null;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <ProgressIndicator currentStep={currentStep} />
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded">
          {error}
        </div>
      )}
      {autoPlayNotice && (
        <div className="p-3 bg-sky-50 border border-sky-200 text-sky-900 rounded flex justify-between items-center">
          <span>{autoPlayNotice}</span>
          <button onClick={() => setAutoPlayNotice(null)} className="text-sky-700 underline">
            Dismiss
          </button>
        </div>
      )}
      {renderCurrentStep()}
    </div>
  );
}
