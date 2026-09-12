import React, { useState } from 'react';
import { Target, RotateCcw, AlertTriangle, CheckCircle2, X, Info, ShieldCheck } from 'lucide-react';

// Anatomical region definitions (Patient-friendly, NO organ names, English only)
const FRONT_REGIONS = [
  { id: 'head_face', label: 'Head / Face', defaultSide: 'center' },
  { id: 'neck', label: 'Neck / Throat', defaultSide: 'center' },
  { id: 'chest', label: 'Chest', defaultSide: 'center' },
  { id: 'abdomen', label: 'Abdomen / Stomach Area', defaultSide: 'center' },
  { id: 'pelvis', label: 'Pelvis / Groin', defaultSide: 'center' },
  { id: 'shoulder_left', label: 'Left Shoulder', defaultSide: 'left' },
  { id: 'shoulder_right', label: 'Right Shoulder', defaultSide: 'right' },
  { id: 'arm_left', label: 'Left Arm / Hand', defaultSide: 'left' },
  { id: 'arm_right', label: 'Right Arm / Hand', defaultSide: 'right' },
  { id: 'leg_left', label: 'Left Leg / Foot', defaultSide: 'left' },
  { id: 'leg_right', label: 'Right Leg / Foot', defaultSide: 'right' },
];

const BACK_REGIONS = [
  { id: 'head_back', label: 'Back of Head', defaultSide: 'center' },
  { id: 'neck_back', label: 'Back of Neck', defaultSide: 'center' },
  { id: 'upper_back', label: 'Upper Back', defaultSide: 'center' },
  { id: 'lower_back', label: 'Lower Back / Flank', defaultSide: 'center' },
  { id: 'buttock', label: 'Buttocks / Hip', defaultSide: 'center' },
  { id: 'shoulder_left_back', label: 'Left Shoulder (Back)', defaultSide: 'left' },
  { id: 'shoulder_right_back', label: 'Right Shoulder (Back)', defaultSide: 'right' },
  { id: 'arm_left_back', label: 'Left Arm (Back)', defaultSide: 'left' },
  { id: 'arm_right_back', label: 'Right Arm (Back)', defaultSide: 'right' },
  { id: 'leg_left_back', label: 'Left Calf / Heel', defaultSide: 'left' },
  { id: 'leg_right_back', label: 'Right Calf / Heel', defaultSide: 'right' },
];

export default function BodyMapSelector({
  onLocationChange,
  voiceReportedLocation = null,
  initialLocations = [],
}) {
  const [view, setView] = useState('front'); // 'front' | 'back'
  const [selectedRegion, setSelectedRegion] = useState(null); // Active region being refined
  const [pendingSide, setPendingSide] = useState('center'); // 'left' | 'center' | 'right'
  const [pendingDepth, setPendingDepth] = useState('internal'); // 'external' | 'internal' | 'not_sure'
  const [selectedLocations, setSelectedLocations] = useState(initialLocations);

  const activeRegions = view === 'front' ? FRONT_REGIONS : BACK_REGIONS;

  const handleRegionClick = (region) => {
    setSelectedRegion(region);
    setPendingSide(region.defaultSide || 'center');
    setPendingDepth('internal');
  };

  const handleAddLocation = () => {
    if (!selectedRegion) return;

    // Build patient-reported approximate location (STRICTLY NO ORGAN NAMES)
    const sideText = pendingSide === 'left' ? 'Left' : pendingSide === 'right' ? 'Right' : 'Center';
    const depthText = pendingDepth === 'external' ? 'External / Skin level' : pendingDepth === 'internal' ? 'Internal / Deep' : 'Unspecified depth';

    const locationText = `${sideText} ${selectedRegion.label} (${depthText}, patient-reported)`;

    const newLoc = {
      id: `${selectedRegion.id}_${pendingSide}_${pendingDepth}_${Date.now()}`,
      regionId: selectedRegion.id,
      regionLabel: selectedRegion.label,
      view: view,
      side: pendingSide,
      depth: pendingDepth,
      locationText: locationText,
      formattedSummary: `${sideText} ${selectedRegion.label} — ${depthText}`,
    };

    // Prevent duplicate entries for exact same region & side
    const updated = [...selectedLocations.filter((l) => !(l.regionId === newLoc.regionId && l.side === newLoc.side)), newLoc];
    setSelectedLocations(updated);
    setSelectedRegion(null);

    // Notify parent component / session state
    if (onLocationChange) {
      const combinedString = updated.map((l) => l.formattedSummary).join('; ');
      onLocationChange(updated, combinedString);
    }
  };

  const handleRemoveLocation = (idToRemove) => {
    const updated = selectedLocations.filter((l) => l.id !== idToRemove);
    setSelectedLocations(updated);

    if (onLocationChange) {
      const combinedString = updated.map((l) => l.formattedSummary).join('; ');
      onLocationChange(updated, combinedString);
    }
  };

  const handleClearAll = () => {
    setSelectedLocations([]);
    setSelectedRegion(null);
    if (onLocationChange) {
      onLocationChange([], '');
    }
  };

  // Check for discrepancy between voice reported location and body map selection
  const bodyMapString = selectedLocations.map((l) => l.formattedSummary.toLowerCase()).join(' ');
  const hasDiscrepancy =
    voiceReportedLocation &&
    selectedLocations.length > 0 &&
    !voiceReportedLocation.toLowerCase().split(' ').some((word) => word.length > 3 && bodyMapString.includes(word));

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5 space-y-4">
      {/* Header Title */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-teal-100 text-teal-700 rounded-xl">
            <Target className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-sm sm:text-base">
              Where do you feel the problem?
            </h3>
            <p className="text-xs text-slate-500">
              Tap to select approximate area.
            </p>
          </div>
        </div>

        {/* View Switcher Controls */}
        <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl border border-slate-200 shrink-0">
          <button
            onClick={() => setView('front')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              view === 'front' ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Front
          </button>
          <button
            onClick={() => setView('back')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              view === 'back' ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Back
          </button>
        </div>
      </div>

      {/* Discrepancy Alert Notice (if Voice & Body Map differ) */}
      {hasDiscrepancy && (
        <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded-xl flex items-start space-x-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold block">Patient Location Input Comparison</span>
            <p className="text-[11px] text-amber-800">
              Voice extraction reported: <strong className="underline">{voiceReportedLocation}</strong>. Body Map selected: <strong className="underline">{selectedLocations[0]?.formattedSummary}</strong>.
            </p>
            <p className="text-[10px] text-amber-700 italic">
              Both patient-reported locations are preserved for doctor review. You may adjust your selection anytime.
            </p>
          </div>
        </div>
      )}

      {/* Main Interactive Diagram & Controls */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">
        {/* SVG Interactive Body Representation (5 cols) */}
        <div className="md:col-span-5 bg-slate-50 border border-slate-200 rounded-2xl p-4 flex flex-col items-center justify-center min-h-[320px] relative">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2">
            {view === 'front' ? 'Anatomical Front View' : 'Anatomical Back View'}
          </span>

          {/* SVG Human Silhouette Graphic */}
          <div className="relative w-48 h-64 flex items-center justify-center">
            <svg viewBox="0 0 100 200" className="w-full h-full drop-shadow-md">
              {/* Body Outline Base */}
              <g fill="#e2e8f0" stroke="#cbd5e1" strokeWidth="1.5">
                {/* Head */}
                <circle cx="50" cy="22" r="14" />
                {/* Neck */}
                <rect x="44" y="36" width="12" height="10" rx="2" />
                {/* Torso / Upper Body */}
                <path d="M 28,46 L 72,46 L 68,110 L 32,110 Z" />
                {/* Left Arm */}
                <path d="M 26,46 L 14,95 L 22,98 L 30,52 Z" />
                {/* Right Arm */}
                <path d="M 74,46 L 86,95 L 78,98 L 70,52 Z" />
                {/* Left Leg */}
                <path d="M 34,110 L 30,185 L 42,185 L 47,110 Z" />
                {/* Right Leg */}
                <path d="M 66,110 L 70,185 L 58,185 L 53,110 Z" />
              </g>

              {/* Clickable Overlay Regions */}
              {view === 'front' ? (
                <>
                  {/* Head */}
                  <circle
                    cx="50" cy="22" r="13"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'head_face' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[0])}
                  />
                  {/* Neck */}
                  <rect
                    x="44" y="36" width="12" height="10" rx="2"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'neck' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[1])}
                  />
                  {/* Chest */}
                  <path
                    d="M 30,48 L 70,48 L 68,75 L 32,75 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'chest' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[2])}
                  />
                  {/* Abdomen */}
                  <path
                    d="M 32,76 L 68,76 L 67,98 L 33,98 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'abdomen' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[3])}
                  />
                  {/* Pelvis */}
                  <path
                    d="M 33,99 L 67,99 L 65,112 L 35,112 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'pelvis' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[4])}
                  />
                  {/* Left Arm */}
                  <path
                    d="M 26,46 L 14,95 L 22,98 L 30,52 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'arm_left' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[7])}
                  />
                  {/* Right Arm */}
                  <path
                    d="M 74,46 L 86,95 L 78,98 L 70,52 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'arm_right' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[8])}
                  />
                  {/* Left Leg */}
                  <path
                    d="M 34,110 L 30,185 L 42,185 L 47,110 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'leg_left' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[9])}
                  />
                  {/* Right Leg */}
                  <path
                    d="M 66,110 L 70,185 L 58,185 L 53,110 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'leg_right' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(FRONT_REGIONS[10])}
                  />
                </>
              ) : (
                <>
                  {/* Head Back */}
                  <circle
                    cx="50" cy="22" r="13"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'head_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[0])}
                  />
                  {/* Upper Back */}
                  <path
                    d="M 30,48 L 70,48 L 68,75 L 32,75 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'upper_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[2])}
                  />
                  {/* Lower Back */}
                  <path
                    d="M 32,76 L 68,76 L 67,98 L 33,98 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'lower_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[3])}
                  />
                  {/* Buttocks */}
                  <path
                    d="M 33,99 L 67,99 L 65,112 L 35,112 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'buttock' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[4])}
                  />
                  {/* Left Arm Back */}
                  <path
                    d="M 26,46 L 14,95 L 22,98 L 30,52 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'arm_left_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[7])}
                  />
                  {/* Right Arm Back */}
                  <path
                    d="M 74,46 L 86,95 L 78,98 L 70,52 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'arm_right_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[8])}
                  />
                  {/* Left Leg Back */}
                  <path
                    d="M 34,110 L 30,185 L 42,185 L 47,110 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'leg_left_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[9])}
                  />
                  {/* Right Leg Back */}
                  <path
                    d="M 66,110 L 70,185 L 58,185 L 53,110 Z"
                    className={`cursor-pointer transition-all ${selectedRegion?.id === 'leg_right_back' ? 'fill-sky-500 opacity-90' : 'fill-sky-500/20 hover:fill-sky-500/50'}`}
                    onClick={() => handleRegionClick(BACK_REGIONS[10])}
                  />
                </>
              )}
            </svg>
          </div>

          <p className="text-[11px] text-slate-500 mt-2 text-center">
            Tap any body area on the diagram or buttons to the right
          </p>
        </div>

        {/* Region Selector & Contextual Refinement Controls (7 cols) */}
        <div className="md:col-span-7 space-y-4">
          {/* Quick Buttons for Regions */}
          <div>
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-2">
              Select Body Region ({view.toUpperCase()})
            </label>
            <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-1">
              {activeRegions.map((reg) => {
                const isSelected = selectedRegion?.id === reg.id;
                return (
                  <button
                    key={reg.id}
                    onClick={() => handleRegionClick(reg)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                      isSelected
                        ? 'bg-sky-600 text-white font-bold shadow'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200'
                    }`}
                  >
                    <span>{reg.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Contextual Refinement Controls (Side & Depth) */}
          {selectedRegion ? (
            <div className="p-4 bg-sky-50/70 border border-sky-200 rounded-2xl space-y-3 animate-in fade-in duration-150">
              <div className="flex items-center justify-between border-b border-sky-200/80 pb-2">
                <span className="font-bold text-xs text-sky-950 flex items-center space-x-1.5">
                  <Info className="w-4 h-4 text-sky-600" />
                  <span>Refine Location for {selectedRegion.label}</span>
                </span>
                <button
                  onClick={() => setSelectedRegion(null)}
                  className="text-slate-400 hover:text-slate-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Side Selection */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-bold text-slate-700 block">
                  Where in the {selectedRegion.label} do you feel it?
                </span>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  {[
                    { id: 'left', label: 'Left' },
                    { id: 'center', label: 'Center' },
                    { id: 'right', label: 'Right' },
                  ].map((side) => (
                    <button
                      key={side.id}
                      onClick={() => setPendingSide(side.id)}
                      className={`py-2 px-2 rounded-xl text-xs font-bold transition-all border ${
                        pendingSide === side.id
                          ? 'bg-sky-600 text-white border-sky-700 shadow-sm'
                          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      {side.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Depth Selection */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-bold text-slate-700 block">
                  Does the symptom feel:
                </span>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  {[
                    { id: 'external', label: 'Outside / Skin' },
                    { id: 'internal', label: 'Inside / Deep' },
                    { id: 'not_sure', label: 'Not Sure' },
                  ].map((depth) => (
                    <button
                      key={depth.id}
                      onClick={() => setPendingDepth(depth.id)}
                      className={`py-2 px-2 rounded-xl text-[11px] font-bold transition-all border ${
                        pendingDepth === depth.id
                          ? 'bg-sky-600 text-white border-sky-700 shadow-sm'
                          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      {depth.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex justify-end pt-1">
                <button
                  onClick={handleAddLocation}
                  className="flex items-center space-x-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl shadow transition-all"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Confirm Location Selection</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-500 italic text-center">
              Tap any body area on the left diagram or buttons above to specify symptom location.
            </div>
          )}
        </div>
      </div>

      {/* Selected Locations List (Patient-Reported Locations) */}
      <div className="pt-3 border-t border-slate-100 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Patient-Reported Locations ({selectedLocations.length})</span>
          </span>
          {selectedLocations.length > 0 && (
            <button
              onClick={handleClearAll}
              className="text-[11px] text-red-600 hover:text-red-800 font-semibold flex items-center space-x-1"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Clear All</span>
            </button>
          )}
        </div>

        {selectedLocations.length === 0 ? (
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-400 italic text-center">
            No body map location selected yet. (Tap body diagram above to select location).
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {selectedLocations.map((loc) => (
              <div
                key={loc.id}
                className="flex items-center space-x-2 bg-emerald-50 border border-emerald-200 text-emerald-900 px-3 py-1.5 rounded-xl text-xs font-medium shadow-sm"
              >
                <span>{loc.formattedSummary}</span>
                <button
                  onClick={() => handleRemoveLocation(loc.id)}
                  className="text-emerald-700 hover:text-red-700 p-0.5 rounded transition-colors"
                  title="Remove location"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Clinical Disclaimer */}
        <p className="text-[10px] text-slate-400 italic pt-1">
          * Note: Selected body locations represent patient-reported location context only and do not infer specific organ diagnoses.
        </p>
      </div>
    </div>
  );
}
