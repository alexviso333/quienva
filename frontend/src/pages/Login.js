import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", username: "", city: "Palma de Mallorca" });

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        if (!form.name || !form.username) {
          toast.error("Completa nombre y usuario");
          setLoading(false);
          return;
        }
        await register(form);
      }
      navigate("/feed");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/feed";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col">
      <div className="max-w-md mx-auto w-full flex-1 flex flex-col justify-center px-6 py-10">
        <div className="mb-10">
          <p className="text-xs tracking-[0.3em] uppercase text-qv-secondary font-bold mb-3">Palma de Mallorca</p>
          <h1 className="font-display text-5xl font-black tracking-tighter leading-[0.95]">
            ¿Quién<br />
            <span className="text-qv-primary">va?</span>
          </h1>
          <p className="text-white/60 mt-4 text-base leading-relaxed">
            Descubre los planes del finde y mira <span className="text-white font-semibold">qué amigos van</span> a cada sitio.
          </p>
        </div>

        <div className="flex gap-2 mb-6 p-1 bg-white/5 rounded-2xl border border-white/10">
          {["login", "register"].map((m) => (
            <button
              key={m}
              data-testid={`auth-tab-${m}`}
              onClick={() => setMode(m)}
              className={`flex-1 h-11 rounded-xl font-semibold text-sm transition-colors duration-300 ${
                mode === m ? "bg-white text-black" : "text-white/60"
              }`}
            >
              {m === "login" ? "Entrar" : "Crear cuenta"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3" data-testid="auth-form">
          {mode === "register" && (
            <>
              <Input
                data-testid="auth-name"
                placeholder="Tu nombre"
                value={form.name}
                onChange={update("name")}
                className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
              />
              <Input
                data-testid="auth-username"
                placeholder="Nombre de usuario (ej. martag)"
                value={form.username}
                onChange={update("username")}
                className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
              />
            </>
          )}
          <Input
            data-testid="auth-email"
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={update("email")}
            className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
          />
          <Input
            data-testid="auth-password"
            type="password"
            placeholder="Contraseña"
            value={form.password}
            onChange={update("password")}
            className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
          />
          <button
            data-testid="auth-submit"
            type="submit"
            disabled={loading}
            className="h-13 mt-2 py-3.5 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 shadow-[0_0_22px_rgba(255,0,85,0.4)] transition-transform duration-300 active:scale-95 disabled:opacity-60"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : mode === "login" ? "Entrar" : "Crear mi cuenta"}
          </button>
        </form>

        <div className="flex items-center gap-4 my-6">
          <div className="flex-1 h-px bg-white/10" />
          <span className="text-white/40 text-xs uppercase tracking-widest">o</span>
          <div className="flex-1 h-px bg-white/10" />
        </div>

        <button
          data-testid="auth-google"
          onClick={googleLogin}
          className="h-12 rounded-2xl bg-white text-black font-semibold text-sm flex items-center justify-center gap-3 transition-transform duration-300 active:scale-95"
        >
          <svg className="w-5 h-5" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Continuar con Google
        </button>
      </div>
    </div>
  );
}
