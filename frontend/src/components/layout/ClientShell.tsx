"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, createContext, useContext } from "react";
import { ThemeProvider } from "@/lib/theme";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";

// Mobile sidebar context
const MobileSidebarContext = createContext({
  open: false,
  toggle: () => {},
  close: () => {},
});
export const useMobileSidebar = () => useContext(MobileSidebarContext);

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated && pathname !== "/login") {
      router.replace("/login");
    } else if (isAuthenticated && pathname === "/login") {
      router.replace("/chat");
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  // Show nothing while loading auth state
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-dark-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-dark-200">Se incarca...</p>
        </div>
      </div>
    );
  }

  // Login page: no sidebar/header
  if (pathname === "/login") {
    return <>{children}</>;
  }

  // Not authenticated, waiting for redirect
  if (!isAuthenticated) {
    return null;
  }

  const sidebarCtx = {
    open: sidebarOpen,
    toggle: () => setSidebarOpen((v) => !v),
    close: () => setSidebarOpen(false),
  };

  // Authenticated: show full shell
  return (
    <MobileSidebarContext.Provider value={sidebarCtx}>
      <div className="flex h-screen overflow-hidden bg-dark-900">
        {/* Mobile overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <Sidebar mobileOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <Header />
          <main className="flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
    </MobileSidebarContext.Provider>
  );
}

export default function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AuthGuard>{children}</AuthGuard>
      </AuthProvider>
    </ThemeProvider>
  );
}
