import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { PartyPopper, Users, Bell, ChevronRight, Sparkles } from "lucide-react";

const SLIDES = [
  {
    icon: PartyPopper,
    color: "text-qv-primary",
    title: "Descubre los planes",
    body: "Las mejores fiestas de la semana en Palma, con foto, hora, local y links directos para comprar entrada.",
  },
  {
    icon: Users,
    color: "text-qv-secondary",
    title: "Mira quién va",
    body: "Añade a tus amigos y ve al instante en qué fiesta va cada uno. Nunca más llegar solo a un sitio.",
  },
  {
    icon: Bell,
    color: "text-yellow-300",
    title: "No te pierdas el finde",
    body: "Te avisamos cuando un amigo se apunta a un plan que no viste, o cuando queda 30 minutos para el tuyo.",
  },
];

export default function Onboarding() {
  const nav = useNavigate();
  const [i, setI] = useState(0);
  const Icon = SLIDES[i].icon;

  useEffect(() => {
    // If already onboarded, skip
    if (localStorage.getItem("qv_onboarded") === "1") {
      nav("/feed", { replace: true });
    }
  }, [nav]);

  const finish = () => {
    localStorage.setItem("qv_onboarded", "1");
    nav("/feed", { replace: true });
  };

  const next = () => {
    if (i === SLIDES.length - 1) finish();
    else setI(i + 1);
  };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col px-6 py-10" data-testid="onboarding">
      <div className="flex justify-between items-center">
        <span className="text-qv-secondary text-xs font-bold uppercase tracking-widest">
          <Sparkles className="w-3.5 h-3.5 inline mr-1" /> Bienvenido
        </span>
        <button onClick={finish} className="text-white/50 text-sm">Saltar</button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center text-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.35 }}
            className="flex flex-col items-center gap-6"
          >
            <div className="w-24 h-24 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <Icon className={`w-11 h-11 ${SLIDES[i].color}`} />
            </div>
            <h1 className="font-display text-3xl font-bold text-white">{SLIDES[i].title}</h1>
            <p className="text-white/60 text-base max-w-xs leading-relaxed">{SLIDES[i].body}</p>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="flex justify-center gap-2 mb-8">
        {SLIDES.map((_, idx) => (
          <span
            key={idx}
            className={`h-1.5 rounded-full transition-all ${idx === i ? "w-8 bg-qv-primary" : "w-1.5 bg-white/20"}`}
          />
        ))}
      </div>

      <button
        data-testid="onboarding-next"
        onClick={next}
        className="h-14 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform"
      >
        {i === SLIDES.length - 1 ? "Empezar" : "Siguiente"} <ChevronRight className="w-5 h-5" />
      </button>
    </div>
  );
}
