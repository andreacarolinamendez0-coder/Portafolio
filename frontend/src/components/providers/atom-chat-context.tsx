"use client";
import { createContext, useContext, useEffect, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
import { useRouter } from "next/navigation";

export interface AtomMsg { role: "user" | "bot"; text: string }

interface AtomChatContextValue {
  msgs: AtomMsg[];
  setMsgs: Dispatch<SetStateAction<AtomMsg[]>>;
}

const AtomChatContext = createContext<AtomChatContextValue | null>(null);

// Persiste la conversación con Atom por portafolio (localStorage) para que
// sobreviva a cambios de pestaña y a un refresh -- antes vivía en un
// useState local de bot/page.tsx y se perdía apenas el usuario navegaba.
export function AtomChatProvider({ archivo, children }: { archivo: string; children: ReactNode }) {
  const storageKey = `atom-chat-${archivo}`;
  const [msgs, setMsgs] = useState<AtomMsg[]>([]);
  const [cargado, setCargado] = useState(false);

  useEffect(() => {
    setCargado(false);
    try {
      const raw = localStorage.getItem(storageKey);
      setMsgs(raw ? JSON.parse(raw) : []);
    } catch {
      setMsgs([]);
    }
    setCargado(true);
  }, [storageKey]);

  useEffect(() => {
    if (!cargado) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(msgs));
    } catch {
      // localStorage lleno o no disponible -- la conversación sigue
      // funcionando en memoria, solo no persiste entre sesiones.
    }
  }, [msgs, storageKey, cargado]);

  return <AtomChatContext.Provider value={{ msgs, setMsgs }}>{children}</AtomChatContext.Provider>;
}

export function useAtomChat() {
  const ctx = useContext(AtomChatContext);
  if (!ctx) throw new Error("useAtomChat debe usarse dentro de AtomChatProvider");
  return ctx;
}

// Mismas claves que NAVEGAR_DESTINOS en dashboard.py (_tool_navegar) -- el
// backend valida y devuelve la clave corta, el frontend la traduce a ruta.
const RUTAS_NAVEGAR: Record<string, string> = {
  dashboard: "",
  analista: "/analista",
  seguimiento: "/seguimiento",
  monitor: "/monitor",
  config: "/config",
};

// Logica de envio compartida entre la pagina completa (bot/page.tsx) y el
// launcher flotante (asistente-flotante.tsx) -- ambos leen/escriben el mismo
// historial via useAtomChat, asi que una conversacion empezada en uno
// continua en el otro sin duplicar la llamada a /api/bot.
export function useAtomSend(archivo: string) {
  const { msgs, setMsgs } = useAtomChat();
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function send(texto: string) {
    const userMsg = texto.trim();
    if (!userMsg || loading) return;
    setMsgs(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);
    try {
      const historial = msgs.map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
      historial.push({ role: "user", content: userMsg });
      const res = await fetch(`/api/bot/${archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje: userMsg, historial }),
      });
      const data = await res.json();
      setMsgs(m => [...m, { role: "bot", text: data.respuesta ?? "Sin respuesta" }]);

      if (data.accion?.tipo === "navegar" && data.accion.destino in RUTAS_NAVEGAR) {
        router.push(`/portafolio/${archivo}${RUTAS_NAVEGAR[data.accion.destino]}`);
      }
    } catch {
      setMsgs(m => [...m, { role: "bot", text: "Error de conexión." }]);
    } finally {
      setLoading(false);
    }
  }

  return { msgs, loading, send };
}
