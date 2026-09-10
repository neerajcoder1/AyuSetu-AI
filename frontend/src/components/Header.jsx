import React from 'react';
import { Activity, Stethoscope, User, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function Header({
  activeTab,
  setActiveTab,
  sessionId,
  onNewSession,
  isConnected,
  isCreatingSession,
}) {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Name */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-medical-600 to-sky-400 flex items-center justify-center text-white shadow-md shadow-sky-500/20">
              <Activity className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-xl text-slate-900 tracking-tight">AyuSetu AI</span>
                <span className="bg-sky-100 text-sky-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                  v2.0 Clinical
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">Session-Scoped Intake & Cockpit</p>
            </div>
          </div>

          {/* Navigation View Switcher */}
          <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setActiveTab('patient')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg font-medium text-xs sm:text-sm transition-all duration-150 ${
                activeTab === 'patient'
                  ? 'bg-white text-medical-700 shadow-sm font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
              }`}
            >
              <User className="w-4 h-4" />
              <span>Patient Voice Intake</span>
            </button>

            <button
              onClick={() => setActiveTab('doctor')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg font-medium text-xs sm:text-sm transition-all duration-150 ${
                activeTab === 'doctor'
                  ? 'bg-white text-medical-700 shadow-sm font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
              }`}
            >
              <Stethoscope className="w-4 h-4" />
              <span>Doctor Cockpit</span>
            </button>
          </div>

          {/* Session Info & Backend Connectivity */}
          <div className="flex items-center space-x-3">
            {/* Status indicator */}
            <div className="hidden md:flex items-center space-x-1.5 px-2 py-1 rounded-md bg-slate-50 border border-slate-200 text-xs font-medium">
              {isConnected ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-slate-600">FastAPI Ready</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                  <span className="text-slate-600">Connecting...</span>
                </>
              )}
            </div>

            {/* Session ID Pill */}
            {sessionId ? (
              <div className="flex items-center space-x-2 bg-sky-50 border border-sky-200 rounded-lg px-2.5 py-1">
                <div className="flex flex-col">
                  <span className="text-[10px] text-sky-600 uppercase tracking-wider font-semibold">Session ID</span>
                  <span className="font-mono text-xs text-sky-900 font-bold max-w-[100px] sm:max-w-[140px] truncate">
                    {sessionId}
                  </span>
                </div>
                <button
                  onClick={onNewSession}
                  disabled={isCreatingSession}
                  title="Create New Session"
                  className="p-1 rounded-md text-sky-700 hover:bg-sky-100 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isCreatingSession ? 'animate-spin' : ''}`} />
                </button>
              </div>
            ) : (
              <button
                onClick={onNewSession}
                disabled={isCreatingSession}
                className="bg-medical-600 hover:bg-medical-700 text-white font-medium text-xs px-3 py-1.5 rounded-lg shadow-sm transition-all"
              >
                {isCreatingSession ? 'Creating...' : 'Start Session'}
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
