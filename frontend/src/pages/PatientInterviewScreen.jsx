import React, { useState, useRef } from 'react';
import {
  Bot,
  User,
  Volume2,
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
import { api } from '../services/api';

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
  const [turns, setTurns] = useState([]);
  const [isSendingTurn, setIsSendingTurn] = useState(false);
  const [lowConfidenceWarning, setLowConfidenceWarning] = useState(false);
  const [playingAudioIndex, setPlayingAudioIndex] = useState(null);
  const [autoPlayNotice, setAutoPlayNotice] = useState(null);
  const [isDocModalOpen, setIsDocModalOpen] = useState(false);
  const [bodyMapSummary, setBodyMapSummary] = useState('');
  const [error, setError] = useState(null);

  const currentAudioRef = useRef(null);
  const currentAudioUrlRef = useRef(null);

  // Synchronously primed audio instance to preserve user activation gesture across async API requests
  const primedAudioRef = useRef(null);

  const handleBodyMapLocationChange = (locations, summaryString) => {
    setBodyMapSummary(summaryString);
    if (dialogueState && summaryString) {
      if (!dialogueState.collected_info) {
        dialogueState.collected_info = {};
      }
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

    // Stop any audio currently playing from previous turn
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.onended = null;
      currentAudioRef.current.onerror = null;
      currentAudioRef.current = null;
    }

    // Synchronously prime/unlock HTMLAudioElement during user click gesture before async fetch boundary
    try {
      if (!primedAudioRef.current) {
        primedAudioRef.current = new Audio();
      }
      const primedAudio = primedAudioRef.current;
      // 44-byte silent WAV data URI to unlock audio playback permission
      primedAudio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
      const primePromise = primedAudio.play();
      if (primePromise !== undefined) {
        primePromise.then(() => {
          primedAudio.pause();
          console.log('[AudioDiag] Audio element successfully primed during user activation gesture');
        }).catch((e) => {
          console.warn('[AudioDiag] Audio priming gesture notification:', e);
        });
      }
    } catch (e) {
      console.warn('[AudioDiag] Audio priming exception:', e);
    }

    setIsSendingTurn(true);
    setError(null);
    setLowConfidenceWarning(false);

    try {
      const turnRes = await api.sendTurn(sessionId, audioBlob);

      // Low confidence alert check
      if (turnRes.low_confidence) {
        setLowConfidenceWarning(true);
      }

      // Index for the new turn being added
      const newTurnIndex = turns.length;

      // Add to conversation history turns
      const newTurn = {
        id: Date.now(),
        patientText: turnRes.transcribed_text,
        language: turnRes.detected_language,
        confidence: turnRes.asr_confidence,
        lowConfidence: turnRes.low_confidence,
        aiResponseText: turnRes.response_text || 'Samajh gaya, kripya aage batayein.',
        aiAudioB64: turnRes.response_audio,
        redFlags: turnRes.red_flags || [],
      };

      setTurns((prev) => [...prev, newTurn]);

      // Automatically play returned TTS response audio
      if (turnRes.response_audio) {
        handlePlayTTS(turnRes.response_audio, newTurnIndex, true);
      }

      // Trigger parent update
      if (onTurnCompleted) {
        onTurnCompleted(turnRes);
      }
    } catch (err) {
      console.error('Turn submission error:', err);
      setError(err.message || 'Failed to process voice turn.');
    } finally {
      setIsSendingTurn(false);
    }
  };

  const handlePlayTTS = (audioB64, index, isAutoPlay = false) => {
    if (!audioB64) {
      console.warn('[AudioDiag] handlePlayTTS called with empty audioB64');
      return;
    }

    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.onended = null;
      currentAudioRef.current.onerror = null;
      currentAudioRef.current.oncanplay = null;
      currentAudioRef.current.onloadedmetadata = null;
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
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const blob = new Blob([bytes], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      currentAudioUrlRef.current = blobUrl;

      const audio = primedAudioRef.current || new Audio();
      currentAudioRef.current = audio;

      setPlayingAudioIndex(index);

      const cleanup = () => {
        setPlayingAudioIndex(null);
        if (audio) {
          audio.onended = null;
          audio.onerror = null;
          audio.oncanplay = null;
          audio.onloadedmetadata = null;
        }
        if (currentAudioUrlRef.current === blobUrl) {
          URL.revokeObjectURL(blobUrl);
          currentAudioUrlRef.current = null;
        }
        if (currentAudioRef.current === audio) {
          currentAudioRef.current = null;
        }
      };

      audio.onended = () => {
        cleanup();
      };

      audio.onerror = (e) => {
        cleanup();
      };

      let hasTriggeredPlay = false;

      const triggerPlay = () => {
        if (hasTriggeredPlay) return;
        hasTriggeredPlay = true;

        const playPromise = audio.play();
        if (playPromise !== undefined) {
          playPromise.then(() => {
            setAutoPlayNotice(null);
          }).catch((err) => {
            cleanup();
            if (isAutoPlay) {
              setAutoPlayNotice('Tap Play Audio to hear the AI response.');
            }
          });
        }
      };

      audio.oncanplay = () => {
        triggerPlay();
      };

      audio.pause();
      audio.src = blobUrl;
      audio.load();

      if (audio.readyState >= 3 && !hasTriggeredPlay) {
        triggerPlay();
      }
    } catch (e) {
      console.error('[AudioDiag] Real TTS playback exception:', e);
      setPlayingAudioIndex(null);
    }
  };

  const patientDocs = sessionDocuments.filter((d) => d.uploaderRole === 'patient' || d.confirmedByPatient);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Compact Hospital Clinical Header */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-slate-100 pb-3">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-sky-700 bg-sky-50 border border-sky-200/80 px-2.5 py-0.5 rounded-full">
                PATIENT CONSULTATION
              </span>
              <span className="text-slate-300">•</span>
              {/* Dynamic Consultation Status Badge */}
              <div className="inline-flex items-center space-x-1.5 text-xs font-bold">
                <span className="text-slate-500 font-medium">Consultation Status:</span>
                {sessionId ? (
                  <span className="inline-flex items-center space-x-1 text-emerald-700 font-bold bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full text-[11px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span>Active</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center space-x-1 text-amber-700 font-bold bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full text-[11px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                    <span>Not Started</span>
                  </span>
                )}
              </div>
            </div>
            <h1 className="text-lg sm:text-xl font-extrabold text-slate-900 tracking-tight">
              Let's understand what you're experiencing.
            </h1>
            <p className="text-xs text-slate-600 font-normal leading-relaxed max-w-3xl">
              Tell AyuSetu about your symptoms in your own words. You can speak naturally, use the body map to point to problem areas, or upload supporting medical reports.
            </p>
          </div>

          {onGoToDoctorDashboard && (
            <button
              onClick={onGoToDoctorDashboard}
              className="flex items-center space-x-2 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs px-3.5 py-2 rounded-xl shadow-sm transition-all shrink-0"
            >
              <span>Open Physician Cockpit</span>
              <ArrowRight className="w-3.5 h-3.5 text-sky-400" />
            </button>
          )}
        </div>

        {/* Voice-First Clinical Interaction Guidance Panel */}
        <div className="flex items-center justify-between bg-sky-50/70 border border-sky-200/80 rounded-xl p-3 text-xs">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-sky-600 text-white rounded-lg shadow-sm">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div>
              <span className="font-bold text-sky-950 block">🎙 Voice-First Consultation Intake</span>
              <span className="text-[11px] text-sky-800 font-medium">
                Speak naturally in Hindi, Hinglish, or English. Tap the microphone control below to record your response.
              </span>
            </div>
          </div>
          <span className="hidden sm:inline-block text-[10px] font-bold uppercase tracking-wider text-sky-700 bg-white border border-sky-200 px-2.5 py-1 rounded-lg">
            Patient Intake Active
          </span>
        </div>
      </div>


      {/* Patient Medical Document Upload Card */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-5 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-sky-50 text-sky-700 rounded-xl border border-sky-200">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-bold text-slate-900 text-xs sm:text-sm">Upload Medical Document</h4>
              <p className="text-[11px] text-slate-500 font-medium">
                Have lab reports, prescriptions, or medical records? Automated OCR will scan and extract findings for doctor review.
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsDocModalOpen(true)}
            className="flex items-center space-x-1.5 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs px-3.5 py-2 rounded-xl transition-all shadow-sm shrink-0"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Upload Medical Document</span>
          </button>
        </div>

        {/* Display Patient Uploaded Documents list */}
        {patientDocs.length > 0 && (
          <div className="pt-3 border-t border-slate-100 space-y-2">
            <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
              Attached Medical Documents ({patientDocs.length})
            </span>
            <div className="space-y-2">
              {patientDocs.map((doc, idx) => (
                <div key={idx} className="p-3 bg-slate-50/80 border border-slate-200/90 rounded-xl text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900 flex items-center space-x-1.5">
                      <FileText className="w-3.5 h-3.5 text-sky-700" />
                      <span>{doc.filename}</span>
                    </span>
                    <span className="text-[10px] bg-emerald-100 text-emerald-900 font-bold px-2.5 py-0.5 rounded-full flex items-center space-x-1">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                      <span>Confirmed for Doctor Review</span>
                    </span>
                  </div>
                  {doc.entities && doc.entities.length > 0 && (
                    <div className="mt-1 pt-1 border-t border-slate-200/60">
                      <span className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                        OCR Extracted Information:
                      </span>
                      <div className="flex flex-wrap gap-1">
                        {doc.entities.map((e, ei) => (
                          <span key={ei} className="px-2 py-0.5 bg-white border border-slate-200 text-[10px] text-slate-700 rounded-md">
                            <strong className="text-sky-700 uppercase font-bold">{e.entity_type}:</strong> {e.raw_text}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {autoPlayNotice && (
        <div className="p-3.5 bg-sky-50 border border-sky-200 text-sky-900 text-xs rounded-xl flex items-center justify-between shadow-sm">
          <div className="flex items-center space-x-2">
            <Volume2 className="w-4 h-4 text-sky-600 shrink-0" />
            <span className="font-semibold">{autoPlayNotice}</span>
          </div>
          <button
            onClick={() => setAutoPlayNotice(null)}
            className="text-sky-700 hover:text-sky-900 font-bold text-xs"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Conversation, Body Map & Recorder (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Interactive Symptom & Pain Location Mapping */}
          <BodyMapSelector
            onLocationChange={handleBodyMapLocationChange}
            voiceReportedLocation={dialogueState?.collected_info?.location || null}
          />

          {/* Voice Recorder Component */}
          <AudioRecorder
            onSendTurn={handleSendTurn}
            isSendingTurn={isSendingTurn}
            lowConfidenceWarning={lowConfidenceWarning}
          />

          {/* Live Dialogue Transcript Stream */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 sm:p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-sky-50 text-sky-700 rounded-xl">
                  <MessageSquare className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-sm sm:text-base">
                    Live Conversation Log
                  </h3>
                  <p className="text-xs text-slate-500">Real-time ASR transcript & AI responses</p>
                </div>
              </div>
              <span className="text-xs text-slate-500 font-bold bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200">
                {turns.length} Turn{turns.length === 1 ? '' : 's'}
              </span>
            </div>

            {turns.length === 0 ? (
              <div className="text-center py-10 space-y-2 bg-slate-50/60 rounded-xl border border-slate-100">
                <Bot className="w-10 h-10 text-slate-300 mx-auto" />
                <p className="text-xs text-slate-600 font-bold">
                  No conversation turns recorded yet.
                </p>
                <p className="text-[11px] text-slate-400">
                  Tap the microphone above or interact with the body map to begin.
                </p>
              </div>
            ) : (
              <div className="space-y-4 max-h-[420px] overflow-y-auto pr-1">
                {turns.map((turn, index) => (
                  <div key={turn.id} className="space-y-2">
                    {/* Patient Bubble */}
                    <div className="flex items-start space-x-2 justify-end">
                      <div className="bg-sky-600 text-white rounded-2xl rounded-tr-none px-4 py-3 text-xs sm:text-sm max-w-[85%] shadow-sm space-y-1.5">
                        <div className="flex items-center justify-between space-x-2 text-[10px] text-sky-100 border-b border-white/20 pb-1">
                          <span className="font-bold">Patient</span>
                          <span>
                            Lang: {turn.language.toUpperCase()} | Conf: {(turn.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="leading-relaxed font-medium">{turn.patientText}</p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 shrink-0 text-xs font-bold shadow-sm">
                        <User className="w-4 h-4" />
                      </div>
                    </div>

                    {/* AI Response Bubble */}
                    <div className="flex items-start space-x-2 justify-start">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-600 to-teal-500 flex items-center justify-center text-white shrink-0 text-xs font-bold shadow-sm">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="bg-slate-50 border border-slate-200/90 text-slate-900 rounded-2xl rounded-tl-none px-4 py-3 text-xs sm:text-sm max-w-[85%] space-y-2 shadow-sm">
                        <div className="flex items-center justify-between text-[10px] text-slate-500 border-b border-slate-200/80 pb-1">
                          <span className="font-bold text-sky-800">AyuSetu AI Assistant</span>
                          {turn.aiAudioB64 && (
                            <button
                              onClick={() => handlePlayTTS(turn.aiAudioB64, index)}
                              className="flex items-center space-x-1 text-sky-700 hover:text-sky-900 font-bold"
                            >
                              <Volume2 className="w-3.5 h-3.5" />
                              <span>{playingAudioIndex === index ? 'Playing...' : 'Play Response Audio'}</span>
                            </button>
                          )}
                        </div>
                        <p className="leading-relaxed font-semibold">{turn.aiResponseText}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Slot Tracker (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <SlotChecklist dialogueState={dialogueState} />
        </div>
      </div>

      {/* Patient Document Upload Modal */}
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
