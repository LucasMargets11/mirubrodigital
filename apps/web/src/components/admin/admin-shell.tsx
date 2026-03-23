"use client";

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { Route } from 'next';
import {
  LayoutDashboard,
  Users,
  CreditCard,
  HeadphonesIcon,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Shield,
  Menu,
  X,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { adminLogout } from '@/lib/admin/client';
import type { AdminSession, AdminSection } from '@/lib/admin/types';

type NavItem = {
  section: AdminSection;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
};

const ALL_NAV_ITEMS: NavItem[] = [
  { section: 'dashboard', label: 'Dashboard', href: '/admin/dashboard', icon: LayoutDashboard },
  { section: 'clientes', label: 'Clientes', href: '/admin/clientes', icon: Users },
  { section: 'suscripciones', label: 'Suscripciones', href: '/admin/suscripciones', icon: CreditCard },
  { section: 'soporte', label: 'Soporte', href: '/admin/soporte', icon: HeadphonesIcon },
  { section: 'blog', label: 'Blog', href: '/admin/blog', icon: FileText },
  { section: 'reportes', label: 'Reportes', href: '/admin/reportes', icon: BarChart3 },
  { section: 'configuracion', label: 'Configuración', href: '/admin/configuracion', icon: Settings },
];

const ROLE_LABELS: Record<string, string> = {
  superadmin: 'Super Admin',
  operations: 'Operaciones',
  support_agent: 'Soporte',
  content_admin: 'Contenido',
};

function AdminSidebarContent({
  session,
  onNavigate,
}: {
  session: AdminSession;
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? '/admin';
  const [isPending, startTransition] = useTransition();

  const authorizedItems = ALL_NAV_ITEMS.filter((item) =>
    session.authorized_sections.includes(item.section),
  );

  const handleLogout = () => {
    startTransition(async () => {
      try {
        await adminLogout();
        window.location.assign('/admin/login');
      } catch {
        window.location.assign('/admin/login');
      }
    });
  };

  return (
    <div className="flex h-full w-64 flex-col bg-slate-900 text-white">
      {/* Brand header */}
      <div className="border-b border-slate-700 px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Mi Rubro</p>
            <p className="text-xs text-slate-400">Panel Interno</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {authorizedItems.map((item) => {
            const isActive =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;

            return (
              <li key={item.section}>
                <Link
                  href={item.href as Route}
                  onClick={onNavigate}
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-brand-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  )}
                >
                  <Icon className="h-4.5 w-4.5 shrink-0" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User footer */}
      <div className="border-t border-slate-700 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-slate-200">
            {session.user.name
              .split(' ')
              .map((p) => p[0]?.toUpperCase())
              .slice(0, 2)
              .join('')}
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium text-slate-200">
              {session.user.name}
            </p>
            <p className="truncate text-xs text-slate-400">
              {ROLE_LABELS[session.internal_role] ?? session.internal_role}
            </p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            disabled={isPending}
            className="shrink-0 rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white disabled:opacity-50 transition-colors"
            aria-label="Cerrar sesión"
            title="Salir"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AdminShell({
  session,
  children,
}: {
  session: AdminSession;
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <AdminSidebarContent session={session} />
      </div>

      {/* Mobile drawer backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 transition-transform duration-300 md:hidden',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <AdminSidebarContent session={session} onNavigate={() => setMobileOpen(false)} />
      </div>

      {/* Main area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Mobile header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-brand-600" />
            <span className="text-sm font-semibold text-slate-900">Mi Rubro Admin</span>
          </div>
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100"
            aria-label="Menú"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
