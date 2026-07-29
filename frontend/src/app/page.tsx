"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { authMe, getPortafolios } from "@/lib/api";

/**
 * Portero. Decide a donde mandar al usuario. Nunca se ve como pantalla:
 *   - Sin sesion            -> /login
 *   - Con sesion, 0 portaf. -> /bienvenida (crear el primero)
 *   - Con sesion, N portaf. -> /portafolio/<ultimo usado o el primero>
 *
 * Reemplaza a la vieja pagina /portafolios como punto de entrada. Cualquier
 * router.push("/") del resto de la app aterriza aqui y se resuelve solo.
 */
export default function Root() {
  const router = useRouter();

  useEffect(() => {
    (async () => {
      try {
        const me = await authMe();
        if (!me.authenticated) { router.replace("/login"); return; }

        const { portafolios } = await getPortafolios();
        if (portafolios.length === 0) { router.replace("/bienvenida"); return; }

        const ultimo = typeof window !== "undefined" ? localStorage.getItem("ultimoPortafolio") : null;
        const existe = ultimo && portafolios.some(p => p.archivo === ultimo);
        router.replace(`/portafolio/${existe ? ultimo : portafolios[0].archivo}`);
      } catch {
        router.replace("/login");
      }
    })();
  }, [router]);

  // Pantalla de transicion mientras decide (se ve un instante)
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>
    </div>
  );
}