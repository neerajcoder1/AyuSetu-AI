// frontend/src/components/VoiceStep.jsx
import React from 'react';
import AudioRecorder from '../components/AudioRecorder';
import SlotChecklist from '../components/SlotChecklist';
import AIProcessingVisual from '../components/AIProcessingVisual';

/**
 * VoiceStep UI for the patient interview flow.
 * Props:
 * - handleSendTurn: function to send audio blob and receive AI turn.
 * - turns: array of turn objects (patient and AI messages).
 * - isSendingTurn: boolean indicating if a turn is being processed.
 * - lowConfidenceWarning: boolean indicating low ASR confidence.
 * - activeAudioState: { index, status } for currently playing AI audio.
 * - handleToggleAudio: function to play/pause AI audio for a turn.
 * - goToNextStep: function to advance the flow after voice is completed.
 * - dialogueState: shared dialogue state object (used for slot checklist).
 * - preferredLanguage: language string (e.g., 'hinglish').
 */
export default function VoiceStep({
  handleSendTurn,
  turns,
  isSendingTurn,
  lowConfidenceWarning,
  activeAudioState,
  handleToggleAudio,
  goToNextStep,
  dialogueState,
  preferredLanguage,
}) {
  const missingSlots = dialogueState?.missing_slots || [];
  const canContinue = missingSlots.length === 0 && turns.length > 0 && !isSendingTurn;

  return (
    <div className="space-y-4">
      <AudioRecorder onSendTurn={handleSendTurn} disabled={isSendingTurn} />
      {isSendingTurn && <AIProcessingVisual />}
      {lowConfidenceWarning && (
        <div className="p-2 bg-yellow-50 border border-yellow-200 text-yellow-800 rounded">
          The speech recognition confidence was low. Please consider re‑phrasing.
        </div>
      )}
      {turns.map((turn, idx) => (
        <div key={turn.id} className="border rounded p-2 bg-gray-50">
          <div className="flex justify-between items-center">
            <span className="font-medium text-gray-700">Patient:</span>
            <span>{turn.patientText}</span>
          </div>
          <div className="flex justify-between items-center mt-1">
            <span className="font-medium text-gray-700">Assistant:</span>
            <button onClick={() => handleToggleAudio(turn, idx)} className="text-sky-600 underline">
              {activeAudioState.index === idx && activeAudioState.status === 'playing' ? 'Pause' : 'Play'}
            </button>
          </div>
        </div>
      ))}
      <SlotChecklist dialogueState={dialogueState} />
      <button
        onClick={goToNextStep}
        disabled={!canContinue}
        className={`px-4 py-2 rounded ${canContinue ? 'bg-sky-600 text-white' : 'bg-gray-300 text-gray-600 cursor-not-allowed'}`}
      >
        Continue to Review
      </button>
    </div>
  );
}
