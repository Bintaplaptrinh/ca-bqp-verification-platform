import { useEffect, useState } from "react";
import { changePassword, fetchCurrentUser, login, logout } from "./auth";
import type { CurrentUser } from "./types";
import VerificationModule from "./components/VerificationModule.jsx";
import { BrandTitle } from "./components/layout/AppHeader.jsx";

const inputClass =
  "input-auth w-full h-10 px-3 rounded-md border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 outline-none";

/**
 * Signed-out layout: the red bronze-drum background fills the screen and the
 * system title sits centered above the form.
 */
function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 flex flex-col overflow-hidden bg-[#8f0a12] bg-cover bg-center"
      style={{ backgroundImage: "url(/login-bg.jpg)" }}
    >
      <main className="flex-1 min-h-0 overflow-y-auto flex flex-col items-center justify-center gap-6 px-4 py-8">
        <BrandTitle tone="light" size="large" align="center" />
        <div className="w-full max-w-[400px]">{children}</div>
      </main>

      <footer className="flex-none py-3 text-center text-[11px] text-white/70">
        Hệ thống xác minh nhân sự Bộ Công an - Bộ Quốc phòng, 2026
      </footer>
    </div>
  );
}

function LoginPage({ onSignedIn }: { onSignedIn: (user: CurrentUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <AuthShell>
      <section className="bg-white rounded-md shadow-2xl border-t-4 border-[#b91c1c] px-6 py-7 sm:px-8">
        <h1 className="text-center text-xl font-bold uppercase tracking-wide text-[#b91c1c]">Đăng nhập</h1>
        <p className="mt-1 text-center text-xs text-slate-500">Tài khoản do quản trị viên hệ thống cấp</p>

        {error && (
          <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700" role="alert">
            <strong className="block font-semibold">Đăng nhập không thành công</strong>
            <span className="block mt-0.5">{error}</span>
          </div>
        )}

        <form className="mt-5 space-y-4" onSubmit={submit}>
          <div>
            <label htmlFor="login-username" className="block mb-1 text-[13px] font-semibold text-slate-700">
              Tên đăng nhập
            </label>
            <input
              id="login-username"
              className={inputClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Nhập tên đăng nhập"
              autoComplete="username"
              autoFocus
              required
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block mb-1 text-[13px] font-semibold text-slate-700">
              Mật khẩu
            </label>
            <div className="relative">
              <input
                id="login-password"
                className={`${inputClass} pr-14`}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Nhập mật khẩu"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 px-3 text-xs font-medium text-slate-500 hover:text-slate-800"
              >
                {showPassword ? "Ẩn" : "Hiện"}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full h-10 rounded-md bg-[#b91c1c] hover:bg-[#8a1010] disabled:bg-slate-400 text-white text-sm font-semibold transition-colors"
          >
            {busy ? "Đang kiểm tra" : "Đăng nhập"}
          </button>
        </form>
      </section>
    </AuthShell>
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
    <AuthShell>
      <section className="bg-white rounded-md shadow-2xl border-t-4 border-[#b91c1c] px-6 py-7 sm:px-8">
        <h1 className="text-center text-xl font-bold uppercase tracking-wide text-[#b91c1c]">Đổi mật khẩu</h1>
        <p className="mt-1 text-center text-xs text-slate-500 leading-relaxed">
          Tài khoản <strong className="text-slate-700">{user.username}</strong> đang dùng mật khẩu do quản trị viên cấp.
          Đặt mật khẩu riêng trước khi sử dụng.
        </p>

        {error && (
          <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700" role="alert">
            {error}
          </div>
        )}

        <form className="mt-5 space-y-4" onSubmit={submit}>
          {[
            { id: "pw-current", label: "Mật khẩu được cấp", value: currentPassword, set: setCurrentPassword, autoComplete: "current-password" },
            { id: "pw-new", label: "Mật khẩu mới", value: newPassword, set: setNewPassword, autoComplete: "new-password" },
            { id: "pw-confirm", label: "Nhập lại mật khẩu mới", value: confirmation, set: setConfirmation, autoComplete: "new-password" },
          ].map((field) => (
            <div key={field.id}>
              <label htmlFor={field.id} className="block mb-1 text-[13px] font-semibold text-slate-700">
                {field.label}
              </label>
              <input
                id={field.id}
                className={inputClass}
                type="password"
                value={field.value}
                onChange={(e) => field.set(e.target.value)}
                autoComplete={field.autoComplete}
                required
              />
            </div>
          ))}

          <button
            type="submit"
            disabled={busy}
            className="w-full h-10 rounded-md bg-[#b91c1c] hover:bg-[#8a1010] disabled:bg-slate-400 text-white text-sm font-semibold transition-colors"
          >
            {busy ? "Đang lưu" : "Đặt mật khẩu mới"}
          </button>
        </form>

        <button
          type="button"
          className="mt-2 w-full h-9 text-sm text-slate-500 hover:text-slate-800"
          onClick={onDone}
        >
          Để sau
        </button>
      </section>
    </AuthShell>
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
      <div className="fixed inset-0 flex items-center justify-center bg-slate-100">
        <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-md shadow-sm px-5 py-4">
          <div className="w-6 h-6 border-[3px] border-red-200 border-t-red-700 rounded-full animate-spin" />
          <span className="text-sm font-medium text-slate-700">Đang kiểm tra phiên đăng nhập</span>
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
