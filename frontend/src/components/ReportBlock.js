import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { MoreVertical, Flag, Ban, Loader2 } from "lucide-react";
import { toast } from "@/lib/notify";

// value = canonical string stored/sent to backend (kept stable across languages)
const REASONS = [
  { value: "Contenido inapropiado", k: "report.reason_inappropriate" },
  { value: "Acoso o abuso", k: "report.reason_harassment" },
  { value: "Spam", k: "report.reason_spam" },
  { value: "Suplantación de identidad", k: "report.reason_impersonation" },
  { value: "Otro", k: "report.reason_other" },
];

/** Small dialog to submit a report for any target (user, moment, photo…). */
export function ReportDialog({ open, onOpenChange, targetType, targetId, targetName }) {
  const { t } = useTranslation();
  const [reason, setReason] = useState(REASONS[0].value);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/reports", { target_type: targetType, target_id: targetId, reason, note });
      toast.success(t("report.toast_thanks"));
      onOpenChange(false);
      setNote("");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#0d0d0d] border-white/10 text-white max-w-sm rounded-2xl">
        <h3 className="font-display font-black text-lg">{targetName ? t("report.title_named", { name: targetName }) : t("report.title")}</h3>
        <p className="text-white/50 text-xs -mt-1">{t("report.subtitle")}</p>
        <div className="flex flex-col gap-1.5 mt-2">
          {REASONS.map((r) => (
            <button
              key={r.value}
              data-testid={`report-reason-${r.value}`}
              onClick={() => setReason(r.value)}
              className={`text-left text-sm px-3 py-2.5 rounded-xl border transition-colors ${
                reason === r.value ? "bg-qv-primary/15 border-qv-primary/50 text-white" : "bg-white/5 border-white/10 text-white/70"
              }`}
            >
              {t(r.k)}
            </button>
          ))}
        </div>
        <textarea
          data-testid="report-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={t("report.note_ph")}
          rows={2}
          className="mt-2 w-full bg-white/5 border border-white/10 rounded-xl text-white text-sm p-3 placeholder:text-white/30"
        />
        <button
          data-testid="report-submit"
          onClick={submit}
          disabled={busy}
          className="h-12 mt-1 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Flag className="w-4 h-4" />} {t("report.submit")}
        </button>
      </DialogContent>
    </Dialog>
  );
}

/** Overflow menu for a user profile: Report + Block. */
export function UserActionsMenu({ userId, userName }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [confirmBlock, setConfirmBlock] = useState(false);
  const [busy, setBusy] = useState(false);

  const block = async () => {
    setBusy(true);
    try {
      await api.post("/me/block", { user_id: userId });
      toast.success(t("report.toast_blocked", { name: userName || t("report.default_user") }));
      setConfirmBlock(false);
      setOpen(false);
      navigate(-1);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        data-testid="user-actions-btn"
        onClick={() => setOpen(true)}
        className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center active:scale-90"
        aria-label={t("report.more_options")}
      >
        <MoreVertical className="w-5 h-5 text-white/80" />
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#0d0d0d] border-white/10 text-white max-w-xs rounded-2xl p-2">
          <button
            data-testid="menu-report-user"
            onClick={() => { setOpen(false); setReportOpen(true); }}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left text-sm font-semibold text-white/90 active:bg-white/5"
          >
            <Flag className="w-4 h-4 text-yellow-300" /> {t("report.report")}
          </button>
          <button
            data-testid="menu-block-user"
            onClick={() => { setOpen(false); setConfirmBlock(true); }}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left text-sm font-semibold text-red-300 active:bg-white/5"
          >
            <Ban className="w-4 h-4" /> {t("report.block")}
          </button>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmBlock} onOpenChange={setConfirmBlock}>
        <DialogContent className="bg-[#0d0d0d] border-white/10 text-white max-w-sm rounded-2xl">
          <h3 className="font-display font-black text-lg">{t("report.confirm_block_title", { name: userName || t("report.default_user") })}</h3>
          <p className="text-white/60 text-sm">
            {t("report.confirm_block_body")}
          </p>
          <div className="flex gap-2 mt-2">
            <button onClick={() => setConfirmBlock(false)} className="flex-1 h-12 rounded-2xl bg-white/10 text-white/80 font-bold active:scale-95">{t("report.cancel")}</button>
            <button
              data-testid="confirm-block-btn"
              onClick={block}
              disabled={busy}
              className="flex-1 h-12 rounded-2xl bg-red-500 text-white font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />} {t("report.block")}
            </button>
          </div>
        </DialogContent>
      </Dialog>

      <ReportDialog open={reportOpen} onOpenChange={setReportOpen} targetType="user" targetId={userId} targetName={userName} />
    </>
  );
}

/** Tiny inline flag button for content (moments, photos). */
export function ReportFlag({ targetType, targetId, className = "" }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <span
        role="button"
        tabIndex={0}
        data-testid="report-flag-btn"
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen(true); }}
        onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setOpen(true); } }}
        className={`inline-flex items-center justify-center cursor-pointer active:scale-90 ${className}`}
        aria-label={t("report.report_content")}
      >
        <Flag className="w-3.5 h-3.5 text-white/80" />
      </span>
      <ReportDialog open={open} onOpenChange={setOpen} targetType={targetType} targetId={targetId} />
    </>
  );
}
