import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import LoginScreen from './components/LoginScreen';
import PatientInterviewScreen from './pages/PatientInterviewScreen';
import DoctorDashboardScreen from './pages/DoctorDashboardScreen';
import { api } from './services/api';

// Note: Prototype role state only — not production authentication.
const AUTH_STORAGE_KEY = 'ayusetu_prototype_user_auth';

export default function App() {
  // Prototype user authentication state
  const [userAuth, setUserAuth] = useState(() => {
    try {
      const stored = sessionStorage.getItem(AUTH_STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const [activeTab, setActiveTab] = useState('patient');
  const [activeSection, setActiveSection] = useState('overview');
  const [sessionId, setSessionId] = useState(null);
  const [preferredLanguage, setPreferredLanguage] = useState('hinglish');
  const [dialogueState, setDialogueState] = useState(null);
  const [redFlags, setRedFlags] = useState([]);
  const [sessionDocuments, setSessionDocuments] = useState([]);
  const [isCreatingSession, setIsCreatingSession] = useState(false);

  // Sync activeTab with userRole when auth state changes
  useEffect(() => {
    if (userAuth) {
      if (userAuth.role === 'patient') {
        setActiveTab('patient');
      } else if (userAuth.role === 'physician') {
        setActiveTab('doctor');
      }
    }
  }, [userAuth]);

  // Initialize new session
  const initSession = useCallback(async (lang = preferredLanguage) => {
    setIsCreatingSession(true);
    try {
      const res = await api.createSession(lang);
      setSessionId(res.session_id);
      const stateRes = await api.getSessionState(res.session_id);
      setDialogueState(stateRes.state || null);
      setRedFlags([]);
      setSessionDocuments([]);
    } catch (err) {
      console.error('Failed to create session:', err);
    } finally {
      setIsCreatingSession(false);
    }
  }, [preferredLanguage]);

  useEffect(() => {
    if (userAuth) {
      initSession();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userAuth]);

  const handleLoginSuccess = (authData) => {
    // Note: Prototype role state only — not production authentication.
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authData));
    setUserAuth(authData);
  };

  const handleLogout = () => {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    setUserAuth(null);
    setActiveTab('patient');
  };

  const handleLanguageChange = async (newLang) => {
    setPreferredLanguage(newLang);
    if (sessionId) {
      try {
        await api.updateSessionLanguage(sessionId, newLang);
        refreshSessionState();
      } catch (err) {
        console.error('Failed to update language:', err);
      }
    }
  };

  // Refresh current session state from backend
  const refreshSessionState = async () => {
    if (!sessionId) return;
    try {
      const res = await api.getSessionState(sessionId);
      setDialogueState((prev) => {
        const fresh = res.state || null;
        if (fresh && fresh.preferred_language) {
          setPreferredLanguage(fresh.preferred_language);
        }
        return fresh;
      });
    } catch (err) {
      console.error('Failed to refresh state:', err);
    }
  };

  const handleDocumentProcessed = (docRes) => {
    if (docRes) {
      setSessionDocuments((prev) => [...prev, docRes]);
    }
    refreshSessionState();
  };

  // Called after a voice turn finishes
  const handleTurnCompleted = (turnResponse) => {
    if (turnResponse.preferred_language) {
      setPreferredLanguage(turnResponse.preferred_language);
    }
    if (turnResponse.red_flags && turnResponse.red_flags.length > 0) {
      setRedFlags((prev) => {
        const existingIds = new Set(prev.map((rf) => rf.rule_id));
        const newFlags = turnResponse.red_flags.filter((rf) => !existingIds.has(rf.rule_id));
        return [...prev, ...newFlags];
      });
    }
    refreshSessionState();
  };

  // Render LoginScreen if unauthenticated
  if (!userAuth) {
    return (
      <LoginScreen
        onLoginSuccess={handleLoginSuccess}
        preferredLanguage={preferredLanguage}
        onLanguageChange={handleLanguageChange}
      />
    );
  }

  const collectedInfo = dialogueState?.collected_info || {};
  const slotsElicitedCount = Object.keys(collectedInfo).length;
  const isPatientRole = userAuth.role === 'patient';
  const isPhysicianRole = userAuth.role === 'physician';

  // Role separation safeguard: Patient role CANNOT view doctor tab
  const currentTab = isPatientRole ? 'patient' : activeTab;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Global Header Bar */}
      <Header
        activeTab={currentTab}
        setActiveTab={isPatientRole ? () => {} : setActiveTab}
        sessionId={sessionId}
        onNewSession={initSession}
        isCreatingSession={isCreatingSession}
        preferredLanguage={preferredLanguage}
        onLanguageChange={handleLanguageChange}
        userAuth={userAuth}
        onLogout={handleLogout}
      />

      {/* Main Screen Layout Container */}
      <div className="flex flex-1">
        {/* Sidebar rendered ONLY in Doctor Dashboard view for Physician role */}
        {currentTab === 'doctor' && isPhysicianRole && (
          <Sidebar
            activeSection={activeSection}
            onSelectSection={setActiveSection}
            onSwitchToPatientView={() => setActiveTab('patient')}
            redFlagsCount={redFlags.length}
            documentsCount={sessionDocuments.length}
            slotsElicitedCount={slotsElicitedCount}
          />
        )}

        {/* Dynamic View Body */}
        <main className="flex-1 overflow-x-hidden">
          {currentTab === 'patient' ? (
            <PatientInterviewScreen
              sessionId={sessionId}
              dialogueState={dialogueState}
              preferredLanguage={preferredLanguage}
              onLanguageChange={handleLanguageChange}
              onTurnCompleted={handleTurnCompleted}
              onGoToDoctorDashboard={isPhysicianRole ? () => setActiveTab('doctor') : null}
              sessionDocuments={sessionDocuments}
              onDocumentProcessed={handleDocumentProcessed}
            />
          ) : (
            <DoctorDashboardScreen
              sessionId={sessionId}
              dialogueState={dialogueState}
              redFlags={redFlags}
              onRefreshSessionState={refreshSessionState}
              sessionDocuments={sessionDocuments}
              onDocumentProcessed={handleDocumentProcessed}
              activeSection={activeSection}
            />
          )}
        </main>
      </div>
    </div>
  );
}
