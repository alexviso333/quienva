import { useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { LogOut, Camera, Share2, Shield, Loader2, Save, Bell, BellRing, Flame, Archive, Grid3x3, Rows3 } from "lucide-react";
import { toast } from "sonner";
import { isPushSupported, getPushStatus, subscribeToPush, unsubscribeFromPush } from "@/lib/push";
import { StoriesArchive } from "@/components/Stories";
import { useCompactMode } from "@/hooks/useCompactMode";

export default function Profile() {
  const { user, setUser, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [name, setName] = useState(user?.name || "");
  const [city, setCity] = useState(user?.city || "Palma de Mallorca");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [pushOn, setPushOn] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [streak, setStreak] = useState(0);
  const [streakLoaded, setStreakLoaded] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [compact, setCompact] = useCompactMode();
  const pushSupported = isPushSupported();

  useEffect(() => {
    if (pushSupported) getPushStatus().then(setPushOn);
  }, [pushSupported]);

  useEffect(() => {
    api.get("/me/streak")
      .then(({ data }) => setStreak(data.streak))
      .catch(() => {})
      .finally(() => setStreakLoaded(true));
  }, []);

  const togglePush = async () => {
    setPushBusy(true);
    try {
      if (pushOn) {
        await unsubscribeFromPush();
        setPushOn(false);
        toast.success("Avisos en el móvil desactivados");
      } else {
        await subscribeToPush();
        setPushOn(true);
        toast.success("¡Avisos en el móvil activados!");
      }
    } catch (e) {
      toast.error(e.message || "No se pudo cambiar los avisos");
    } finally {
      setPushBusy(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/auth/profile", { name, city });
      setUser(data);
      toast.success("Perfil actualizado");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
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
    } catch {
      toast.error("No se pudo subir la foto");
    } finally {
      setUploading(false);
    }
  };

  const shareInvite = async () => {
    const link = `${window.location.origin}/login?add=${user?.username}`;
    const text = `Únete a mí en ¿Quién va? y te añado como amigo: ${link}`;
    try {
      if (navigator.share) await navigator.share({ title: "¿Quién va?", text, url: link });
      else {
        await navigator.clipboard.writeText(link);
        toast.success("Enlace de invitación copiado");
      }
    } catch {
      /* share cancelled */
    }
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4">
        <h1 className="font-display text-4xl font-black tracking-tighter">
          Perfil<span className="text-qv-primary">.</span>
        </h1>
      </header>

      <div className="px-5 flex flex-col items-center pt-2 pb-6">
        <div className="relative">
          <AvatarCircle name={user?.name} picture={user?.picture} size={96} ring={false} testid="profile-avatar" />
          <button
            data-testid="upload-avatar-btn"
            onClick={() => fileRef.current?.click()}
            className="absolute -bottom-1 -right-1 w-9 h-9 rounded-full bg-qv-primary flex items-center justify-center border-2 border-[#0A0A0C]"
          >
            {uploading ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Camera className="w-4 h-4 text-white" />}
          </button>
          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onUpload} data-testid="avatar-file-input" />
        </div>
        <p className="mt-4 text-xl font-bold">{user?.name}</p>
        <p className="text-white/40 text-sm">@{user?.username}</p>
      </div>

      <div className="px-5 mb-2">
        {streakLoaded && (
        <div
          data-testid="streak-card"
          className="relative rounded-2xl overflow-hidden border border-qv-primary/40 bg-[#1a0a12] p-4 flex items-center gap-4"
        >
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_left,_rgba(255,0,85,0.22),transparent_65%)]" />
          <div className="relative w-14 h-14 rounded-2xl bg-qv-primary/20 flex items-center justify-center shrink-0">
            <Flame className="w-7 h-7 text-qv-primary" style={{ filter: "drop-shadow(0 0 8px rgba(255,0,85,0.7))" }} />
          </div>
          <div className="relative">
            <p className="font-display text-3xl font-black leading-none" data-testid="streak-count">
              {streak}
            </p>
            <p className="text-sm text-white/70 mt-1">
              {streak === 0
                ? "Empieza tu racha este finde 🔥"
                : `finde${streak > 1 ? "s" : ""} seguido${streak > 1 ? "s" : ""} saliendo`}
            </p>
          </div>
        </div>
        )}
      </div>

      <div className="px-5 flex flex-col gap-3">
        <div>
          <label className="text-xs uppercase tracking-widest text-white/40 font-bold">Nombre</label>
          <Input
            data-testid="profile-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-12 mt-1.5 bg-white/5 border-white/15 rounded-2xl text-white"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-widest text-white/40 font-bold">Ciudad</label>
          <Input
            data-testid="profile-city"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="h-12 mt-1.5 bg-white/5 border-white/15 rounded-2xl text-white"
          />
        </div>
        <button
          data-testid="profile-save"
          onClick={save}
          disabled={saving}
          className="h-12 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
        >
          {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Save className="w-4 h-4" /> Guardar cambios</>}
        </button>

        <button
          data-testid="invite-btn"
          onClick={shareInvite}
          className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform"
        >
          <Share2 className="w-4 h-4" /> Invitar amigos
        </button>

        <button
          data-testid="archive-btn"
          onClick={() => setArchiveOpen(true)}
          className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform"
        >
          <Archive className="w-4 h-4" /> Archivo de historias
        </button>
        <StoriesArchive open={archiveOpen} onOpenChange={setArchiveOpen} />

        {pushSupported && (
          <button
            data-testid="push-toggle-btn"
            onClick={togglePush}
            disabled={pushBusy}
            className={`h-12 rounded-2xl font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60 ${
              pushOn
                ? "bg-qv-primary/15 border border-qv-primary/40 text-qv-primary"
                : "bg-white/5 border border-white/15 text-white"
            }`}
          >
            {pushBusy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : pushOn ? (
              <><BellRing className="w-4 h-4" /> Avisos en el móvil activados</>
            ) : (
              <><Bell className="w-4 h-4" /> Activar avisos en el móvil</>
            )}
          </button>
        )}

        <button
          data-testid="compact-toggle-btn"
          onClick={() => {
            setCompact(!compact);
            toast.success(compact ? "Vista completa activada" : "Vista compacta activada");
          }}
          className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-between px-4 active:scale-95 transition-transform"
        >
          <span className="flex items-center gap-2">
            {compact ? <Grid3x3 className="w-4 h-4" /> : <Rows3 className="w-4 h-4" />}
            Vista del feed
          </span>
          <span className={`text-xs px-2.5 py-1 rounded-full ${compact ? "bg-qv-secondary/20 text-qv-secondary" : "bg-white/10 text-white/70"}`}>
            {compact ? "Compacta" : "Completa"}
          </span>
        </button>

        {user?.role === "admin" && (
          <button
            data-testid="admin-panel-btn"
            onClick={() => navigate("/admin")}
            className="h-12 rounded-2xl bg-qv-secondary/15 border border-qv-secondary/40 text-qv-secondary font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform"
          >
            <Shield className="w-4 h-4" /> Panel de administración
          </button>
        )}

        <button
          data-testid="logout-btn"
          onClick={async () => {
            await logout();
            navigate("/login");
          }}
          className="h-12 rounded-2xl bg-transparent border border-white/10 text-white/60 font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform mt-2"
        >
          <LogOut className="w-4 h-4" /> Cerrar sesión
        </button>
      </div>
    </AppShell>
  );
}
