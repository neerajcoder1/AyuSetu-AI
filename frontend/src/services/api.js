const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function handleResponse(response) {
  if (!response.ok) {
    let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        errorMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errorMsg);
  }
  if (response.status === 204) {
    return null;
  }
  return await response.json();
}

export const api = {
  // Create session
  async createSession() {
    const res = await fetch(`${API_BASE_URL}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse(res);
  },

  // Send turn with audio file (Blob or File)
  async sendTurn(sessionId, audioBlob, filename = 'voice_turn.wav') {
    const formData = new FormData();
    formData.append('audio', audioBlob, filename);

    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/turn`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse(res);
  },

  // Get session dialogue state
  async getSessionState(sessionId) {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/state`, {
      method: 'GET',
    });
    return handleResponse(res);
  },

  // Delete session
  async deleteSession(sessionId) {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return handleResponse(res);
  },

  // Upload document for OCR entity extraction
  async uploadDocument(sessionId, file) {
    const formData = new FormData();
    formData.append('document', file);

    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/documents`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse(res);
  },

  // Generate evidence-grounded summary
  async generateSummary(sessionId) {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/summary`, {
      method: 'POST',
    });
    return handleResponse(res);
  },

  // Physician Sign-off
  async signOffSummary(sessionId, physicianId = 'DR-9942') {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/summary/sign-off`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ physician_id: physicianId }),
    });
    return handleResponse(res);
  },

  // Physician Edit slot
  async editSummary(sessionId, slotPath, newValue, reason, physicianId = 'DR-9942') {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/summary/edit`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slot_path: slotPath,
        new_value: newValue,
        reason: reason,
        physician_id: physicianId,
      }),
    });
    return handleResponse(res);
  },

  // Physician Reject summary
  async rejectSummary(sessionId, reason, detail = '', physicianId = 'DR-9942') {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/summary/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reason: reason,
        physician_id: physicianId,
        detail: detail,
      }),
    });
    return handleResponse(res);
  },

  // Get patient timeline events
  async getTimeline(sessionId) {
    const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/timeline`, {
      method: 'GET',
    });
    return handleResponse(res);
  },
};
