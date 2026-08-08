import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiErrorDetail } from "@/lib/api";
import { startGoogleLogin } from "@/lib/googleAuth";
import { Input } from "@/components/ui/input";
import { Loader2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";

export default function Login() {
  const { t } = useTranslation();
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [mode, setMode] = useState("login");
  const [loading, setLoading] = useState(false);
  const [invitedBy, setInvitedBy] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "", username: "", city: "Palma de Mallorca", birthdate: "", phone: "" });
  const [cities, setCities] = useState([{ id: "Palma de Mallorca", label: "Palma de Mallorca", emoji: "" }]);

  useEffect(() => {
    api.get("/cities").then(({ data }) => {
      if (data?.cities?.length) setCities(data.cities);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    // WARMUP PING: fire-and-forget health check to wake up the backend
    // (Render free tier sleeps after 15 min). By the time the user submits
    // the form, the server is warm → login feels instant.
    api.get("/health").catch(() => {});

    const params = new URLSearchParams(window.location.search);
    const add = params.get("add");
    if (add) {
      const uname = add.toLowerCase().trim();
      localStorage.setItem("qv_pending_add", uname);
      setInvitedBy(uname);
      setMode("register");
    }
    const ref = params.get("ref");
    if (ref) {
      localStorage.setItem("qv_pending_ref", ref.trim());
      setInvitedBy(t("login.invited_by_code", { code: ref.trim() }));
      setMode("register");
    }
    // If the visitor was captured earlier (arrived on the preview via a
    // referral link and now navigated here), still show the banner + put them
    // in register mode so the invite context is not lost.
    if (!add && !ref) {
      try {
        const pendingAdd = localStorage.getItem("qv_pending_add");
        const pendingRef = localStorage.getItem("qv_pending_ref");
        if (pendingAdd) {
          setInvitedBy(pendingAdd);
          setMode("register");
        } else if (pendingRef) {
          setInvitedBy(t("login.invited_by_code", { code: pendingRef }));
          setMode("register");
        }
      } catch (e) { /* ignore */ }
    }
  }, []);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        if (!form.name || !form.username) {
          toast.error(t("login.err_name_user"));
          setLoading(false);
          return;
        }
        if (!form.birthdate) {
          toast.error(t("login.err_birthdate"));
          setLoading(false);
          return;
        }
        // +18 gate (client-side; backend re-checks)
        const b = new Date(form.birthdate);
        const now = new Date();
        let age = now.getFullYear() - b.getFullYear();
        const m = now.getMonth() - b.getMonth();
        if (m < 0 || (m === 0 && now.getDate() < b.getDate())) age--;
        if (isNaN(age) || age < 18) {
          toast.error(t("login.err_age"));
          setLoading(false);
          return;
        }
        const pendingSrc = localStorage.getItem("qv_src");
        await register(pendingSrc ? { ...form, source: pendingSrc } : form);
        if (pendingSrc) { try { localStorage.removeItem("qv_src"); } catch (e) { /* ignore */ } }
        // Claim referral if there is a pending code
        const pendingRef = localStorage.getItem("qv_pending_ref");
        if (pendingRef) {
          try {
            await api.post("/me/claim-referral", { code: pendingRef });
            toast.success(t("login.ref_applied"));
          } catch (err) {
            /* ignore */
          }
          localStorage.removeItem("qv_pending_ref");
        }
      }
      const onboarded = localStorage.getItem("qv_onboarded") === "1";
      // PREFETCH: start loading feed + carousels in parallel while the router
      // transitions to /feed → the page renders instantly instead of showing a spinner.
      qc.prefetchQuery({
        queryKey: ["events", "all", "all"],
        queryFn: async () => (await api.get("/events", { params: { date_filter: "all", genre: "all" } })).data,
      });
      qc.prefetchQuery({
        queryKey: ["carousels"],
        queryFn: async () => (await api.get("/events/carousels")).data,
      });
      qc.prefetchQuery({
        queryKey: ["top-weekend"],
        queryFn: async () => (await api.get("/events/top-weekend")).data,
      });
      navigate(onboarded ? "/feed" : "/onboarding");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = () => { startGoogleLogin(); };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col">
      <div className="flex justify-end px-6 pt-5">
        <LanguageSwitcher />
      </div>
      <div className="max-w-md mx-auto w-full flex-1 flex flex-col justify-center px-6 py-10">
        <div className="mb-10">
          <p className="text-xs tracking-[0.3em] uppercase text-qv-secondary font-bold mb-3">{t("login.tagline")}</p>
          <h1 className="font-display text-5xl font-black tracking-tighter leading-[0.95]">
            {t("login.title_line1")}<br />
            <span className="text-qv-primary">{t("login.title_line2")}</span>
          </h1>
          <p className="text-white/60 mt-4 text-base leading-relaxed">
            {t("login.subtitle_pre")}<span className="text-white font-semibold">{t("login.subtitle_bold")}</span>{t("login.subtitle_post")}
          </p>
        </div>

        {invitedBy && (
          <div
            data-testid="invite-banner"
            className="mb-5 flex items-center gap-3 rounded-2xl border border-qv-secondary/40 bg-qv-secondary/10 px-4 py-3"
          >
            <span className="w-9 h-9 rounded-full bg-qv-secondary/20 flex items-center justify-center text-qv-secondary shrink-0">
              <UserPlus className="w-4 h-4" />
            </span>
            <p className="text-sm text-white/90">
              <span className="font-semibold text-qv-secondary">@{invitedBy}</span> {t("login.invited_text")}
            </p>
          </div>
        )}

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
              {m === "login" ? t("login.tab_login") : t("login.tab_register")}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3" data-testid="auth-form">
          {mode === "register" && (
            <>
              <Input
                data-testid="auth-name"
                placeholder={t("login.ph_name")}
                value={form.name}
                onChange={update("name")}
                className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
              />
              <Input
                data-testid="auth-username"
                placeholder={t("login.ph_username")}
                value={form.username}
                onChange={update("username")}
                className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
              />
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/40 font-bold ml-1">{t("login.label_birthdate")}</label>
                <Input
                  data-testid="auth-birthdate"
                  type="date"
                  value={form.birthdate}
                  onChange={update("birthdate")}
                  className="h-12 mt-1 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
                />
              </div>
              <Input
                data-testid="auth-phone"
                type="tel"
                placeholder={t("login.ph_phone")}
                value={form.phone}
                onChange={update("phone")}
                className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
              />
              <div>
                <label className="text-[11px] uppercase tracking-wider text-white/40 font-bold ml-1">{t("login.label_city")}</label>
                <select
                  data-testid="auth-city"
                  value={form.city}
                  onChange={update("city")}
                  className="w-full h-12 mt-1 px-3 bg-white/5 border border-white/15 rounded-2xl text-white appearance-none"
                >
                  {cities.map((c) => (
                    <option key={c.id} value={c.id} className="bg-[#121215] text-white">
                      {c.emoji ? `${c.emoji} ` : ""}{c.label}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
          <Input
            data-testid="auth-email"
            type="email"
            placeholder={t("login.ph_email")}
            value={form.email}
            onChange={update("email")}
            className="h-12 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
          />
          <Input
            data-testid="auth-password"
            type="password"
            placeholder={t("login.ph_password")}
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
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : mode === "login" ? t("login.submit_login") : t("login.submit_register")}
          </button>
        </form>

        <div className="flex items-center gap-4 my-6">
          <div className="flex-1 h-px bg-white/10" />
          <span className="text-white/40 text-xs uppercase tracking-widest">{t("login.or")}</span>
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
          {t("login.google")}
        </button>
      </div>
    </div>
  );
}
