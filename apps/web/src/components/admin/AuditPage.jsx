import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Loader2, RefreshCw } from '../../icons/index.jsx';

export function AuditPage({ apiBaseUrl }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/admin/audit`, { params: { limit: 200 } });
      setItems(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-extrabold text-slate-900">Nhật ký kiểm toán</h1>
            <p className="text-sm text-slate-500 mt-0.5">Nhật ký nghiệp vụ append-only — chỉ ghi, không sửa/xoá.</p>
          </div>
          <button onClick={load} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-slate-200 text-sm text-slate-600 hover:bg-slate-50">
            <RefreshCw className="w-4 h-4" /> Tải lại
          </button>
        </div>

        {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-4 py-3 mb-4">{String(error)}</div>}

        {loading ? (
          <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Đang tải...</div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2.5">Thời gian</th>
                  <th className="text-left px-4 py-2.5">Actor</th>
                  <th className="text-left px-4 py-2.5">Hành động</th>
                  <th className="text-left px-4 py-2.5">Entity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((x) => (
                  <React.Fragment key={x.id}>
                    <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setExpanded(expanded === x.id ? null : x.id)}>
                      <td className="px-4 py-2.5 text-slate-500 text-xs whitespace-nowrap">{new Date(x.timestamp).toLocaleString('vi-VN')}</td>
                      <td className="px-4 py-2.5 font-medium text-slate-900">{x.actor} <span className="text-xs text-slate-400">({x.role})</span></td>
                      <td className="px-4 py-2.5 text-slate-700 font-mono text-xs">{x.action}</td>
                      <td className="px-4 py-2.5 text-slate-500 text-xs">{x.entity_type}#{String(x.entity_id).slice(0, 10)}</td>
                    </tr>
                    {expanded === x.id && x.metadata && (
                      <tr>
                        <td colSpan={4} className="px-4 py-3 bg-slate-50">
                          <pre className="text-[11px] text-slate-600 whitespace-pre-wrap break-all">{JSON.stringify(x.metadata, null, 2)}</pre>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {items.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-400">Chưa có bản ghi audit nào.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
