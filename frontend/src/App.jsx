import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import PatientInterviewScreen from './pages/PatientInterviewScreen';
import DoctorDashboardScreen from './pages/DoctorDashboardScreen';
import { api } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('patient');
  const [sessionId, setSessionId] = useState(null);
  const [preferredLanguage, setPreferredLanguage] = useState('hinglish');
  const [dialogueState, setDialogueState] = useState(null);
  const [redFlags, setRedFlags] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);

  // Initialize new session
  const initSession = useCallback(async (lang = preferredLanguage) => {
    setIsCreatingSession(true);
    try {
      const res = await api.createSession(lang);
      setSessionId(res.session_id);
      setIsConnected(true);
      // Fetch initial empty dialogue state
      const stateRes = await api.getSessionState(res.session_id);
      setDialogueState(stateRes.state || null);
      setRedFlags([]);
    } catch (err) {
      console.error('Failed to create session:', err);
      setIsConnected(false);
    } finally {
      setIsCreatingSession(false);
    }
  }, [preferredLanguage]);

  useEffect(() => {
    initSession();
  }, [initSession]);

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

  // Refresh current session state
  const refreshSessionState = async () => {
    if (!sessionId) return;
    try {
      const res = await api.getSessionState(sessionId);
      setDialogueState(stateRes => {
        const fresh = res.state || null;
        if (fresh && fresh.preferred_language) {
          setPreferredLanguage(fresh.preferred_language);
        }
        return fresh;
      });
      setIsConnected(true);
    } catch (err) {
      console.error('Failed to refresh state:', err);
    }
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

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Global Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        sessionId={sessionId}
        onNewSession={initSession}
        isConnected={isConnected}
        isCreatingSession={isCreatingSession}
        preferredLanguage={preferredLanguage}
        onLanguageChange={handleLanguageChange}
      />

      {/* Screen Views */}
      <main className="flex-1">
        {activeTab === 'patient' ? (
          <PatientInterviewScreen
            sessionId={sessionId}
            dialogueState={dialogueState}
            preferredLanguage={preferredLanguage}
            onLanguageChange={handleLanguageChange}
            onTurnCompleted={handleTurnCompleted}
            onGoToDoctorDashboard={() => setActiveTab('doctor')}
          />
        ) : (
          <DoctorDashboardScreen
            sessionId={sessionId}
            dialogueState={dialogueState}
            redFlags={redFlags}
            onRefreshSessionState={refreshSessionState}
          />
        )}
      </main>
    </div>
  );
}
