import { useState } from "react";
import { useAuth } from "./AuthContext";
import { ROLE_LABEL } from "./auth";

export default function LoginBar() {
  const { user, meta, login, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (u: string, p: string) => {
    setBusy(true);
    setError(null);
    try {
      await login(u, p);
      setOpen(false);
      setPassword("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (user) {
    return (
      <div className="user-chip">
        <span>{user.display_name}</span>
        <span className="badge">{ROLE_LABEL[user.role]}</span>
        <button className="small" onClick={logout}>
          Log out
        </button>
      </div>
    );
  }

  return (
    <div className="login">
      <button className="small" onClick={() => setOpen(!open)}>
        Log in
      </button>
      {open && (
        <form
          className="card login-pop"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(username, password);
          }}
        >
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={busy || !username || !password}>
            Log in
          </button>
          {meta?.demo_mode && meta.demo_password && (
            <div className="demo-accounts">
              <p className="muted">Demo accounts (synthetic data). One click to try a role:</p>
              {meta.demo_users.map((u) => (
                <button
                  type="button"
                  key={u.username}
                  className="small"
                  disabled={busy}
                  onClick={() => void submit(u.username, meta.demo_password ?? "")}
                >
                  {u.username} · {ROLE_LABEL[u.role]}
                </button>
              ))}
            </div>
          )}
        </form>
      )}
    </div>
  );
}
