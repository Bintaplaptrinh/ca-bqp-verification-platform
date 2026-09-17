import { useEffect, useState } from "react";
import { KeyRound, LockKeyhole, LogIn, UserRound } from "./icons/index.jsx";
import { changePassword, fetchCurrentUser, login, logout } from "./auth";
import type { CurrentUser } from "./types";
import VerificationModule from "./components/VerificationModule.jsx";

function LoginPage({ onSignedIn }: { onSignedIn: (user: CurrentUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await login(username.trim(), password));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-white text-neutral-900 flex flex-col relative overflow-hidden">
      <header className="relative z-10 bg-[#c8102e] flex items-center px-5 sm:px-10 py-3.5">
        <div className="leading-tight">
          <strong className="block text-white text-sm font-bold uppercase tracking-wide">Hệ thống xác minh nhân sự</strong>
          <span className="block text-white/85 text-xs mt-0.5">Bộ Công An – Bộ Quốc Phòng</span>
        </div>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-10 sm:py-14 bg-neutral-50">
        <section className="w-full max-w-[460px] bg-white rounded-md border border-neutral-200 shadow-[0_18px_55px_rgba(15,23,42,0.08)] p-6 sm:p-8">
          <h1 className="text-2xl sm:text-[28px] font-bold tracking-tight">Đăng nhập hệ thống</h1>
          <p className="mt-2 text-sm text-neutral-500 leading-relaxed">
            Sử dụng tài khoản nghiệp vụ do quản trị viên cấp để tra cứu và thẩm định hồ sơ.
          </p>

          {error && (
            <div className="mt-5 rounded-md bg-[#fbe9eb] px-4 py-3 flex gap-3 text-sm text-[#7a1220]" role="alert">
              <div className="w-6 h-6 rounded-full bg-[#f0b6bf] flex items-center justify-center font-bold flex-shrink-0">!</div>
              <div>
                <strong className="block">Đăng nhập không thành công</strong>
                <p className="mt-0.5 text-[#9e0b22]">{error}</p>
              </div>
            </div>
          )}

          <form className="mt-6 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="text-sm font-semibold text-neutral-700">Tên đăng nhập</span>
              <div className="mt-1.5 relative">
                <UserRound className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                <input
                  className="w-full h-11 pl-9 pr-3 rounded-md border border-neutral-200 focus:border-[#c8102e] focus:ring-2 focus:ring-[#fbe9eb] outline-none text-sm"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </div>
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-neutral-700">Mật khẩu</span>
              <div className="mt-1.5 relative">
                <KeyRound className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                <input
                  className="w-full h-11 pl-9 pr-3 rounded-md border border-neutral-200 focus:border-[#c8102e] focus:ring-2 focus:ring-[#fbe9eb] outline-none text-sm"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
            </label>

            <button
              type="submit"
              disabled={busy}
              className="w-full h-12 rounded-md bg-[#c8102e] hover:bg-[#9e0b22] active:bg-[#7a1220] disabled:bg-neutral-300 text-white font-semibold flex items-center justify-center gap-2 shadow-sm transition-colors"
            >
              <LogIn className="w-4.5 h-4.5" aria-hidden="true" />
              {busy ? "Đang kiểm tra…" : "Đăng nhập"}
            </button>
          </form>

          <div className="mt-4 flex items-start gap-2 text-xs text-neutral-500 leading-relaxed">
            <LockKeyhole className="w-4 h-4 mt-0.5 flex-shrink-0 text-neutral-400" aria-hidden="true" />
            <span>
              Quyền truy cập được quản trị viên cấp theo từng tài khoản và được kiểm tra tại máy chủ ở mọi thao tác.
            </span>
          </div>
        </section>
      </main>

      <footer className="relative z-10 min-h-14 bg-white border-t border-neutral-200 px-5 sm:px-10 py-3 flex flex-col sm:flex-row items-center justify-between gap-1 text-[11px] text-neutral-500">
        <span>Hệ thống xác minh nhân sự Bộ Công An - Bộ Quốc Phòng &copy; 2026</span>
        <span>Dữ liệu nghiệp vụ được bảo vệ theo phân quyền</span>
      </footer>
    </div>
  );
}

/**
 * Shown when an administrator has flagged the account to change its password.
 *
 * This is a prompt, not a gate: the server does not treat an unchanged password
 * as a reason to refuse requests, so nothing here is load-bearing for security.
 */
function ChangePasswordPage({ user, onDone }: { user: CurrentUser; onDone: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (newPassword !== confirmation) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex items-center justify-center px-4 py-10">
      <section className="w-full max-w-[460px] bg-white rounded-md border border-neutral-200 shadow-[0_18px_55px_rgba(15,23,42,0.08)] p-6 sm:p-8">
        <h1 className="text-2xl font-bold tracking-tight">Đổi mật khẩu lần đầu</h1>
        <p className="mt-2 text-sm text-neutral-500 leading-relaxed">
          Tài khoản <strong>{user.username}</strong> đang dùng mật khẩu do quản trị viên cấp. Hãy đặt mật khẩu riêng
          trước khi sử dụng hệ thống.
        </p>

        {error && (
          <div className="mt-5 rounded-md bg-[#fbe9eb] px-4 py-3 text-sm text-[#7a1220]" role="alert">
            {error}
          </div>
        )}

        <form className="mt-6 space-y-4" onSubmit={submit}>
          {[
            { label: "Mật khẩu được cấp", value: currentPassword, set: setCurrentPassword, autoComplete: "current-password" },
            { label: "Mật khẩu mới", value: newPassword, set: setNewPassword, autoComplete: "new-password" },
            { label: "Xác nhận mật khẩu mới", value: confirmation, set: setConfirmation, autoComplete: "new-password" },
          ].map((field) => (
            <label className="block" key={field.label}>
              <span className="text-sm font-semibold text-neutral-700">{field.label}</span>
              <input
                className="mt-1.5 w-full h-11 px-3 rounded-md border border-neutral-200 focus:border-[#c8102e] focus:ring-2 focus:ring-[#fbe9eb] outline-none text-sm"
                type="password"
                value={field.value}
                onChange={(e) => field.set(e.target.value)}
                autoComplete={field.autoComplete}
                required
              />
            </label>
          ))}

          <button
            type="submit"
            disabled={busy}
            className="w-full h-12 rounded-md bg-[#c8102e] hover:bg-[#9e0b22] disabled:bg-neutral-300 text-white font-semibold transition-colors"
          >
            {busy ? "Đang lưu…" : "Đặt mật khẩu mới"}
          </button>
        </form>

        <button
          type="button"
          className="mt-3 w-full h-10 text-sm text-neutral-500 hover:text-neutral-700"
          onClick={onDone}
        >
          Để sau
        </button>
      </section>
    </div>
  );
}

export default function App() {
  const [booting, setBooting] = useState(true);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [passwordPromptDismissed, setPasswordPromptDismissed] = useState(false);

  useEffect(() => {
    (async () => {
      setUser(await fetchCurrentUser());
      setBooting(false);
    })();
  }, []);

  if (booting) {
    return (
      <div className="app-loading">
        <div className="boot-card">
          <div className="spinner" />
          <div>
            <strong>Đang khởi tạo phiên làm việc</strong>
            <p>Đang kiểm tra thông tin đăng nhập…</p>
          </div>
        </div>
      </div>
    );
  }

  if (!user) return <LoginPage onSignedIn={setUser} />;

  if (user.mustChangePassword && !passwordPromptDismissed) {
    return (
      <ChangePasswordPage
        user={user}
        onDone={async () => {
          setPasswordPromptDismissed(true);
          setUser((await fetchCurrentUser()) ?? user);
        }}
      />
    );
  }

  return <VerificationModule user={user} onLogout={logout} />;
}
