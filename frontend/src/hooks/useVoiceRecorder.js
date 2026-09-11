import { useState, useRef, useCallback, useEffect } from 'react';

export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [error, setError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerRef = useRef(null);
  const animFrameRef = useRef(null);
  const audioContextRef = useRef(null);

  const startRecording = useCallback(async () => {
    setError(null);
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingTime(0);
    audioChunksRef.current = [];

    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    const isHostnameIp = /^(?:\d{1,3}\.){3}\d{1,3}$/.test(hostname);
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
    const isSecureContext = window.isSecureContext || protocol === 'https:' || isLocalhost;

    // 1. Check for insecure context (e.g. accessing via LAN IP over HTTP)
    if (!isSecureContext || (isHostnameIp && protocol !== 'https:')) {
      setError(
        `Microphone access requires a secure context (HTTPS or localhost). ` +
        `If you are accessing via LAN IP (${hostname}), please open http://localhost:5173 instead.`
      );
      return;
    }

    // 2. Check for navigator.mediaDevices support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (isHostnameIp && protocol !== 'https:') {
        setError(
          `Microphone API is disabled when accessing via IP (${hostname}). Please open http://localhost:5173 instead.`
        );
      } else {
        setError(
          'Microphone recording (navigator.mediaDevices.getUserMedia) is not supported in this browser context.'
        );
      }
      return;
    }

    // 3. Check for MediaRecorder API support
    if (typeof window.MediaRecorder === 'undefined') {
      setError(
        'MediaRecorder API is not supported in this browser. Please try Chrome, Edge, or Firefox.'
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Setup AudioContext for volume meter
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
          const audioCtx = new AudioContext();
          audioContextRef.current = audioCtx;
          const source = audioCtx.createMediaStreamSource(stream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 256;
          source.connect(analyser);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);
          const updateVolume = () => {
            analyser.getByteFrequencyData(dataArray);
            const sum = dataArray.reduce((acc, val) => acc + val, 0);
            const avg = sum / dataArray.length;
            setVolumeLevel(Math.min(100, Math.round((avg / 128) * 100)));
            animFrameRef.current = requestAnimationFrame(updateVolume);
          };
          updateVolume();
        }
      } catch (err) {
        console.warn('AudioContext volume metering non-critical error:', err);
      }

      let mimeType = 'audio/webm';
      if (MediaRecorder.isTypeSupported('audio/wav')) {
        mimeType = 'audio/wav';
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        mimeType = 'audio/mp4';
      } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
        mimeType = 'audio/ogg';
      }

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        setAudioBlob(blob);
        setAudioUrl(url);

        // Stop all tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(200); // 200ms timeslice
      setIsRecording(true);

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error('Failed to access microphone:', err);
      const errName = err.name || '';

      if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
        setError(
          'Microphone permission was denied. Please click the camera/lock icon in your browser address bar to allow microphone access for this site, then click Speak again.'
        );
      } else if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
        setError(
          'No microphone device was found. Please connect a working microphone to your system and try again.'
        );
      } else if (errName === 'NotReadableError' || errName === 'TrackStartError') {
        setError(
          'Microphone is currently in use by another application or hardware device.'
        );
      } else if (errName === 'SecurityError') {
        if (isHostnameIp && protocol !== 'https:') {
          setError(
            `Microphone access blocked over HTTP IP (${hostname}). Please open http://localhost:5173 instead.`
          );
        } else {
          setError('Microphone access restricted due to browser security settings.');
        }
      } else {
        setError(err.message || 'Unable to access microphone. Please check browser permissions and settings.');
      }
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
    }
    setIsRecording(false);
    setVolumeLevel(0);
  }, []);

  const clearAudio = useCallback(() => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingTime(0);
    setVolumeLevel(0);
  }, [audioUrl]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  return {
    isRecording,
    audioBlob,
    audioUrl,
    recordingTime,
    volumeLevel,
    error,
    startRecording,
    stopRecording,
    clearAudio,
  };
}
