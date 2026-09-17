import React from 'react';

export default function AppFooter({ className = '' }) {
  return (
    <footer className={`flex-none bg-white border-t border-slate-200 py-2 px-4 sm:px-6 lg:px-8 text-[11px] text-slate-500 select-none z-20 ${className}`}>
      <div className="max-w-[1480px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-1">
        <span className="font-semibold text-slate-700 uppercase">Hệ thống xác minh nhân sự</span>
        <span>Bộ Công an - Bộ Quốc phòng, 2026</span>
      </div>
    </footer>
  );
}
