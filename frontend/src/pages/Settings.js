import { useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { ArrowLeft, LogOut, Camera, Share2, Loader2, Save, Bell, BellRing, Archive, Grid3x3, Rows3, Copy, Eye, Users2, EyeOff, Ban, Zap, Globe2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { isPushSupported, getPushStatus, subscribeToPush, unsubscribeFromPush } from "@/lib/push";
import { StoriesArchive } from "@/components/Stories";
import { useCompactMode } from "@/hooks/useCompactMode";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";

export default function Settings() {
  const { t } = useTranslation();
  const { user, setUser, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileRef = useRef(null);
  const [name, setName] = useState(user?.name || "");
  const [city, setCity] = useState(user?.city || "Palma de Mallorca");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [pushOn, setPushOn] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [compact, setCompact] = useCompactMode();
  const pushSupported = isPushSupported();
  const [privacy, setPrivacy] = useState(user?.attendance_privacy || "amigos");
  const [privacyBusy, setPrivacyBusy] = useState(false);
  const { data: citiesData } = useQuery({
    queryKey: ["cities"],
    queryFn: async () => (await api.get("/cities")).data,
    staleTime: 1000 * 60 * 60,
  });
  const cities = citiesData?.cities || [{ id: "Palma de Mallorca", label: "Palma de Mallorca", emoji: "" }];
  const [momentPriv, setMomentPriv] = useState(user?.moment_privacy || "amigos");
  const [cityAlerts, setCityAlerts] = useState(!!user?.city_change_alerts);
  const [cityAlertsBusy, setCityAlertsBusy] = useState(false);

  const toggleCityAlerts = async () => {
    const next = !cityAlerts;
    setCityAlerts(next);
    setCityAlertsBusy(true);
    try {
      await api.put("/me/city-alerts", { enabled: next });
      if (user) setUser({ ...user, city_change_alerts: next });
      toast.success(next ? `Te avisaremos de cambios en ${user?.city || "tu ciudad"} 🔔` : "Aviso de ciudad desactivado");
    } catch {
      setCityAlerts(!next);
      toast.error("No se pudo actualizar");
    } finally {
      setCityAlertsBusy(false);
    }
  };
  const [momentBusy, setMomentBusy] = useState(false);
  const [blockedOpen, setBlockedOpen] = useState(false);

  const savePrivacy = async (val) => {
    setPrivacy(val);
    setPrivacyBusy(true);
    try {
      const { data } = await api.put("/auth/profile", { attendance_privacy: val });
      setUser(data);
      toast.success("Privacidad actualizada");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setPrivacy(user?.attendance_privacy || "amigos");
    } finally {
      setPrivacyBusy(false);
    }
  };

  const saveMomentPrivacy = async (val) => {
    setMomentPriv(val);
    setMomentBusy(true);
    try {
      const { data } = await api.put("/auth/profile", { moment_privacy: val });
      setUser(data);
      toast.success("Privacidad del Momento actualizada");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setMomentPriv(user?.moment_privacy || "amigos");
    } finally {
      setMomentBusy(false);
    }
  };

  const { data: blocked = [], refetch: refetchBlocked } = useQuery({
    queryKey: ["blocked-users"],
    queryFn: async () => (await api.get("/me/blocked")).data,
    enabled: blockedOpen,
  });

  const unblock = async (userId) => {
    try {
      await api.post("/me/unblock", { user_id: userId });
      toast.success("Desbloqueado");
      refetchBlocked();
    } catch {
      toast.error("No se pudo desbloquear");
    }
  };

  const PRIVACY_OPTS = [
    { key: "todos", label: "Todos", icon: Eye, hint: "Sales en el recuento público y tus amigos te ven." },
    { key: "amigos", label: "Solo amigos", icon: Users2, hint: "Solo tus amigos ven a qué vas; sin anuncios." },
    { key: "nadie", label: "Nadie", icon: EyeOff, hint: "Modo fantasma: nadie ve a qué fiestas vas." },
  ];

  useEffect(() => {
    if (pushSupported) getPushStatus().then(setPushOn);
  }, [pushSupported]);

  const { data: referral } = useQuery({
    queryKey: ["referral"],
    queryFn: async () => (await api.get("/me/referral")).data,
    staleTime: 5 * 60_000,
  });

  const togglePush = async () => {
    if (!pushSupported) {
      toast.error("Tu navegador no permite avisos push aquí. Instala la app en tu pantalla de inicio y actívalos desde ahí.");
      return;
    }
    setPushBusy(true);
    try {
      if (pushOn) { await unsubscribeFromPush(); setPushOn(false); toast.success("Avisos en el móvil desactivados"); }
      else { await subscribeToPush(); setPushOn(true); toast.success("¡Avisos en el móvil activados!"); }
    } catch (e) {
      toast.error(e.message || "No se pudo cambiar los avisos");
    } finally { setPushBusy(false); }
  };

  const save = async () => {
    setSaving(true);
    const cityChanged = city !== (user?.city);
    try {
      const { data } = await api.put("/auth/profile", { name, city });
      setUser(data);
      if (cityChanged) {
        // Drop the old city's cached parties so the feed reloads instantly for
        // the new city instead of showing stale events during a slow refetch.
        queryClient.removeQueries({ queryKey: ["events"] });
        queryClient.removeQueries({ queryKey: ["carousels"] });
        queryClient.removeQueries({ queryKey: ["top-weekend"] });
        queryClient.removeQueries({ queryKey: ["genres"] });
        queryClient.invalidateQueries({ queryKey: ["venues"] });
        toast.success(`Ciudad cambiada a ${data.city} 🎉`);
      } else {
        toast.success("Perfil actualizado");
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setSaving(false); }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/upload/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await refreshUser();
      toast.success("Foto actualizada");
    } catch { toast.error("No se pudo subir la foto"); }
    finally { setUploading(false); }
  };

  const shareInvite = async () => {
    const code = referral?.code || "";
    const url = `${window.location.origin}/login?ref=${code}`;
    const text = `Únete a mí en ¿Quién va? y ambos ganamos +100 puntos. Mi código: ${code} · ${url}`;
    try {
      if (navigator.share) await navigator.share({ title: "¿Quién va?", text, url });
      else { await navigator.clipboard.writeText(text); toast.success("Enlace de invitación copiado"); }
    } catch { /* cancelled */ }
  };

  const copyCode = async () => {
    if (!referral?.code) return;
    await navigator.clipboard.writeText(referral.code);
    toast.success("Código copiado");
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4 flex items-center gap-3">
        <button onClick={() => navigate(-1)} data-testid="settings-back" className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90">
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <h1 className="font-display text-3xl font-black tracking-tighter">Ajustes<span className="text-qv-primary">.</span></h1>
      </header>

      <div className="px-5 flex flex-col items-center pb-5">
        <div className="relative">
          <AvatarCircle name={user?.name} picture={user?.picture} size={84} ring={false} />
          <button onClick={() => fileRef.current?.click()} data-testid="upload-avatar-btn" className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-qv-primary flex items-center justify-center border-2 border-[#0A0A0C]">
            {uploading ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Camera className="w-4 h-4 text-white" />}
          </button>
          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onUpload} data-testid="avatar-file-input" />
        </div>
      </div>

      <div className="px-5 flex flex-col gap-3">
        <p className="text-xs uppercase tracking-widest text-white/40 font-bold">Tu perfil</p>
        <div>
          <label className="text-xs text-white/40 font-bold">Nombre</label>
          <Input data-testid="profile-name" value={name} onChange={(e) => setName(e.target.value)} className="h-12 mt-1.5 bg-white/5 border-white/15 rounded-2xl text-white" />
        </div>
        <div>
          <label className="text-xs text-white/40 font-bold">Ciudad</label>
          <select
            data-testid="profile-city"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="w-full h-12 mt-1.5 px-3 bg-white/5 border border-white/15 rounded-2xl text-white appearance-none"
          >
            {cities.map((c) => (
              <option key={c.id} value={c.id} className="bg-[#121215] text-white">
                {c.emoji ? `${c.emoji} ` : ""}{c.label}
              </option>
            ))}
            {!cities.some((c) => c.id === city) && (
              <option value={city} className="bg-[#121215] text-white">{city}</option>
            )}
          </select>
        </div>
        <button data-testid="profile-save" onClick={save} disabled={saving} className="h-12 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60">
          {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Save className="w-4 h-4" /> Guardar cambios</>}
        </button>

        <p className="text-xs uppercase tracking-widest text-white/40 font-bold mt-3">Invitar</p>
        <button data-testid="invite-btn" onClick={shareInvite} className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95">
          <Share2 className="w-4 h-4" /> Invitar amigos {referral && <span className="text-qv-secondary text-xs">(+{referral.points_per_referral} pts)</span>}
        </button>
        {referral && (
          <button data-testid="referral-code" onClick={copyCode} className="h-12 rounded-2xl bg-qv-secondary/10 border border-qv-secondary/30 text-white font-semibold flex items-center justify-between px-4 active:scale-95">
            <span className="flex items-center gap-2 text-white/70 text-sm"><Copy className="w-4 h-4 text-qv-secondary" /> Tu código</span>
            <span className="font-mono text-qv-secondary font-bold">{referral.code}</span>
          </button>
        )}

        <p className="text-xs uppercase tracking-widest text-white/40 font-bold mt-3">Preferencias</p>
        <div className="flex items-center justify-between h-12 rounded-2xl bg-white/5 border border-white/15 px-4" data-testid="settings-language">
          <span className="flex items-center gap-2 text-white font-semibold"><Globe2 className="w-4 h-4" /> {t("lang.label")}</span>
          <LanguageSwitcher />
        </div>
        <button data-testid="push-toggle-btn" onClick={togglePush} disabled={pushBusy} className={`h-12 rounded-2xl font-semibold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60 ${pushOn ? "bg-qv-primary/15 border border-qv-primary/40 text-qv-primary" : "bg-white/5 border border-white/15 text-white"}`}>
          {pushBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : pushOn ? <><BellRing className="w-4 h-4" /> Notificaciones activadas</> : <><Bell className="w-4 h-4" /> Activar notificaciones</>}
        </button>
        <button data-testid="compact-toggle-btn" onClick={() => { setCompact(!compact); toast.success(compact ? "Vista completa activada" : "Vista compacta activada"); }} className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-between px-4 active:scale-95">
          <span className="flex items-center gap-2">{compact ? <Grid3x3 className="w-4 h-4" /> : <Rows3 className="w-4 h-4" />} Vista del feed</span>
          <span className={`text-xs px-2.5 py-1 rounded-full ${compact ? "bg-qv-secondary/20 text-qv-secondary" : "bg-white/10 text-white/70"}`}>{compact ? "Compacta" : "Completa"}</span>
        </button>
        <button data-testid="notif-prefs-btn" onClick={() => navigate("/ajustes/avisos")} className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95">
          <Bell className="w-4 h-4" /> Ajustes de avisos
        </button>
        <button data-testid="city-alerts-toggle" onClick={toggleCityAlerts} disabled={cityAlertsBusy} className="min-h-12 py-2 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-between px-4 active:scale-95 disabled:opacity-60 gap-3 text-left">
          <span className="flex items-center gap-2 min-w-0">
            <Globe2 className="w-4 h-4 shrink-0" />
            <span className="min-w-0">
              <span className="block truncate">Avisos de mi ciudad</span>
              <span className="block text-white/40 text-[11px] font-normal leading-tight">Cualquier cambio de precio o estado en {user?.city || "tu ciudad"}</span>
            </span>
          </span>
          <span className={`text-xs px-2.5 py-1 rounded-full shrink-0 ${cityAlerts ? "bg-qv-secondary/20 text-qv-secondary" : "bg-white/10 text-white/70"}`}>{cityAlerts ? "ON" : "OFF"}</span>
        </button>
        <button data-testid="archive-btn" onClick={() => setArchiveOpen(true)} className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95">
          <Archive className="w-4 h-4" /> Archivo de historias
        </button>
        <StoriesArchive open={archiveOpen} onOpenChange={setArchiveOpen} />

        <p className="text-xs uppercase tracking-widest text-white/40 font-bold mt-3">Privacidad y seguridad</p>
        <div className="rounded-2xl bg-white/5 border border-white/10 p-3" data-testid="privacy-section">
          <p className="text-sm font-semibold text-white flex items-center gap-2"><Eye className="w-4 h-4 text-qv-secondary" /> ¿Quién ve que voy?</p>
          <div className="grid grid-cols-3 gap-1.5 mt-2.5">
            {PRIVACY_OPTS.map((o) => {
              const Icon = o.icon;
              const on = privacy === o.key;
              return (
                <button
                  key={o.key}
                  data-testid={`privacy-${o.key}`}
                  onClick={() => savePrivacy(o.key)}
                  disabled={privacyBusy}
                  className={`py-2.5 rounded-xl text-xs font-bold flex flex-col items-center gap-1 border transition-colors ${on ? "bg-qv-primary/15 border-qv-primary/50 text-white" : "bg-white/5 border-white/10 text-white/60"}`}
                >
                  <Icon className="w-4 h-4" /> {o.label}
                </button>
              );
            })}
          </div>
          <p className="text-white/40 text-[11px] mt-2 leading-tight">{PRIVACY_OPTS.find((o) => o.key === privacy)?.hint}</p>
        </div>

        <div className="rounded-2xl bg-white/5 border border-white/10 p-3" data-testid="moment-privacy-section">
          <p className="text-sm font-semibold text-white flex items-center gap-2"><Zap className="w-4 h-4 text-qv-primary" /> ¿Quién ve tu Momento?</p>
          <div className="grid grid-cols-2 gap-1.5 mt-2.5">
            {[
              { key: "amigos", label: "Solo amigos", icon: Users2 },
              { key: "publico", label: "Público", icon: Globe2 },
            ].map((o) => {
              const Icon = o.icon;
              const on = momentPriv === o.key;
              return (
                <button
                  key={o.key}
                  data-testid={`moment-privacy-${o.key}`}
                  onClick={() => saveMomentPrivacy(o.key)}
                  disabled={momentBusy}
                  className={`py-2.5 rounded-xl text-xs font-bold flex flex-col items-center gap-1 border transition-colors ${on ? "bg-qv-primary/15 border-qv-primary/50 text-white" : "bg-white/5 border-white/10 text-white/60"}`}
                >
                  <Icon className="w-4 h-4" /> {o.label}
                </button>
              );
            })}
          </div>
          <p className="text-white/40 text-[11px] mt-2 leading-tight">
            {momentPriv === "publico"
              ? "Tus capturas de El Momento pueden aparecer en Descubrir para gente nueva."
              : "Modo normal: solo tus amigos ven tus capturas de El Momento."}
          </p>
        </div>
        <button data-testid="blocked-accounts-btn" onClick={() => setBlockedOpen(true)} className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95">
          <Ban className="w-4 h-4 text-red-300" /> Cuentas bloqueadas
        </button>

        <Dialog open={blockedOpen} onOpenChange={setBlockedOpen}>
          <DialogContent className="bg-[#0d0d0d] border-white/10 text-white max-w-sm rounded-2xl">
            <h3 className="font-display font-black text-lg">Cuentas bloqueadas</h3>
            {blocked.length === 0 ? (
              <p className="text-white/50 text-sm py-3">No tienes cuentas bloqueadas.</p>
            ) : (
              <div className="flex flex-col gap-2 mt-1 max-h-[50vh] overflow-y-auto">
                {blocked.map((b) => (
                  <div key={b.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-2.5" data-testid={`blocked-${b.username}`}>
                    <AvatarCircle name={b.name} picture={b.picture} size={40} ring={false} />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold truncate text-sm">{b.name}</p>
                      <p className="text-white/40 text-xs truncate">@{b.username}</p>
                    </div>
                    <button data-testid={`unblock-${b.username}`} onClick={() => unblock(b.user_id)} className="h-9 px-4 rounded-full bg-white/10 text-white/80 text-sm font-semibold active:scale-95">
                      Desbloquear
                    </button>
                  </div>
                ))}
              </div>
            )}
          </DialogContent>
        </Dialog>

        <button data-testid="logout-btn" onClick={async () => { await logout(); navigate("/login"); }} className="h-12 rounded-2xl bg-transparent border border-white/10 text-white/60 font-semibold flex items-center justify-center gap-2 active:scale-95 mt-3">
          <LogOut className="w-4 h-4" /> Cerrar sesión
        </button>
      </div>
    </AppShell>
  );
}
