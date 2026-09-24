import React from 'react';
import { ChevronRight } from '../../icons/index.jsx';

/** Shared horizontal boundary for every signed-in page. */
export function PageContainer({ children, className = '' }) {
  return <div className={`mx-auto w-full max-w-[1480px] px-4 sm:px-6 lg:px-8 ${className}`}>{children}</div>;
}

/**
 * Breadcrumb, title row with a square icon, and an optional action slot.
 * `trail` lists the crumbs before the current page; a crumb with `onClick`
 * renders as a link.
 */
export default function PageHeader({ trail = [], title, description, icon: Icon, actions, className = '' }) {
  return (
    <div className={`flex-none mb-3 ${className}`}>
      <div className="flex items-center gap-1 text-xs text-slate-500 mb-1.5">
        {trail.map((crumb) => (
          <React.Fragment key={crumb.label}>
            {crumb.onClick ? (
              <button type="button" onClick={crumb.onClick} className="hover:text-red-700 cursor-pointer">
                {crumb.label}
              </button>
            ) : (
              <span>{crumb.label}</span>
            )}
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
          </React.Fragment>
        ))}
        <span className="text-slate-700 font-medium">{title}</span>
      </div>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {Icon && (
            <div className="w-8 h-8 rounded-md bg-red-600 flex items-center justify-center text-white shadow-xs flex-shrink-0">
              <Icon className="w-5 h-5" />
            </div>
          )}
          <div className="min-w-0">
            <h1 className="text-base sm:text-[17px] font-bold text-slate-900 tracking-tight leading-snug">{title}</h1>
            {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
      </div>
    </div>
  );
}
