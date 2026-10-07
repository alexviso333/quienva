// Avisos de la app.
//
// Decisión de producto: los "toasts" de CONFIRMACIÓN (verdes, arriba) molestan
// más de lo que ayudan — si cancelas un plan ya ves que se cancela, no hace
// falta un cartel diciendo "Plan actualizado". Así que se anulan en toda la app.
//
// Los ERRORES sí se mantienen: si algo falla hay que enterarse.
//
// El panel de /admin sigue importando `sonner` directamente, porque ahí sí
// quieres confirmación explícita de cada acción.
import { toast as sonnerToast } from "sonner";

const noop = () => undefined;

export const toast = Object.assign(noop, {
  success: noop,
  info: noop,
  warning: noop,
  message: noop,
  loading: noop,
  custom: noop,
  // Los errores pasan tal cual.
  error: (...args) => sonnerToast.error(...args),
  dismiss: (...args) => sonnerToast.dismiss(...args),
  promise: (p) => p,
});

export default toast;
