import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import NavBar from "@/components/NavBar";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "VoiceTravel AI — Real-Time Trip Planner",
  description:
    "Plan your perfect trip using voice and AI. Multi-agent itinerary generation with real-time streaming.",
  keywords: ["travel", "AI", "voice", "trip planner", "itinerary"],
  authors: [{ name: "VoiceTravel AI" }],
  openGraph: {
    title: "VoiceTravel AI",
    description: "Plan your perfect trip with AI-powered voice assistance.",
    type: "website",
  },
};


export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${geistMono.variable} h-full antialiased`}
      style={{ colorScheme: "dark" }}
    >
      <body
        className="flex min-h-full flex-col"
        style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}
      >
        <NavBar />
        <main className="flex-1">{children}</main>
        <footer
          className="py-6 text-center text-xs"
          style={{ color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}
        >
          © {new Date().getFullYear()} VoiceTravel AI — Built with Next.js &amp; FastAPI
        </footer>
      </body>
    </html>
  );
}
