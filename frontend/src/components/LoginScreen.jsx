import React, { useState, useEffect } from 'react';
import {
  Activity,
  User,
  Stethoscope,
  ArrowRight,
  ShieldCheck,
  Globe,
  CheckCircle2,
  AlertCircle,
  FileText,
  Clock,
  Layers,
  Sparkles,
  PhoneCall,
} from 'lucide-react';
import { api } from '../services/api';

export default function LoginScreen({
  onLoginSuccess,
  preferredLanguage = 'hinglish',
  onLanguageChange,
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

  const handlePatientLogin = () => {
    if (onLoginSuccess) {
      onLoginSuccess({
        role: 'patient',
        displayName: 'Demo Patient',
        id: 'patient_demo',
        authType: 'prototype_demo',
      });
    }
  };

  const handlePhysicianLogin = () => {
    if (onLoginSuccess) {
      onLoginSuccess({
        role: 'physician',
        displayName: 'Demo Physician',
        id: 'physician_demo',
        authType: 'prototype_demo',
      });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">
      {/* Global Header Bar */}
      <header className="bg-white border-b border-slate-200/90 sticky top-0 z-20 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Left: Product Brand Identity */}
            <div className="flex items-center space-x-3">
              <img
                src="/branding/ayusetu-logo-primary.png"
                alt="AyuSetu AI"
                className="h-10 sm:h-11 w-auto object-contain"
              />
              <span className="hidden sm:inline-block bg-teal-50 text-teal-800 border border-teal-200/80 text-[10px] font-extrabold px-2.5 py-0.5 rounded-full">
                Clinical Case-Taking Platform
              </span>
            </div>

            {/* Right: Real API GET /health status, Language dropdown & Environment tag */}
            <div className="flex items-center space-x-3">
              {/* Real API Status Indicator */}
              <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-slate-50 border border-slate-200 text-xs font-semibold">
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

              {/* Language Selector */}
              <div className="flex items-center space-x-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
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

              {/* Prototype Environment Tag */}
              <span className="bg-slate-100 text-slate-600 border border-slate-200 text-[10px] font-semibold px-2.5 py-1 rounded-xl hidden lg:inline">
                Prototype environment
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-8">
        {/* Two-Column Hero Section */}
        <section className="bg-white border border-slate-200/90 rounded-3xl p-6 sm:p-8 shadow-sm grid grid-cols-1 lg:grid-cols-11 gap-8 items-center">
          {/* Left Column: Introduction & Feature Indicators (6 cols ~ 55%) */}
          <div className="lg:col-span-6 space-y-5">
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-500">
                <span>AyuSetu AI</span>
                <span>/</span>
                <span className="text-sky-700 font-bold">Clinical Portal Access</span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
                Welcome to AyuSetu AI
              </h1>
              <p className="text-sm sm:text-base font-bold text-slate-600">
                Bridging people, care and better outcomes.
              </p>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed max-w-2xl font-normal pt-1">
                Choose your clinical workflow to begin. AyuSetu AI helps capture meaningful clinical information through natural conversation, with physician oversight.
              </p>
            </div>

            {/* Three Compact Feature Indicators */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-100">
              <div className="flex items-center space-x-2.5 p-2.5 bg-slate-50 rounded-xl border border-slate-200/80">
                <div className="p-2 bg-sky-100 text-sky-700 rounded-lg shrink-0">
                  <PhoneCall className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-bold text-xs text-slate-900 block leading-snug">Voice-first consultation</span>
                  <span className="text-[10px] text-slate-500 block leading-snug">Speak naturally in your language</span>
                </div>
              </div>

              <div className="flex items-center space-x-2.5 p-2.5 bg-slate-50 rounded-xl border border-slate-200/80">
                <div className="p-2 bg-teal-100 text-teal-700 rounded-lg shrink-0">
                  <FileText className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-bold text-xs text-slate-900 block leading-snug">Document understanding</span>
                  <span className="text-[10px] text-slate-500 block leading-snug">Upload supporting medical reports</span>
                </div>
              </div>

              <div className="flex items-center space-x-2.5 p-2.5 bg-slate-50 rounded-xl border border-slate-200/80">
                <div className="p-2 bg-emerald-100 text-emerald-700 rounded-lg shrink-0">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-bold text-xs text-slate-900 block leading-snug">Physician review & sign-off</span>
                  <span className="text-[10px] text-slate-500 block leading-snug">Always under physician oversight</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Clean, Independent Doctor-Patient Consultation Hero Visual (5 cols ~ 45%) */}
          <div className="lg:col-span-5">
            <div className="rounded-2xl overflow-hidden border border-slate-200/90 shadow-sm bg-slate-100 aspect-[4/3] w-full">
              <img
                src="/assets/doctor-patient-consultation.png"
                alt="Doctor consulting with a patient using AyuSetu AI"
                className="w-full h-full object-cover"
              />
            </div>
          </div>
        </section>

        {/* Workflow Selection Panels */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Panel 1: Patient Consultation */}
          <div className="bg-white border border-slate-200 rounded-3xl p-6 sm:p-7 shadow-sm hover:border-sky-300 transition-all flex flex-col justify-between space-y-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="p-3 bg-sky-50 text-sky-700 rounded-xl border border-sky-100">
                  <User className="w-6 h-6" />
                </div>
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-sky-800 bg-sky-50 border border-sky-200 px-3 py-1 rounded-full">
                  VOICE-FIRST PATIENT INTAKE
                </span>
              </div>

              <div className="space-y-1.5">
                <h2 className="text-xl font-extrabold text-slate-900">Patient Consultation</h2>
                <p className="text-xs text-slate-600 leading-relaxed font-normal">
                  Start a voice-first clinical consultation, describe your symptoms naturally, identify approximate pain locations, and upload supporting medical documents.
                </p>
              </div>

              {/* Checklist Items */}
              <div className="pt-3 border-t border-slate-100 space-y-2.5 text-xs text-slate-700 font-medium">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-sky-600 shrink-0" />
                  <span>Multimodal voice consultation in preferred language</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-sky-600 shrink-0" />
                  <span>Interactive symptom & pain location mapping</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-sky-600 shrink-0" />
                  <span>Medical document upload & automated OCR</span>
                </div>
              </div>
            </div>

            <button
              onClick={handlePatientLogin}
              className="w-full py-3.5 bg-sky-600 hover:bg-sky-700 text-white font-extrabold text-xs sm:text-sm rounded-xl shadow-sm transition-all flex items-center justify-center space-x-2"
            >
              <span>Start Consultation</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Panel 2: Physician Cockpit */}
          <div className="bg-white border border-slate-200 rounded-3xl p-6 sm:p-7 shadow-sm hover:border-teal-300 transition-all flex flex-col justify-between space-y-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="p-3 bg-teal-50 text-teal-700 rounded-xl border border-teal-100">
                  <Stethoscope className="w-6 h-6" />
                </div>
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-teal-800 bg-teal-50 border border-teal-200 px-3 py-1 rounded-full">
                  CLINICAL REVIEW & SIGN-OFF
                </span>
              </div>

              <div className="space-y-1.5">
                <h2 className="text-xl font-extrabold text-slate-900">Physician Cockpit</h2>
                <p className="text-xs text-slate-600 leading-relaxed font-normal">
                  Review elicited clinical information, red-flag alerts, patient documents, clinical timeline, and AI-generated clinical summaries.
                </p>
              </div>

              {/* Checklist Items */}
              <div className="pt-3 border-t border-slate-100 space-y-2.5 text-xs text-slate-700 font-medium">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Real-time 12-slot clinical memory triage</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Safety triage alerts & longitudinal patient timeline</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Evidence-grounded summary review, edit & sign-off</span>
                </div>
              </div>
            </div>

            <button
              onClick={handlePhysicianLogin}
              className="w-full py-3.5 bg-teal-600 hover:bg-teal-700 text-white font-extrabold text-xs sm:text-sm rounded-xl shadow-sm transition-all flex items-center justify-center space-x-2"
            >
              <span>Open Physician Cockpit</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </section>

        {/* Clinical Safety Disclaimer Footer */}
        <footer className="pt-6 border-t border-slate-200/80 text-center space-y-1 text-xs text-slate-500">
          <p className="max-w-4xl mx-auto leading-relaxed">
            🛡 <strong className="font-semibold text-slate-700">Clinical Responsibility Notice:</strong> AyuSetu AI assists with clinical case-taking and triage. It does not autonomously diagnose or prescribe. The physician remains the final clinical decision-maker. | <span className="font-semibold text-slate-600">Built for a healthier India</span>
          </p>
          <p className="text-[11px] text-slate-400 font-medium">
            AyuSetu AI SIH 2026 • Problem Statement SIH26047
          </p>
        </footer>
      </main>
    </div>
  );
}
