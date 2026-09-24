import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogOut, User } from '../../icons/index.jsx';

const BRAND_TONES = {
  // White text for the red login background.
  light: { title: 'text-white', subtitle: 'text-amber-300' },
  // Dark red text for the pale header background after sign-in.
  dark: { title: 'text-[#8a1010]', subtitle: 'text-[#9a3412]' },
};

const BRAND_SIZES = {
  normal: { title: 'text-[15px] sm:text-[17px]', subtitle: 'text-[11px] sm:text-[12px]' },
  large: { title: 'text-[22px] sm:text-[30px]', subtitle: 'text-[13px] sm:text-[16px] mt-1' },
};

/** Text-only brand block. The header deliberately carries no emblem or logo image. */
export function BrandTitle(props) {
  const { onClick, tone = 'dark', size = 'normal', align = 'left' } = props;
  const Tag = onClick ? 'button' : 'div';
  const colors = BRAND_TONES[tone];
  const sizes = BRAND_SIZES[size];
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`flex flex-col leading-tight ${align === 'center' ? 'items-center text-center' : 'text-left'} ${onClick ? 'cursor-pointer' : ''}`}
    >
      <span className={`${sizes.title} ${colors.title} font-bold tracking-wide uppercase`}>Hệ thống xác minh nhân sự</span>
      <span className={`${sizes.subtitle} ${colors.subtitle} font-semibold tracking-wider uppercase`}>
        Bộ Công an - Bộ Quốc phòng
      </span>
    </Tag>
  );
}

export default function AppHeader({ user, roleLabel, onHome, onLogout }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const name = user?.displayName || user?.username || 'Người dùng';

  return (
    <header
      className="flex-none relative select-none z-30 border-b border-amber-200 bg-[#fdeec4] bg-cover bg-center"
      style={{ backgroundImage: 'url(/bg-head-new.png)' }}
    >
      <div className="max-w-[1480px] mx-auto px-4 sm:px-6 lg:px-8 h-[64px] flex items-center justify-between">
        <BrandTitle onClick={onHome} />

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="flex items-center gap-2.5 py-1 px-1.5 rounded-md hover:bg-amber-900/10 transition-colors cursor-pointer"
          >
            <span className="w-8 h-8 rounded-full bg-[#8a1010] text-white flex items-center justify-center flex-shrink-0">
              <User className="w-5 h-5" />
            </span>
            <span className="hidden sm:flex flex-col text-left leading-tight">
              <span className="text-[12.5px] font-semibold text-slate-900">{name}</span>
              <span className="text-[11px] text-slate-600">{roleLabel}</span>
            </span>
            <ChevronDown className="w-4 h-4 text-slate-600" />
          </button>

          {open && (
            <div className="absolute right-0 top-full mt-1 w-56 bg-white rounded-md shadow-xl border border-slate-200 py-1 text-slate-700 text-xs z-50">
              <div className="px-4 py-2 border-b border-slate-100 bg-slate-50">
                <p className="font-semibold text-slate-800 truncate">{name}</p>
                <p className="text-[11px] text-slate-500 truncate">{user?.username}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  if (onLogout) onLogout();
                }}
                className="w-full text-left flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 font-medium"
              >
                <LogOut className="w-4 h-4" />
                Đăng xuất
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
