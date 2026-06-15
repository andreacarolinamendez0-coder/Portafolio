import type { Metadata } from "next";
import { DM_Sans, Geist } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-dm-sans",
});

export const metadata: Metadata = {
  title: "Sistema de Portafolio",
  description: "Gestión inteligente de inversiones",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={cn("dark", "h-full", dmSans.variable, "font-sans", geist.variable)}>
      <body
        className="min-h-full flex flex-col"
        style={{ fontFamily: "var(--font-dm-sans), -apple-system, BlinkMacSystemFont, sans-serif" }}
      >
        {children}
      </body>
    </html>
  );
}
