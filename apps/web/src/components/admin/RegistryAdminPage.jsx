import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { RefreshCw, Loader2, CheckCircle2, XCircle, Plus, Building2 } from '../../icons/index.jsx';
import PageHeader, { PageContainer } from '../layout/PageHeader.jsx';

const TABS = [
  { value: 'units', label: 'Đơn vị' },
  { value: 'candidates', label: 'Đề xuất chờ duyệt' },
  { value: 'versions', label: 'Phiên bản dữ liệu' },
];

const QA_LABELS = { APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối', PENDING_QA: 'Chờ duyệt', DRAFT: 'Bản nháp', VALIDATED: 'Đã kiểm tra' };
const ORG_LABELS = { BCA: 'Bộ Công an', BQP: 'Bộ Quốc phòng', OTHER: 'Ngoài phạm vi CA/BQP' };

function QaBadge({ status }) {
  const cls =
    status === 'APPROVED'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : status === 'REJECTED'
      ? 'bg-red-50 text-red-700 border-red-200'
      : 'bg-[#FDF0BE] text-amber-700 border-amber-200';
  return <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${cls}`}>{QA_LABELS[status] || status}</span>;
}

function UnitsTab({ apiBaseUrl }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [qaFilter, setQaFilter] = useState('');
  const [creating, setCreating] = useState(false);
  const [newUnit, setNewUnit] = useState({ canonical_name: '', organization_type: 'BCA' });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/admin/registry/units`, {
        params: { page_size: 100, ...(qaFilter ? { qa_status: qaFilter } : {}) },
      });
      setItems(res.data?.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, qaFilter]);

  useEffect(() => { load(); }, [load]);

  const createUnit = async () => {
    if (!newUnit.canonical_name.trim()) return;
    setCreating(true);
    try {
      await axios.post(`${apiBaseUrl}/api/v1/admin/registry/units`, newUnit);
      setNewUnit({ canonical_name: '', organization_type: 'BCA' });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setCreating(false);
    }
  };

  const decide = async (unitId, decision) => {
    try {
      await axios.post(`${apiBaseUrl}/api/v1/admin/registry/units/${unitId}/qa`, { decision });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-end gap-2 mb-4 bg-white border border-slate-200 rounded-md p-3">
        <input
          value={newUnit.canonical_name}
          onChange={(e) => setNewUnit((x) => ({ ...x, canonical_name: e.target.value }))}
          placeholder="Tên đơn vị mới"
          className="text-sm border border-slate-200 rounded-md px-2.5 py-1.5 outline-none focus:border-red-400 flex-1 min-w-[220px]"
        />
        <select
          value={newUnit.organization_type}
          onChange={(e) => setNewUnit((x) => ({ ...x, organization_type: e.target.value }))}
          className="text-sm border border-slate-200 rounded-md px-2.5 py-1.5 outline-none"
        >
          <option value="BCA">Bộ Công an</option>
          <option value="BQP">Bộ Quốc phòng</option>
          <option value="OTHER">Ngoài phạm vi CA/BQP</option>
        </select>
        <button
          onClick={createUnit}
          disabled={creating}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900 text-white text-xs font-semibold disabled:opacity-50"
        >
          <Plus className="w-3.5 h-3.5" /> Tạo và chờ duyệt
        </button>
        <select value={qaFilter} onChange={(e) => setQaFilter(e.target.value)} className="text-sm border border-slate-200 rounded-md px-2.5 py-1.5 ml-auto">
          <option value="">Tất cả trạng thái</option>
          <option value="PENDING_QA">Chờ duyệt</option>
          <option value="APPROVED">Đã duyệt</option>
          <option value="REJECTED">Đã từ chối</option>
        </select>
      </div>

      {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-4 py-3 mb-4">{String(error)}</div>}

      {loading ? (
        <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Đang tải</div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2.5">Tên đơn vị</th>
                <th className="text-left px-4 py-2.5">Loại</th>
                <th className="text-left px-4 py-2.5">Kiểm duyệt</th>
                <th className="text-left px-4 py-2.5">Đang sử dụng</th>
                <th className="text-right px-4 py-2.5">Hành động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2.5 font-medium text-slate-900">{u.canonical_name}</td>
                  <td className="px-4 py-2.5 text-slate-600">{ORG_LABELS[u.organization_type] || u.organization_type}</td>
                  <td className="px-4 py-2.5"><QaBadge status={u.qa_status} /></td>
                  <td className="px-4 py-2.5 text-slate-600">{u.active ? 'Có' : 'Không'}</td>
                  <td className="px-4 py-2.5 text-right">
                    {u.qa_status === 'PENDING_QA' && (
                      <div className="inline-flex gap-1.5">
                        <button onClick={() => decide(u.id, 'APPROVE')} className="text-emerald-600 hover:text-emerald-700"><CheckCircle2 className="w-4 h-4" /></button>
                        <button onClick={() => decide(u.id, 'REJECT')} className="text-red-600 hover:text-red-700"><XCircle className="w-4 h-4" /></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Không có đơn vị nào.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CandidatesTab({ apiBaseUrl }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/admin/registry/candidates`, { params: { page_size: 100 } });
      setItems(res.data?.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => { load(); }, [load]);

  const decide = async (id, decision) => {
    try {
      await axios.post(`${apiBaseUrl}/api/v1/admin/registry/candidates/${id}/decision`, { decision });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message);
    }
  };

  if (loading) return <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Đang tải</div>;

  return (
    <div>
      {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-4 py-3 mb-4">{String(error)}</div>}
      <div className="space-y-2.5">
        {items.map((c) => (
          <div key={c.id} className="bg-white border border-slate-200 rounded-md p-4 flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-slate-900">{c.proposed_name}</p>
              <p className="text-xs text-slate-500 mt-0.5">Tên ban đầu: {c.raw_name} ({ORG_LABELS[c.organization_type] || c.organization_type})</p>
            </div>
            <div className="inline-flex gap-1.5 flex-shrink-0">
              <button onClick={() => decide(c.id, 'APPROVE')} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5" /> Duyệt
              </button>
              <button onClick={() => decide(c.id, 'REJECT')} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-red-50 text-red-700 text-xs font-semibold border border-red-200">
                <XCircle className="w-3.5 h-3.5" /> Từ chối
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="text-center text-slate-400 py-10 text-sm">Không có đề xuất nào đang chờ duyệt.</div>}
      </div>
    </div>
  );
}

function VersionsTab({ apiBaseUrl }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/admin/registry/versions`, { params: { page_size: 50 } });
      setItems(res.data?.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => { load(); }, [load]);

  const act = async (version, action) => {
    try {
      await axios.post(`${apiBaseUrl}/api/v1/admin/registry/versions/${version}/${action}`, { notes: '' });
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  if (loading) return <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Đang tải</div>;

  return (
    <div>
      {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-4 py-3 mb-4">{String(error)}</div>}
      <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2.5">Phiên bản</th>
              <th className="text-left px-4 py-2.5">Trạng thái</th>
              <th className="text-left px-4 py-2.5">Số đơn vị</th>
              <th className="text-right px-4 py-2.5">Hành động</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((v) => (
              <tr key={v.id}>
                <td className="px-4 py-2.5 font-medium text-slate-900">{v.version}</td>
                <td className="px-4 py-2.5"><QaBadge status={v.status} /></td>
                <td className="px-4 py-2.5 text-slate-600">{v.counts?.units ?? 'Chưa có'}</td>
                <td className="px-4 py-2.5 text-right">
                  <div className="inline-flex gap-1.5">
                    {v.status === 'DRAFT' && (
                      <button onClick={() => act(v.version, 'validate')} className="text-xs font-semibold text-red-600 hover:text-red-700">Kiểm tra</button>
                    )}
                    {v.status === 'VALIDATED' && (
                      <button onClick={() => act(v.version, 'approve')} className="text-xs font-semibold text-red-600 hover:text-red-700">Phê duyệt</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-400">Chưa có phiên bản dữ liệu nào.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RegistryAdminPage({ apiBaseUrl }) {
  const [tab, setTab] = useState('units');

  return (
    <div className="flex-1 overflow-y-auto">
      <PageContainer className="py-3 sm:py-4">
        <PageHeader
          trail={[{ label: 'Trang chủ' }, { label: 'Quản trị' }]}
          title="Danh mục đơn vị"
          description="Quản lý đơn vị, các đề xuất chờ duyệt và phiên bản danh mục đơn vị."
          icon={Building2}
        />
        <div className="flex border-b border-slate-200 mb-3">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={`px-3.5 pt-1.5 pb-2 mr-1 text-[13px] font-semibold border-b-2 transition-colors ${
                tab === t.value ? 'text-red-600 border-red-600 bg-red-50/70' : 'text-slate-600 border-transparent hover:text-slate-900'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'units' && <UnitsTab apiBaseUrl={apiBaseUrl} />}
        {tab === 'candidates' && <CandidatesTab apiBaseUrl={apiBaseUrl} />}
        {tab === 'versions' && <VersionsTab apiBaseUrl={apiBaseUrl} />}
      </PageContainer>
    </div>
  );
}
