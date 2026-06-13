"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getSupabaseClient, signOut } from "@/lib/auth";
import type { User } from "@supabase/supabase-js";

export default function NavBar() {
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const supabase = getSupabaseClient();
    
    // Fetch initial user
    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user);
    });

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const handleSignOut = async () => {
    setMenuOpen(false);
    await signOut();
  };

  // Extract initial for avatar placeholder
  const displayName =
    user?.user_metadata?.display_name ||
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    (user?.email ? user.email.split("@")[0]?.replace(/[._-]+/g, " ")
      .split(" ")
      .filter(Boolean)
      .map((w: string) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ") : "");
  const initial = displayName ? displayName.charAt(0).toUpperCase() : (user?.email?.charAt(0).toUpperCase() ?? "?");
  const avatarUrl = user?.user_metadata?.avatar_url;

  return (
    <header
      className="sticky top-0 z-50 w-full"
      style={{
        background: "rgba(10, 10, 15, 0.85)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <nav
        className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4"
        aria-label="Main navigation"
      >
        {/* Left Branding */}
        <Link href="/" className="flex flex-col group">
          <span className="text-xl font-extrabold tracking-tight transition-colors" style={{ color: "var(--accent)" }}>
            PlanMyTrip AI
          </span>
          <span className="text-[8px] font-bold tracking-widest text-gray-500 uppercase mt-[-2px]">
            YOUR PERSONAL AI VOICE TRAVEL PLANNER
          </span>
        </Link>

        {/* Middle Links */}
        <div className="hidden md:flex items-center gap-8" role="menubar">
          <Link
            href={user ? "/travel-plans" : "/login"}
            role="menuitem"
            className="flex flex-col items-center group transition-colors"
          >
            <span className={`text-[13px] font-semibold ${pathname === "/travel-plans" ? "text-[#e03e52]" : "text-gray-200 group-hover:text-white"}`}>
              MyTravelPlan
            </span>
            <span className="text-[7px] font-semibold text-gray-400 tracking-wider uppercase">
              MANAGE YOUR PREFERENCES
            </span>
          </Link>

          <Link
            href={user ? "/dashboard" : "/login"}
            role="menuitem"
            className="flex flex-col items-center group transition-colors"
          >
            <span className={`text-[13px] font-semibold ${pathname === "/dashboard" ? "text-[#e03e52]" : "text-gray-200 group-hover:text-white"}`}>
              Trip Dashboard
            </span>
          </Link>
        </div>

        {/* Right Authentication Area */}
        <div className="flex items-center gap-4">
          {user ? (
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setMenuOpen(!menuOpen)}
                className="flex h-9 w-9 items-center justify-center rounded-full overflow-hidden border border-gray-700 hover:border-pink-500 transition-colors focus:outline-none"
                aria-label="User menu"
              >
                {avatarUrl ? (
                  <img
                    src={avatarUrl}
                    alt={user.email ?? "Avatar"}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div
                    className="flex h-full w-full items-center justify-center font-bold text-sm text-white"
                    style={{ background: "linear-gradient(135deg, #e03e52, #ff4e50)" }}
                  >
                    {initial}
                  </div>
                )}
              </button>

              {/* Dropdown Menu */}
              {menuOpen && (
                <div
                  className="absolute right-0 mt-2 w-48 rounded-lg shadow-lg py-1 border border-gray-800 animate-fade-in"
                  style={{ background: "var(--bg-surface)" }}
                >
                  <div className="px-4 py-2 border-b border-gray-800/80">
                    <p className="text-xs text-gray-400 truncate">Signed in as</p>
                    {displayName && (
                      <p className="text-sm font-bold text-white truncate">{displayName}</p>
                    )}
                    <p className="text-xs text-gray-400 truncate">{user.email}</p>
                  </div>
                  <Link
                    href="/travel-plans"
                    onClick={() => setMenuOpen(false)}
                    className="block px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
                  >
                    My Travel Plans
                  </Link>
                  <Link
                    href="/dashboard"
                    onClick={() => setMenuOpen(false)}
                    className="block px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
                  >
                    Trip Dashboard
                  </Link>
                  <Link
                    href="/planner"
                    onClick={() => setMenuOpen(false)}
                    className="block px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
                  >
                    Plan a Trip
                  </Link>
                  <button
                    type="button"
                    onClick={handleSignOut}
                    className="w-full text-left block px-4 py-2 text-sm text-red-400 hover:bg-gray-800 hover:text-red-300 transition-colors border-t border-gray-800/80 mt-1"
                  >
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link
              href="/login"
              className="btn rounded-full px-5 py-1.5 text-xs font-semibold hover:scale-105 transition-transform"
              style={{
                background: "#ffffff",
                color: "#0a0a0f",
                boxShadow: "0 4px 12px rgba(255, 255, 255, 0.1)",
              }}
            >
              Sign-In
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}
