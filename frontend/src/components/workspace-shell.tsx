"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";
import { formatRole } from "@/lib/format";
import type { AuthUser } from "@/lib/types";

type WorkspaceShellProps = {
  currentUser: AuthUser;
  children: ReactNode;
};

const navItems = [
  { href: "/app", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/mappings", label: "Mappings" },
  { href: "/reports", label: "Reports" },
  { href: "/users", label: "Users" },
];

const pageLabels: Record<string, string> = {
  "/app": "Dashboard",
  "/jobs": "Jobs",
  "/mappings": "Mappings",
  "/reports": "Reports",
  "/users": "Users",
};

function NavIcon({ label }: { label: string }) {
  switch (label) {
    case "Dashboard":
      return (
        <svg viewBox="0 0 24 24">
          <path d="M4 10.5 12 4l8 6.5" />
          <path d="M6.5 9.5V20h11V9.5" />
          <path d="M10 20v-5h4v5" />
        </svg>
      );
    case "Jobs":
      return (
        <svg viewBox="0 0 24 24">
          <path d="M12 4v9" />
          <path d="M8.5 10 12 13.5 15.5 10" />
          <path d="M4.5 15.5v2A2.5 2.5 0 0 0 7 20h10a2.5 2.5 0 0 0 2.5-2.5v-2" />
          <path d="M4.5 15.5h4l1.8 2h3.4l1.8-2h4" />
        </svg>
      );
    case "Mappings":
      return (
        <svg viewBox="0 0 24 24">
          <path d="M6 6h5l3 3h4" />
          <path d="M6 18h5l3-3h4" />
          <circle cx="5" cy="6" r="2" />
          <circle cx="19" cy="9" r="2" />
          <circle cx="5" cy="18" r="2" />
          <circle cx="19" cy="15" r="2" />
        </svg>
      );
    case "Reports":
      return (
        <svg viewBox="0 0 24 24">
          <path d="M7 3h7l5 5v13H7z" />
          <path d="M14 3v5h5" />
          <path d="M10 17v-4" />
          <path d="M14 17v-7" />
          <path d="M18 17v-2" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24">
          <path d="M16 19a4 4 0 0 0-8 0" />
          <circle cx="12" cy="10" r="3" />
          <path d="M20 19a4 4 0 0 0-3-3.87" />
          <path d="M17 6.4A3 3 0 0 1 17 12" />
        </svg>
      );
  }
}

export function WorkspaceShell({ currentUser, children }: WorkspaceShellProps) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);
  const canManageUsers = currentUser.role !== "user";

  useEffect(() => {
    try {
      setSidebarCollapsed(window.localStorage.getItem("redcap-sidebar-collapsed") === "1");
    } catch {
      setSidebarCollapsed(false);
    }
  }, []);

  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", sidebarCollapsed);
    document.body.classList.toggle("sidebar-mobile-open", sidebarMobileOpen);

    return () => {
      document.body.classList.remove("sidebar-collapsed");
      document.body.classList.remove("sidebar-mobile-open");
    };
  }, [sidebarCollapsed, sidebarMobileOpen]);

  useEffect(() => {
    setSidebarMobileOpen(false);
  }, [pathname]);

  function toggleSidebarCollapsed() {
    const nextValue = !sidebarCollapsed;
    setSidebarCollapsed(nextValue);
    try {
      window.localStorage.setItem("redcap-sidebar-collapsed", nextValue ? "1" : "0");
    } catch {}
  }

  return (
    <div className="dashboard-shell app-shell">
      <button
        className="sidebar-mobile-toggle"
        type="button"
        aria-label={sidebarMobileOpen ? "Close menu" : "Open menu"}
        aria-expanded={sidebarMobileOpen}
        title={sidebarMobileOpen ? "Close menu" : "Open menu"}
        onClick={() => setSidebarMobileOpen((currentValue) => !currentValue)}
      >
        <span className="sidebar-mobile-toggle-bars" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </button>

      <div
        className="sidebar-mobile-backdrop"
        hidden={!sidebarMobileOpen}
        onClick={() => setSidebarMobileOpen(false)}
      ></div>

      <aside className="sidebar" data-sidebar>
        <button
          className="sidebar-toggle"
          type="button"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!sidebarCollapsed}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={toggleSidebarCollapsed}
        >
          <span className="sidebar-toggle-chevron" aria-hidden="true"></span>
        </button>

        <div className="brand-card">
          <div className="brand-badge">
            <BrandMark />
          </div>
          <div className="brand-copy">
            <strong>REDCap Batch Locking</strong>
            <span>{formatRole(currentUser.role)}</span>
          </div>
        </div>

        <div className="sidebar-user-card">
          <strong>{currentUser.full_name || "Authenticated User"}</strong>
          <span>{currentUser.email}</span>
        </div>

        <nav className="sidebar-nav" aria-label="Workspace navigation">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const isDisabled = item.href === "/users" && !canManageUsers;

            const content = (
              <>
                <span className="nav-icon" aria-hidden="true">
                  <NavIcon label={item.label} />
                </span>
                <span className="nav-label">{item.label}</span>
              </>
            );

            if (isDisabled) {
              return (
                <span
                  key={item.href}
                  className={`nav-item is-disabled${isActive ? " is-active" : ""}`}
                  title={item.label}
                >
                  {content}
                </span>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item${isActive ? " is-active" : ""}`}
              >
                {content}
              </Link>
            );
          })}
        </nav>

        <form action="/api/session/logout" method="post">
          <button type="submit" className="sidebar-logout">
            <span className="sidebar-button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M10 4H5v16h5" />
                <path d="M14 8l4 4-4 4" />
                <path d="M18 12H8" />
              </svg>
            </span>
            <span className="sidebar-button-label">Sign Out</span>
          </button>
        </form>
      </aside>

      <main className="dashboard-main workspace-main">
        <div className="content-column">
          <header className="topbar">
            <div>
              <div className="topbar-title-row">
                <span className="topbar-brand-icon">
                  <BrandMark />
                </span>
                <h1 className="topbar-title">REDCap Batch Locking</h1>
              </div>
              <p className="topbar-subtitle">{pageLabels[pathname] || "Workspace"}</p>
            </div>
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}
