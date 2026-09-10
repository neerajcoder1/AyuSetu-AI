import React, { useEffect, useState } from 'react';
import { History, Calendar, FileText, AlertTriangle, MessageSquare, RefreshCw } from 'lucide-react';
import { api } from '../services/api';

export default function ClinicalTimelineWidget({ sessionId, refreshTrigger }) {
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTimeline = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getTimeline(sessionId);
      setTimelineEvents(res || []);
    } catch (err) {
      console.error('Failed to load timeline:', err);
      setError(err.message || 'Failed to load timeline');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTimeline();
  }, [sessionId, refreshTrigger]);

  const getEventBadge = (type) => {
    switch (type) {
      case 'encounter':
        return { label: 'Encounter', bg: 'bg-blue-100 text-blue-800 border-blue-200' };
      case 'red_flag':
        return { label: 'Red Flag', bg: 'bg-rose-100 text-rose-800 border-rose-200' };
      case 'medication':
        return { label: 'Medication', bg: 'bg-purple-100 text-purple-800 border-purple-200' };
      case 'diagnosis':
      case 'lab_result':
      case 'vital_sign':
        return { label: type.replace('_', ' '), bg: 'bg-sky-100 text-sky-800 border-sky-200' };
      default:
        return { label: type.replace('_', ' '), bg: 'bg-slate-100 text-slate-700 border-slate-200' };
    }
  };

  const getSourceIcon = (source) => {
    if (source === 'utterance') return <MessageSquare className="w-3 h-3 text-emerald-600" />;
    if (source === 'document') return <FileText className="w-3 h-3 text-sky-600" />;
    return <Calendar className="w-3 h-3 text-slate-400" />;
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <History className="w-4 h-4 text-medical-600" />
          <h3 className="font-semibold text-slate-900 text-sm sm:text-base">
            Longitudinal Patient Timeline
          </h3>
        </div>
        <button
          onClick={fetchTimeline}
          disabled={isLoading}
          className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 text-red-700 text-xs rounded-xl mb-3">
          {error}
        </div>
      )}

      {timelineEvents.length === 0 ? (
        <div className="text-center py-6 text-slate-400 text-xs italic bg-slate-50 rounded-xl">
          No timeline events recorded for this encounter session yet.
        </div>
      ) : (
        <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
          {timelineEvents.map((evt, idx) => {
            const badge = getEventBadge(evt.event_type);
            return (
              <div key={idx} className="relative group">
                {/* Timeline node icon */}
                <div className="absolute -left-6 top-1 w-3.5 h-3.5 rounded-full bg-white border-2 border-medical-500 group-hover:scale-125 transition-transform" />

                <div className="bg-slate-50 hover:bg-slate-100/80 border border-slate-200/80 rounded-xl p-3 text-xs transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-slate-900">{evt.title}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                      {badge.label}
                    </span>
                  </div>

                  <p className="text-slate-600 mb-2 font-medium">{evt.detail}</p>

                  <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1.5 border-t border-slate-200/60">
                    <div className="flex items-center space-x-1">
                      {getSourceIcon(evt.source)}
                      <span className="capitalize">{evt.source} ({evt.source_ref || 'session'})</span>
                    </div>
                    <span>Conf: {(evt.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
