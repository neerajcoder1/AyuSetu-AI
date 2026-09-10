import React from 'react';
import { Mic, Square, Send, RefreshCw, Volume2, AlertTriangle } from 'lucide-react';
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
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 sm:p-6 text-center">
      {/* Error Alert */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl text-left flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Low Confidence Warning from last turn */}
      {lowConfidenceWarning && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-xl text-left flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>
            <strong>Low Speech Recognition Confidence</strong> — AI may have misheard your previous response. Please speak clearly into the microphone.
          </span>
        </div>
      )}

      <div className="flex flex-col items-center justify-center space-y-4">
        {/* Main Microphone Button */}
        <div className="relative">
          {/* Animated pulse rings during recording */}
          {isRecording && (
            <div
              className="absolute -inset-3 rounded-full bg-red-400 opacity-75 animate-ping"
              style={{ animationDuration: '1.5s' }}
            />
          )}

          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isSendingTurn}
            className={`relative z-10 w-24 h-24 rounded-full flex flex-col items-center justify-center text-white shadow-xl transition-all duration-300 transform active:scale-95 ${
              isRecording
                ? 'bg-gradient-to-tr from-red-600 to-rose-500 hover:from-red-700 hover:to-rose-600 ring-4 ring-red-200'
                : 'bg-gradient-to-tr from-medical-600 to-sky-500 hover:from-medical-700 hover:to-sky-600 hover:shadow-sky-500/25 ring-4 ring-sky-100'
            } disabled:opacity-50`}
          >
            {isRecording ? (
              <>
                <Square className="w-8 h-8 fill-current mb-1" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Stop</span>
              </>
            ) : (
              <>
                <Mic className="w-9 h-9 mb-1" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Speak</span>
              </>
            )}
          </button>
        </div>

        {/* Recording Status & Timer */}
        {isRecording && (
          <div className="flex flex-col items-center space-y-2">
            <div className="flex items-center space-x-2 bg-red-50 text-red-700 px-3 py-1 rounded-full border border-red-200 font-mono text-sm font-bold">
              <span className="w-2.5 h-2.5 rounded-full bg-red-600 animate-pulse" />
              <span>{formatTime(recordingTime)}</span>
            </div>

            {/* Audio Volume Bar Visualizer */}
            <div className="flex items-center space-x-1 h-6 px-4">
              {[...Array(12)].map((_, i) => {
                const height = Math.max(15, Math.min(100, volumeLevel * (1 + (i % 3) * 0.2)));
                return (
                  <div
                    key={i}
                    className="w-1 bg-red-400 rounded-full transition-all duration-75"
                    style={{ height: `${height}%` }}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Audio Captured Preview */}
        {!isRecording && audioUrl && (
          <div className="w-full max-w-md bg-slate-50 border border-slate-200 rounded-xl p-3 flex flex-col space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700">
                <Volume2 className="w-4 h-4 text-medical-600" />
                <span>Recorded Turn Preview ({formatTime(recordingTime)})</span>
              </div>
              <button
                onClick={clearAudio}
                className="text-xs text-slate-500 hover:text-slate-800 underline"
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
                className="flex items-center space-x-1.5 px-4 py-1.5 bg-medical-600 hover:bg-medical-700 text-white font-semibold text-xs rounded-lg shadow-sm transition-all disabled:opacity-50"
              >
                {isSendingTurn ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing Turn...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Send to AI</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {!isRecording && !audioUrl && (
          <p className="text-xs text-slate-500 max-w-xs">
            Tap the microphone button to start speaking in Hindi, Hinglish, or English.
          </p>
        )}
      </div>
    </div>
  );
}
