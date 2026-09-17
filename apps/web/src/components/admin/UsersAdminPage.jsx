import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Check,
  Copy,
  KeyRound,
  Loader2,
  Lock,
  Mail,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Unlock,
  UserPlus,
} from '../../icons/index.jsx';

/**
 * Account administration.
 *
 * An administrator enters the officer's administrative particulars; the server
 * issues the login id and a random password, returned once. Permissions are
 * checkboxes on the account — there is no separate "cán bộ thẩm định" role to
 * assign, only the preset that ticks the review permissions.
 *
 * Every control here mirrors a server-side rule. Ticking a box in devtools
 * changes this form and nothing else: the account's authority is whatever the
 * server stored, re-read on each of that account's requests.
 */

const EMPTY_FORM = {
  display_name: '',
  personal_code: '',
  birth_year: '',
  rank: '',
  position: '',
  department: '',
  unit_name: '',
  phone: '',
  email: '',
  username: '',
};

function errorText(e) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg || String(d)).join('; ');
  return e?.message || 'Đã xảy ra lỗi';
}

/**
 * Reports where the issued password went.
 *
 * On a successful send the server withholds the password, so there is nothing
 * to display and nothing to copy — that is the point of mailing it. It comes
 * back only when delivery failed, and then the administrator does need it.
 */
function CredentialNotice({ credential, onDismiss }) {
  const [copied, setCopied] = useState(false);
  if (!credential) return null;

  const delivered = credential.delivery?.ok;
  const toOutbox = credential.delivery?.transport === 'file';
  const tone = delivered
    ? 'border-emerald-300 bg-emerald-50'
    : 'border-amber-300 bg-[#FDF0BE]';
  const textTone = delivered ? 'text-emerald-900' : 'text-amber-900';
  const subTone = delivered ? 'text-emerald-800' : 'text-amber-800';

  return (
    <div className={`mb-4 rounded-md border px-4 py-3 ${tone}`}>
      <div className="flex items-start gap-3">
        {delivered ? (
          <Mail className={`w-5 h-5 mt-0.5 flex-shrink-0 ${textTone}`} />
        ) : (
          <KeyRound className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-bold ${textTone}`}>
            {delivered ? `Đã gửi mật khẩu tới ${credential.email}` : 'Không gửi được thư'}
          </p>
          <p className={`text-xs mt-0.5 ${subTone}`}>{credential.notice}</p>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className={`text-xs ${subTone}`}>Tên đăng nhập:</span>
            <code className="px-2 py-1 rounded bg-white border border-slate-300 text-sm font-mono">
              {credential.username}
            </code>
          </div>

          {credential.password && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className={`text-xs ${subTone}`}>Mật khẩu:</span>
              <code className="px-2 py-1 rounded bg-white border border-amber-300 text-sm font-mono">
                {credential.password}
              </code>
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded border border-amber-300 bg-white text-xs text-amber-800 hover:bg-amber-100"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(`${credential.username} / ${credential.password}`);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  } catch {
                    /* Clipboard access can be refused; the value stays visible on screen. */
                  }
                }}
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Đã sao chép' : 'Sao chép'}
              </button>
            </div>
          )}

          {delivered && toOutbox && (
            <p className="mt-2 text-xs text-emerald-700">
              Hệ thống đang chạy không có máy chủ thư: nội dung thư được ghi ra thư mục
              <code className="mx-1 px-1 rounded bg-white border border-emerald-200">MAIL_OUTBOX_DIR</code>
              thay vì gửi đi thật.
            </p>
          )}
        </div>
        <button type="button" className="text-xs text-slate-600 hover:underline" onClick={onDismiss}>
          Đóng
        </button>
      </div>
    </div>
  );
}

function PermissionEditor({ catalog, presets, value, onChange, disabled }) {
  const groups = useMemo(() => {
    const byGroup = new Map();
    for (const item of catalog) {
      if (!byGroup.has(item.group)) byGroup.set(item.group, []);
      byGroup.get(item.group).push(item);
    }
    return Array.from(byGroup.entries());
  }, [catalog]);

  const selected = new Set(value);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Bộ quyền mẫu</span>
        {Object.entries(presets || {}).map(([name, codes]) => (
          <button
            key={name}
            type="button"
            disabled={disabled}
            onClick={() => onChange(codes)}
            className="px-2.5 py-1 rounded-full border border-slate-200 text-xs font-medium text-slate-600 hover:bg-red-50 hover:border-red-300 hover:text-red-700 disabled:opacity-50"
          >
            {name === 'REVIEWER' ? 'Cán bộ thẩm định' : 'Cán bộ tra cứu'}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange([])}
          className="px-2.5 py-1 rounded-full border border-slate-200 text-xs font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-50"
        >
          Bỏ chọn tất cả
        </button>
      </div>

      <div className="space-y-3">
        {groups.map(([group, items]) => (
          <div key={group}>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-1">{group}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {items.map((item) => (
                <label
                  key={item.code}
                  className="flex items-start gap-2 px-2.5 py-2 rounded-md border border-slate-200 hover:bg-slate-50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    disabled={disabled}
                    checked={selected.has(item.code)}
                    onChange={(e) => {
                      const next = new Set(selected);
                      if (e.target.checked) next.add(item.code);
                      else next.delete(item.code);
                      onChange(catalog.filter((x) => next.has(x.code)).map((x) => x.code));
                    }}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-slate-800">{item.label}</span>
                    <span className="block text-xs text-slate-500 leading-snug">{item.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function UsersAdminPage({ apiBaseUrl }) {
  const base = `${apiBaseUrl}/api/v1/admin/users`;

  const [items, setItems] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [presets, setPresets] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [credential, setCredential] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formPermissions, setFormPermissions] = useState([]);
  const [busyUser, setBusyUser] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(base, { params: { q: query || undefined, page_size: 200 } });
      setItems(res.data?.items || []);
      setCatalog(res.data?.catalog || []);
      setPresets(res.data?.presets || {});
      if (!formPermissions.length && res.data?.presets?.USER) setFormPermissions(res.data.presets.USER);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
    // formPermissions is seeded once from the server's preset; re-running on
    // every edit would fight the administrator's checkbox changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, query]);

  useEffect(() => {
    load();
  }, [load]);

  async function createAccount(event) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const payload = {
        ...form,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        username: form.username.trim() || null,
        permissions: formPermissions,
      };
      for (const key of Object.keys(payload)) {
        if (payload[key] === '') payload[key] = null;
      }
      const res = await axios.post(base, payload);
      setCredential({
        username: res.data.user.username,
        email: res.data.email,
        password: res.data.initial_password,
        delivery: res.data.email_delivery,
        notice: res.data.notice,
      });
      setForm(EMPTY_FORM);
      setFormPermissions(presets.USER || []);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setCreating(false);
    }
  }

  async function patchUser(username, body) {
    setBusyUser(username);
    setError(null);
    try {
      await axios.patch(`${base}/${encodeURIComponent(username)}`, body);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyUser(null);
    }
  }

  async function resetPassword(username) {
    setBusyUser(username);
    setError(null);
    try {
      const res = await axios.post(`${base}/${encodeURIComponent(username)}/reset-password`);
      setCredential({
        username: res.data.username,
        email: res.data.email,
        password: res.data.initial_password,
        delivery: res.data.email_delivery,
        notice: res.data.notice,
      });
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyUser(null);
    }
  }

  async function removeAccount(user) {
    // Irreversible, and the officer loses access immediately — so it asks first,
    // naming the account rather than just "this user".
    const confirmed = window.confirm(
      `Xóa vĩnh viễn tài khoản "${user.username}" (${user.display_name})?\n\n` +
        'Mọi phiên đăng nhập sẽ bị thu hồi ngay. Hồ sơ và nhật ký kiểm toán do tài khoản này tạo vẫn được giữ nguyên.'
    );
    if (!confirmed) return;
    setBusyUser(user.username);
    setError(null);
    try {
      await axios.delete(`${base}/${encodeURIComponent(user.username)}`);
      if (credential?.username === user.username) setCredential(null);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyUser(null);
    }
  }

  async function unlock(username) {
    setBusyUser(username);
    try {
      await axios.post(`${base}/${encodeURIComponent(username)}/unlock`);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyUser(null);
    }
  }

  const field = (name, label, extra = {}) => (
    <label className="block">
      <span className="text-xs font-semibold text-slate-600">{label}</span>
      <input
        className="mt-1 w-full h-10 px-3 rounded-md border border-slate-200 focus:border-red-500 focus:ring-2 focus:ring-red-100 outline-none text-sm"
        value={form[name]}
        onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        {...extra}
      />
    </label>
  );

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-extrabold text-slate-900">Quản trị tài khoản</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Cấp tài khoản theo thông tin hành chính và phân quyền theo từng chức năng.
            </p>
          </div>
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-slate-200 text-sm text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw className="w-4 h-4" /> Tải lại
          </button>
        </div>

        <CredentialNotice credential={credential} onDismiss={() => setCredential(null)} />

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-4 py-3 mb-4">{error}</div>
        )}

        {/* Create */}
        <form onSubmit={createAccount} className="bg-white border border-slate-200 rounded-md p-5 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <UserPlus className="w-4 h-4 text-red-600" />
            <h2 className="text-sm font-bold text-slate-900">Cấp tài khoản mới</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {field('display_name', 'Họ và tên *', { required: true, placeholder: 'Nguyễn Văn Hùng' })}
            {field('personal_code', 'Mã số cán bộ', { placeholder: 'CA-2026-0417' })}
            {field('birth_year', 'Năm sinh', { type: 'number', min: 1900, max: 2100, placeholder: '1988' })}
            {field('rank', 'Cấp bậc', { placeholder: 'Thiếu tá' })}
            {field('position', 'Chức vụ', { placeholder: 'Chuyên viên' })}
            {field('department', 'Phòng/Ban', { placeholder: 'Phòng Tổ chức cán bộ' })}
            {field('unit_name', 'Đơn vị công tác', { placeholder: 'Cục Tổ chức cán bộ' })}
            {field('phone', 'Điện thoại')}
            {field('email', 'Thư điện tử *', {
              type: 'email',
              required: true,
              placeholder: 'Mật khẩu khởi tạo sẽ gửi tới địa chỉ này',
            })}
            {field('username', 'Tên đăng nhập', {
              placeholder: 'Bỏ trống để hệ thống tự sinh từ mã số/họ tên',
            })}
          </div>

          <div className="mt-5 pt-4 border-t border-slate-100">
            <PermissionEditor
              catalog={catalog}
              presets={presets}
              value={formPermissions}
              onChange={setFormPermissions}
              disabled={creating}
            />
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="submit"
              disabled={creating}
              className="inline-flex items-center gap-2 px-4 h-10 rounded-md bg-red-600 hover:bg-red-700 disabled:bg-slate-300 text-white text-sm font-semibold"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
              Cấp tài khoản
            </button>
            <span className="text-xs text-slate-500">
              Mật khẩu ngẫu nhiên được sinh tự động và chỉ hiển thị một lần sau khi tạo.
            </span>
          </div>
        </form>

        {/* List */}
        <div className="flex items-center gap-3 mb-3">
          <input
            className="h-10 px-3 rounded-md border border-slate-200 text-sm w-72"
            placeholder="Tìm theo tên, mã số, phòng ban…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="text-xs text-slate-500">{items.length} tài khoản</span>
        </div>

        {loading ? (
          <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Đang tải...
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2.5">Tài khoản</th>
                  <th className="text-left px-4 py-2.5">Chức vụ / Đơn vị</th>
                  <th className="text-left px-4 py-2.5">Quyền</th>
                  <th className="text-left px-4 py-2.5">Trạng thái</th>
                  <th className="text-right px-4 py-2.5">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((u) => (
                  <React.Fragment key={u.username}>
                    <tr className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <div className="font-semibold text-slate-900">{u.display_name}</div>
                        <div className="text-xs text-slate-500 font-mono">{u.username}</div>
                        {u.personal_code && <div className="text-xs text-slate-400">Mã: {u.personal_code}</div>}
                        {u.email && <div className="text-xs text-slate-400">{u.email}</div>}
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs">
                        <div>{[u.rank, u.position].filter(Boolean).join(' · ') || '—'}</div>
                        <div className="text-slate-400">{[u.department, u.unit_name].filter(Boolean).join(' · ')}</div>
                      </td>
                      <td className="px-4 py-3">
                        {u.is_admin ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-semibold">
                            <ShieldCheck className="w-3 h-3" /> Quản trị viên
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="text-xs text-red-600 hover:underline"
                            onClick={() => setExpanded(expanded === u.username ? null : u.username)}
                          >
                            {u.permissions.length} quyền — {expanded === u.username ? 'thu gọn' : 'chỉnh sửa'}
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {!u.is_active && <span className="text-red-600 font-semibold">Đã khóa</span>}
                        {u.is_active && u.locked_until && (
                          <span className="text-amber-600 font-semibold">Tạm khóa</span>
                        )}
                        {u.is_active && !u.locked_until && <span className="text-emerald-600">Hoạt động</span>}
                        {u.must_change_password && (
                          <div className="text-slate-400 mt-0.5">Chưa đổi mật khẩu</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        {u.is_admin ? (
                          <span className="text-xs text-slate-400">Không chỉnh sửa</span>
                        ) : (
                          <div className="inline-flex items-center gap-1.5">
                            {u.locked_until && (
                              <button
                                type="button"
                                disabled={busyUser === u.username}
                                onClick={() => unlock(u.username)}
                                className="px-2 py-1 rounded border border-slate-200 text-xs text-slate-600 hover:bg-slate-50"
                              >
                                <Unlock className="w-3 h-3 inline" /> Mở khóa
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={busyUser === u.username}
                              onClick={() => resetPassword(u.username)}
                              className="px-2 py-1 rounded border border-slate-200 text-xs text-slate-600 hover:bg-slate-50"
                            >
                              <KeyRound className="w-3 h-3 inline" /> Cấp lại mật khẩu
                            </button>
                            <button
                              type="button"
                              disabled={busyUser === u.username}
                              onClick={() => patchUser(u.username, { is_active: !u.is_active })}
                              className={`px-2 py-1 rounded border text-xs ${
                                u.is_active
                                  ? 'border-red-200 text-red-600 hover:bg-red-50'
                                  : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                              }`}
                            >
                              <Lock className="w-3 h-3 inline" /> {u.is_active ? 'Khóa' : 'Mở'}
                            </button>
                            <button
                              type="button"
                              disabled={busyUser === u.username}
                              onClick={() => removeAccount(u)}
                              title="Xóa vĩnh viễn tài khoản"
                              className="px-2 py-1 rounded border border-red-300 text-xs text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-3 h-3 inline" /> Xóa
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                    {expanded === u.username && !u.is_admin && (
                      <tr className="bg-slate-50/60">
                        <td colSpan={5} className="px-4 py-4">
                          <PermissionEditor
                            catalog={catalog}
                            presets={presets}
                            value={u.permissions}
                            disabled={busyUser === u.username}
                            onChange={(next) => patchUser(u.username, { permissions: next })}
                          />
                          <label className="block mt-4 max-w-md">
                            <span className="text-xs font-semibold text-slate-600">
                              Phạm vi thẩm định (coverage group, để trống = toàn hệ thống)
                            </span>
                            <input
                              className="mt-1 w-full h-10 px-3 rounded-md border border-slate-200 text-sm"
                              defaultValue={(u.coverage_groups || []).join(', ')}
                              placeholder="BCA_CENTRAL_PUBLIC, BQP_SOUTH"
                              onBlur={(e) => {
                                const next = e.target.value
                                  .split(',')
                                  .map((x) => x.trim())
                                  .filter(Boolean);
                                if (next.join(',') !== (u.coverage_groups || []).join(','))
                                  patchUser(u.username, { coverage_groups: next });
                              }}
                            />
                          </label>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default UsersAdminPage;
