import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, History, Search, ShieldCheck } from '../../icons/index.jsx';

function NavTab({ active, onClick, icon: Icon, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 sm:px-3 h-full border-b-2 text-[12.5px] whitespace-nowrap transition-colors cursor-pointer ${
        active ? 'nav-tab-active' : 'nav-tab-inactive'
      }`}
    >
      <Icon className={`w-4 h-4 ${active ? 'text-red-600' : 'text-slate-500'}`} />
      {children}
    </button>
  );
}

/**
 * Primary tab bar. `adminEntries` is already filtered by the caller's
 * permissions; hiding an entry here is cosmetic, the server re-checks.
 */
export default function AppNavigation({ currentNav, onNavigate, historyCount, adminEntries }) {
  const [adminOpen, setAdminOpen] = useState(false);
  const adminRef = useRef(null);
  const adminActive = adminEntries.some((entry) => entry.nav === currentNav);

  useEffect(() => {
    if (!adminOpen) return undefined;
    const close = (event) => {
      if (adminRef.current && !adminRef.current.contains(event.target)) setAdminOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [adminOpen]);

  return (
    <nav className="flex-none bg-white border-b border-slate-200 shadow-sm z-20 select-none">
      <div className="max-w-[1480px] mx-auto px-2 sm:px-4 lg:px-6 h-[38px] flex items-center justify-between gap-2">
        <div className="flex items-center h-full min-w-0 overflow-x-auto">
          <NavTab active={currentNav === 'search'} onClick={() => onNavigate('search')} icon={Search}>
            <span>Tra cứu</span>
          </NavTab>
          <NavTab active={currentNav === 'history'} onClick={() => onNavigate('history')} icon={History}>
            <span>Lịch sử</span>
            <span className="ml-0.5 px-1.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">{historyCount}</span>
          </NavTab>
        </div>

        {adminEntries.length > 0 && (
          <div className="relative h-full flex-shrink-0" ref={adminRef}>
            <button
              type="button"
              onClick={() => setAdminOpen((value) => !value)}
              className={`inline-flex items-center gap-1.5 px-2.5 sm:px-3 h-full border-b-2 text-[12.5px] whitespace-nowrap transition-colors cursor-pointer ${
                adminActive ? 'nav-tab-active' : 'nav-tab-inactive'
              }`}
            >
              <ShieldCheck className={`w-4 h-4 ${adminActive ? 'text-red-600' : 'text-slate-500'}`} />
              <span>Quản trị</span>
              <ChevronDown className="w-4 h-4" />
            </button>
            {adminOpen && (
              <div className="absolute right-0 top-full mt-px w-56 bg-white rounded-md border border-slate-200 shadow-xl py-1 z-50">
                {adminEntries.map((entry) => (
                  <button
                    key={entry.nav}
                    type="button"
                    className={`w-full text-left px-4 py-2 text-[12.5px] hover:bg-slate-50 ${
                      entry.nav === currentNav ? 'text-red-700 font-semibold bg-red-50/60' : 'text-slate-700'
                    }`}
                    onClick={() => {
                      onNavigate(entry.nav);
                      setAdminOpen(false);
                    }}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}
