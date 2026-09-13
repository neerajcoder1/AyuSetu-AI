import React from 'react';
import {
  LayoutDashboard,
  UserCheck,
  FileText,
  Layers,
  Clock,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
} from 'lucide-react';

export default function Sidebar({
  activeSection = 'overview',
  onSelectSection,
  onSwitchToPatientView,
  redFlagsCount = 0,
  documentsCount = 0,
  slotsElicitedCount = 0,
}) {
  const navItems = [
    {
      id: 'overview',
      label: 'Dashboard',
      icon: LayoutDashboard,
      badge: null,
    },
    {
      id: 'clinical-info',
      label: 'Clinical Information',
      icon: FileText,
      badge: slotsElicitedCount > 0 ? `${slotsElicitedCount}/12` : null,
      badgeColor: 'bg-teal-100 text-teal-800',
    },
    {
      id: 'documents',
      label: 'Patient Documents',
      icon: Layers,
      badge: documentsCount > 0 ? `${documentsCount}` : null,
      badgeColor: 'bg-sky-100 text-sky-800',
    },
    {
      id: 'timeline',
      label: 'Clinical Timeline',
      icon: Clock,
      badge: null,
    },
    {
      id: 'red-flags',
      label: 'Red Flags',
      icon: AlertTriangle,
      badge: redFlagsCount > 0 ? `${redFlagsCount}` : null,
      badgeColor: 'bg-rose-100 text-rose-700',
    },
    {
      id: 'summary',
      label: 'Clinical Summary',
      icon: Sparkles,
      badge: null,
    },
    {
      id: 'sign-off',
      label: 'Physician Review',
      icon: ShieldCheck,
      badge: null,
    },
  ];

  const handleNavClick = (id) => {
    if (onSelectSection) {
      onSelectSection(id);
    }
    const elem = document.getElementById(`section-${id}`);
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <aside className="w-64 bg-white border-r border-slate-200/90 flex flex-col shrink-0 h-screen sticky top-0 shadow-sm z-20 hidden md:flex">
      {/* Sidebar Section Header (Logo remains exclusively in global top-left header) */}
      <div className="p-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h2 className="font-extrabold text-xs text-slate-900 tracking-tight leading-none uppercase">
            Physician Cockpit
          </h2>
          <span className="text-[10px] text-teal-700 font-semibold block mt-1">
            Clinical Intake & Triage
          </span>
        </div>
        <span className="w-2 h-2 rounded-full bg-teal-500 shrink-0" />
      </div>

      {/* Navigation Links */}
      <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Physician Navigation
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeSection === item.id;
          return (
            <button
              key={item.id}
              onClick={() => handleNavClick(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-bold text-xs transition-all ${
                isActive
                  ? 'bg-sky-600 text-white shadow-md shadow-sky-600/20'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-500'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                    isActive ? 'bg-white/20 text-white' : item.badgeColor || 'bg-slate-100 text-slate-700'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Switch to Patient Consultation Footer CTA */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/50">
        <button
          onClick={onSwitchToPatientView}
          className="w-full flex items-center justify-center space-x-2 bg-white border border-slate-200 hover:border-sky-300 text-slate-800 font-bold text-xs py-2.5 px-3 rounded-xl shadow-sm transition-all hover:bg-sky-50/60"
        >
          <UserCheck className="w-4 h-4 text-sky-600" />
          <span>Patient Consultation</span>
        </button>
      </div>
    </aside>
  );
}
