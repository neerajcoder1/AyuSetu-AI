import React, { useState, useRef } from 'react';
import { Bot, User, Volume2, ArrowRight, MessageSquare, AlertCircle, Globe } from 'lucide-react';
import AudioRecorder from '../components/AudioRecorder';
import SlotChecklist from '../components/SlotChecklist';
import { api } from '../services/api';

export default function PatientInterviewScreen({
  sessionId,
  dialogueState,
  preferredLanguage = 'hinglish',
  onLanguageChange,
  onTurnCompleted,
  onGoToDoctorDashboard,
}) {
  const [turns, setTurns] = useState([]);
  const [isSendingTurn, setIsSendingTurn] = useState(false);
  const [lowConfidenceWarning, setLowConfidenceWarning] = useState(false);
  const [playingAudioIndex, setPlayingAudioIndex] = useState(null);
  const [autoPlayNotice, setAutoPlayNotice] = useState(null);
  const [error, setError] = useState(null);

  const currentAudioRef = useRef(null);
  const currentAudioUrlRef = useRef(null);

  // Synchronously primed audio instance to preserve user activation gesture across async API requests
  const primedAudioRef = useRef(null);

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

      // Diagnostic logging of raw turn response audio payload
      console.log('[AudioDiag] Turn API response received:', {
        hasResponseAudio: Boolean(turnRes.response_audio),
        b64Length: turnRes.response_audio ? turnRes.response_audio.length : 0,
        sampleRate: turnRes.response_sample_rate,
        duration: turnRes.response_duration,
        detectedLang: turnRes.detected_language,
        responseTextPreview: turnRes.response_text ? turnRes.response_text.substring(0, 50) : null,
      });

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

      // Automatically play the returned TTS response audio once
      if (turnRes.response_audio) {
        handlePlayTTS(turnRes.response_audio, newTurnIndex, true);
      }

      // Trigger parent update (re-fetches state)
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

    // Stop and clean up any currently playing audio
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
      // Decode base64 to binary byte array
      const binaryString = window.atob(audioB64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Create Blob and Object URL for native browser media element playback
      const blob = new Blob([bytes], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      currentAudioUrlRef.current = blobUrl;

      // Prefer the pre-primed Audio element to retain user activation permission across async boundaries
      const audio = primedAudioRef.current || new Audio();
      currentAudioRef.current = audio;

      console.log('[AudioDiag] Real TTS source assigned:', blobUrl);
      console.log('[AudioDiag] Real TTS blob size:', blob.size, 'bytes');
      console.log('[AudioDiag] Real TTS blob type:', blob.type);

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
        console.log('[AudioDiag] REAL TTS playback finished');
        cleanup();
      };

      audio.onerror = (e) => {
        console.error('[AudioDiag] Real TTS HTMLAudioElement load/playback error:', e, audio.error);
        cleanup();
      };

      console.log('[AudioDiag] waiting for media readiness');

      let hasTriggeredPlay = false;

      const triggerPlay = () => {
        if (hasTriggeredPlay) return;
        hasTriggeredPlay = true;

        console.log('[AudioDiag] loadedmetadata / readiness event fired');
        console.log('[AudioDiag] actual TTS duration:', audio.duration);
        console.log('[AudioDiag] readyState:', audio.readyState);

        const playPromise = audio.play();
        if (playPromise !== undefined) {
          playPromise.then(() => {
            console.log('[AudioDiag] play() succeeded for REAL TTS audio. Duration =', audio.duration);
            setAutoPlayNotice(null);
          }).catch((err) => {
            console.warn('[AudioDiag] play() rejected/blocked for REAL TTS audio:', err);
            cleanup();
            if (isAutoPlay) {
              setAutoPlayNotice('Tap Play Audio to hear the response.');
            }
          });
        }
      };

      audio.onloadedmetadata = () => {
        console.log('[AudioDiag] loadedmetadata fired. actual TTS duration:', audio.duration);
      };

      audio.oncanplay = () => {
        triggerPlay();
      };

      // Pause old media, set new source URL, and force reload
      audio.pause();
      audio.src = blobUrl;
      audio.load();

      // Fallback check if media is already ready synchronously
      if (audio.readyState >= 3 && !hasTriggeredPlay) {
        triggerPlay();
      }
    } catch (e) {
      console.error('[AudioDiag] Real TTS playback exception:', e);
      setPlayingAudioIndex(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Intro Banner */}
      <div className="bg-gradient-to-r from-medical-700 via-medical-600 to-sky-600 rounded-2xl p-6 text-white shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <span className="bg-white/20 text-white font-semibold text-xs px-2.5 py-1 rounded-full uppercase tracking-wider mb-2 inline-block">
            Voice Intake Assistant
          </span>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight">
            AyuSetu Patient Consultation Intake
          </h2>
          <p className="text-sky-100 text-xs sm:text-sm mt-1 max-w-xl">
            Speak naturally in Hindi, Hinglish, or English. AyuSetu extracts clinical symptoms and asks relevant follow-up questions.
          </p>
        </div>

        <button
          onClick={onGoToDoctorDashboard}
          className="flex items-center space-x-2 bg-white text-medical-800 hover:bg-sky-50 font-bold text-xs sm:text-sm px-4 py-2.5 rounded-xl shadow-md transition-all shrink-0"
        >
          <span>Open Doctor Dashboard</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* Session Preferred Language Selection Bar */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-sky-100 text-sky-700 rounded-xl">
            <Globe className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-bold text-slate-900 text-xs sm:text-sm">Patient Preferred Language</h4>
            <p className="text-[11px] text-slate-500">
              Select your preferred response language for this intake session.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200 shrink-0">
          {[
            { id: 'hi', label: 'Hindi (हिन्दी)' },
            { id: 'hinglish', label: 'Hinglish' },
            { id: 'en', label: 'English' },
          ].map((lang) => (
            <button
              key={lang.id}
              onClick={() => onLanguageChange && onLanguageChange(lang.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                preferredLanguage === lang.id
                  ? 'bg-medical-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {autoPlayNotice && (
        <div className="p-3 bg-sky-50 border border-sky-200 text-sky-800 text-xs rounded-xl flex items-center justify-between shadow-sm">
          <div className="flex items-center space-x-2">
            <Volume2 className="w-4 h-4 text-sky-600 shrink-0" />
            <span className="font-semibold">{autoPlayNotice}</span>
          </div>
          <button
            onClick={() => setAutoPlayNotice(null)}
            className="text-sky-600 hover:text-sky-900 font-bold text-xs"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Conversation & Recorder (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Voice Recorder Component */}
          <AudioRecorder
            onSendTurn={handleSendTurn}
            isSendingTurn={isSendingTurn}
            lowConfidenceWarning={lowConfidenceWarning}
          />

          {/* Live Dialogue Transcript Stream */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <MessageSquare className="w-4 h-4 text-medical-600" />
                <h3 className="font-semibold text-slate-900 text-sm sm:text-base">
                  Live Conversation Log
                </h3>
              </div>
              <span className="text-xs text-slate-400 font-medium">
                {turns.length} Turn{turns.length === 1 ? '' : 's'}
              </span>
            </div>

            {turns.length === 0 ? (
              <div className="text-center py-10 space-y-2">
                <Bot className="w-10 h-10 text-slate-300 mx-auto" />
                <p className="text-xs text-slate-500 font-medium">
                  No conversation turns recorded yet.
                </p>
                <p className="text-[11px] text-slate-400">
                  Tap the microphone above to begin your intake.
                </p>
              </div>
            ) : (
              <div className="space-y-4 max-h-[400px] overflow-y-auto pr-1">
                {turns.map((turn, index) => (
                  <div key={turn.id} className="space-y-2">
                    {/* Patient Bubble */}
                    <div className="flex items-start space-x-2 justify-end">
                      <div className="bg-medical-600 text-white rounded-2xl rounded-tr-none px-4 py-2.5 text-xs sm:text-sm max-w-[85%] shadow-sm space-y-1">
                        <div className="flex items-center justify-between space-x-2 text-[10px] text-sky-200 border-b border-white/20 pb-1">
                          <span className="font-bold">Patient</span>
                          <span>
                            Lang: {turn.language.toUpperCase()} | Conf: {(turn.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="leading-relaxed">{turn.patientText}</p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 shrink-0 text-xs font-bold">
                        <User className="w-4 h-4" />
                      </div>
                    </div>

                    {/* AI Response Bubble */}
                    <div className="flex items-start space-x-2 justify-start">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-medical-600 to-sky-500 flex items-center justify-center text-white shrink-0 text-xs font-bold shadow-sm">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="bg-slate-100 border border-slate-200 text-slate-800 rounded-2xl rounded-tl-none px-4 py-2.5 text-xs sm:text-sm max-w-[85%] space-y-2">
                        <div className="flex items-center justify-between text-[10px] text-slate-500 border-b border-slate-200/80 pb-1">
                          <span className="font-bold text-medical-800">AyuSetu AI Assistant</span>
                          {turn.aiAudioB64 && (
                            <button
                              onClick={() => handlePlayTTS(turn.aiAudioB64, index)}
                              className="flex items-center space-x-1 text-medical-700 hover:text-medical-900 font-semibold"
                            >
                              <Volume2 className="w-3.5 h-3.5" />
                              <span>{playingAudioIndex === index ? 'Playing...' : 'Play Audio'}</span>
                            </button>
                          )}
                        </div>
                        <p className="leading-relaxed font-medium">{turn.aiResponseText}</p>
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
    </div>
  );
}
