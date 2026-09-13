import React from 'react';
import { Mic, Square, Send, RefreshCw, Volume2, AlertTriangle, Radio } from 'lucide-react';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';

export default function AudioRecorder({
  onSendTurn,
  isSendingTurn,
  lowConfidenceWarning,
}) {
  const {
    isRecording,
    audioBlob,
    audioUrl,
    recordingTime,
    volumeLevel,
    error,
    startRecording,
    stopRecording,
    clearAudio,
  } = useVoiceRecorder();

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleSend = () => {
    if (audioBlob) {
      onSendTurn(audioBlob);
      clearAudio();
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 text-center space-y-4">
      {/* Card Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-medical-50 text-medical-700 rounded-xl">
            <Radio className="w-4 h-4" />
          </div>
          <div className="text-left">
            <h3 className="font-bold text-slate-900 text-sm sm:text-base">Voice Consultation Mic</h3>
            <p className="text-xs text-slate-500">Speak your symptoms naturally in Hindi, Hinglish, or English</p>
          </div>
        </div>
        {isRecording && (
          <span className="flex items-center space-x-1.5 px-2.5 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded-full text-xs font-bold font-mono">
            <span className="w-2 h-2 rounded-full bg-rose-600 animate-pulse" />
            <span>RECORDING ({formatTime(recordingTime)})</span>
          </span>
        )}
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl text-left flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Low Confidence Warning from last turn */}
      {lowConfidenceWarning && (
        <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded-xl text-left flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>
            <strong>Low Speech Recognition Confidence</strong> — AI may have misheard your previous response. Please speak clearly into the microphone.
          </span>
        </div>
      )}

      <div className="flex flex-col items-center justify-center space-y-4 py-2">
        {/* Main Microphone Button */}
        <div className="relative">
          {/* Animated pulse rings during recording */}
          {isRecording && (
            <div
              className="absolute -inset-3 rounded-full bg-rose-400 opacity-75 animate-ping"
              style={{ animationDuration: '1.5s' }}
            />
          )}

          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isSendingTurn}
            className={`relative z-10 w-24 h-24 rounded-full flex flex-col items-center justify-center text-white shadow-lg transition-all duration-200 transform active:scale-95 ${
              isRecording
                ? 'bg-rose-600 hover:bg-rose-700 ring-4 ring-rose-200'
                : 'bg-medical-700 hover:bg-medical-800 ring-4 ring-teal-100 hover:shadow-teal-700/20'
            } disabled:opacity-50`}
          >
            {isRecording ? (
              <>
                <Square className="w-7 h-7 fill-current mb-1" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Stop</span>
              </>
            ) : (
              <>
                <Mic className="w-8 h-8 mb-1" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Tap to Speak</span>
              </>
            )}
          </button>
        </div>

        {/* Audio Volume Bar Visualizer during recording */}
        {isRecording && (
          <div className="flex flex-col items-center space-y-2">
            <div className="flex items-center space-x-1.5 h-6 px-4">
              {[...Array(12)].map((_, i) => {
                const height = Math.max(15, Math.min(100, volumeLevel * (1 + (i % 3) * 0.2)));
                return (
                  <div
                    key={i}
                    className="w-1.5 bg-rose-500 rounded-full transition-all duration-75"
                    style={{ height: `${height}%` }}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Audio Captured Preview */}
        {!isRecording && audioUrl && (
          <div className="w-full max-w-md bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 text-xs font-bold text-slate-700">
                <Volume2 className="w-4 h-4 text-medical-700" />
                <span>Recorded Turn Preview ({formatTime(recordingTime)})</span>
              </div>
              <button
                onClick={clearAudio}
                className="text-xs text-slate-500 hover:text-slate-800 font-semibold underline"
              >
                Re-record
              </button>
            </div>

            <audio src={audioUrl} controls className="w-full h-8" />

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                onClick={clearAudio}
                disabled={isSendingTurn}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={isSendingTurn}
                className="flex items-center space-x-1.5 px-4 py-1.5 bg-medical-700 hover:bg-medical-800 text-white font-bold text-xs rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {isSendingTurn ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing Turn...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Send to AI Consultation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {!isRecording && !audioUrl && (
          <p className="text-xs text-slate-500 max-w-xs font-medium">
            Tap the microphone button to start speaking. AyuSetu AI will listen and ask follow-up questions.
          </p>
        )}
      </div>
    </div>
  );
}
