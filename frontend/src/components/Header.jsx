import React, { useState, useEffect } from 'react';
import { Activity, Stethoscope, User, RefreshCw, Globe, LogOut, Lock } from 'lucide-react';
import { api } from '../services/api';

export default function Header({
  activeTab,
  setActiveTab,
  sessionId,
  onNewSession,
  isCreatingSession,
  preferredLanguage = 'hinglish',
  onLanguageChange,
  userAuth,
  onLogout,
}) {
  const [apiHealth, setApiHealth] = useState('checking'); // 'checking' | 'ready' | 'error'

  useEffect(() => {
    let isMounted = true;
    const checkBackendHealth = async () => {
      try {
        await api.checkHealth();
        if (isMounted) setApiHealth('ready');
      } catch (err) {
        if (isMounted) setApiHealth('error');
      }
    };

    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const isPatientRole = userAuth?.role === 'patient';
  const isPhysicianRole = userAuth?.role === 'physician';

  return (
    <header className="bg-white/95 backdrop-blur-md border-b border-slate-200/80 sticky top-0 z-30 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Official AyuSetu AI Brand Identity */}
          <div className="flex items-center space-x-3">
            <img
              src="/branding/ayusetu-logo-primary.png"
              alt="AyuSetu AI"
              className="h-10 sm:h-11 w-auto object-contain"
            />
            <span className="hidden lg:inline-block bg-teal-50 text-teal-800 border border-teal-200/80 text-[10px] font-extrabold px-2.5 py-0.5 rounded-full">
              Clinical Case-Taking Platform
            </span>
          </div>

          {/* Navigation View Switcher (Role Scoped) */}
          <div className="flex items-center space-x-1 bg-slate-100/90 p-1 rounded-xl border border-slate-200/90 shadow-inner">
            <button
              onClick={() => setActiveTab('patient')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg font-semibold text-xs sm:text-sm transition-all duration-150 ${
                activeTab === 'patient'
                  ? 'bg-white text-sky-800 shadow-sm font-bold border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              <User className="w-4 h-4 text-sky-600" />
              <span>Patient Consultation</span>
            </button>

            {/* Physician View Switcher button rendered ONLY for Physician Role */}
            {!isPatientRole && (
              <button
                onClick={() => setActiveTab('doctor')}
                className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg font-semibold text-xs sm:text-sm transition-all duration-150 ${
                  activeTab === 'doctor'
                    ? 'bg-white text-sky-800 shadow-sm font-bold border border-slate-200/60'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                }`}
              >
                <Stethoscope className="w-4 h-4 text-sky-600" />
                <span>Physician Cockpit</span>
              </button>
            )}
          </div>

          {/* Session Info, Role Profile & Logout */}
          <div className="flex items-center space-x-3">
            {/* Real API Health Indicator */}
            <div className="hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-slate-50 border border-slate-200 text-xs font-semibold">
              {apiHealth === 'ready' && (
                <>
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-slate-700">API Ready</span>
                </>
              )}
              {apiHealth === 'error' && (
                <>
                  <span className="w-2 h-2 rounded-full bg-rose-500" />
                  <span className="text-slate-700">API Offline</span>
                </>
              )}
              {apiHealth === 'checking' && (
                <>
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  <span className="text-slate-700">Checking...</span>
                </>
              )}
            </div>

            {/* User Profile Pill */}
            {userAuth && (
              <div className="flex items-center space-x-2 bg-slate-100 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
                {isPhysicianRole ? (
                  <Stethoscope className="w-3.5 h-3.5 text-teal-600" />
                ) : (
                  <User className="w-3.5 h-3.5 text-sky-600" />
                )}
                <div className="flex flex-col">
                  <span className="font-bold text-slate-800 text-[11px] leading-none">
                    {userAuth.displayName || (isPhysicianRole ? 'Demo Physician' : 'Demo Patient')}
                  </span>
                  <span className="text-[9px] text-slate-500 font-semibold uppercase tracking-wider">
                    Prototype Demo
                  </span>
                </div>
              </div>
            )}

            {/* Preferred Language Selector (Global Application Setting) */}
            <div className="flex items-center space-x-1.5 bg-slate-50 border border-slate-200/90 rounded-xl px-2.5 py-1 text-xs">
              <Globe className="w-3.5 h-3.5 text-sky-600 shrink-0" />
              <select
                value={preferredLanguage}
                onChange={(e) => onLanguageChange && onLanguageChange(e.target.value)}
                className="bg-transparent font-bold text-slate-800 text-xs focus:outline-none cursor-pointer"
              >
                <option value="hi">Hindi (हिन्दी)</option>
                <option value="hinglish">Hinglish</option>
                <option value="en">English</option>
              </select>
            </div>

            {/* Session ID Badge */}
            {sessionId && (
              <div className="hidden md:flex items-center space-x-2 bg-teal-50/70 border border-teal-200/80 rounded-xl px-2.5 py-1">
                <div className="flex flex-col">
                  <span className="text-[9px] text-teal-700 uppercase tracking-wider font-bold">Session</span>
                  <span className="font-mono text-xs text-teal-950 font-bold max-w-[80px] truncate">
                    {sessionId}
                  </span>
                </div>
                <button
                  onClick={() => onNewSession && onNewSession(preferredLanguage)}
                  disabled={isCreatingSession}
                  title="Create New Session"
                  className="p-1 rounded-lg text-teal-700 hover:bg-teal-100 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isCreatingSession ? 'animate-spin' : ''}`} />
                </button>
              </div>
            )}

            {/* Logout Button */}
            {userAuth && (
              <button
                onClick={onLogout}
                title="Logout / Switch Role"
                className="flex items-center space-x-1 bg-slate-100 hover:bg-rose-50 text-slate-700 hover:text-rose-700 border border-slate-200 hover:border-rose-200 font-bold text-xs px-2.5 py-1.5 rounded-xl transition-all"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
