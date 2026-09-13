// frontend/src/components/BodyMapStep.jsx

import React from 'react';
import BodyMapSelector from './BodyMapSelector';

/**
 * BodyMapStep UI.
 * Props:
 * - handleBodyMapLocationChange: callback from parent to process location.
 * - dialogueState: current dialogue state object (may be updated).
 * - goToNextStep: advance to next flow step.
 * - setSkipBodyMap: mark body map as skipped.
 */
export default function BodyMapStep({
  handleBodyMapLocationChange,
  dialogueState,
  goToNextStep,
  setSkipBodyMap,
}) {
  return (
    <div className="space-y-4">
      <BodyMapSelector
        onLocationChange={handleBodyMapLocationChange}
        voiceReportedLocation={dialogueState?.collected_info?.location || null}
      />
      <div className="flex space-x-2">
        <button
          onClick={setSkipBodyMap}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded"
        >
          Skip
        </button>
        <button
          onClick={goToNextStep}
          className="px-4 py-2 bg-sky-600 text-white rounded"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
