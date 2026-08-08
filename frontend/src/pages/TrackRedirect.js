import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";

// Clean bio links: quienva.me/ig, quienva.me/tt (or /r/:src).
// Records the source (fire-and-forget), remembers it until the visitor signs up
// so we can attribute the registration, then drops them into the app.
export default function TrackRedirect({ source }) {
  const navigate = useNavigate();
  const params = useParams();
  useEffect(() => {
    const src = String(source || params.src || "unknown").toLowerCase().slice(0, 40);
    try { localStorage.setItem("qv_src", src); } catch { /* ignore */ }
    api.post("/track/click", { source: src }).catch(() => {});
    navigate("/feed", { replace: true });
  }, [source, params.src, navigate]);
  return null;
}
