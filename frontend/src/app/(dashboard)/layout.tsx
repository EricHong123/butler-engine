'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  FileText,
  FolderOpen,
  ShieldCheck,
  MessageSquare,
  LogOut,
  Menu,
  X,
  Palette,
  Radio,
} from 'lucide-react';
import clsx from 'clsx';

const navItems = [
  { href: '/chat', label: 'AI 对话', icon: MessageSquare },
  { href: '/dashboard', label: '资产总览', icon: LayoutDashboard },
  { href: '/reports', label: 'AI 报告', icon: FileText },
  { href: '/documents', label: '文档保险箱', icon: FolderOpen },
  { href: '/review', label: '审核队列', icon: ShieldCheck },
  { href: '/wechat-setup', label: '企业微信接入', icon: Radio },
];

const themes = [
  { id: 'dark-gold', label: '鎏金', color: '#D4A83C' },
  { id: 'midnight-blue', label: '午夜蓝', color: '#60A5FA' },
  { id: 'forest-green', label: '翡翠绿', color: '#4ADE80' },
  { id: 'warm-amber', label: '暖琥珀', color: '#FB923C' },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState('dark-gold');

  useEffect(() => {
    setMounted(true);
    const savedTheme = localStorage.getItem('butler_theme') || 'dark-gold';
    setTheme(savedTheme);
    document.documentElement.setAttribute('data-theme', savedTheme);
    if (typeof window !== 'undefined' && !localStorage.getItem('butler_authenticated')) {
      router.push('/');
    }
  }, [router]);

  function switchTheme(themeId: string) {
    setTheme(themeId);
    localStorage.setItem('butler_theme', themeId);
    document.documentElement.setAttribute('data-theme', themeId);
  }

  useEffect(() => {
    setMounted(true);
    if (typeof window !== 'undefined' && !localStorage.getItem('butler_authenticated')) {
      router.push('/');
    }
  }, [router]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-50 w-64 bg-card border-r border-gray-800/50 flex flex-col transition-transform lg:relative lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="p-6 border-b border-gray-800/50">
          <h1 className="text-lg font-bold text-white">家族AI管家</h1>
          <p className="text-xs text-muted mt-1">Butler Engine</p>
        </div>

        <nav className="flex-1 p-4 space-y-1 sidebar-nav">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <a
                key={item.href}
                href={item.href}
                className={clsx(
                  'flex items-center gap-3 px-4 py-3 rounded-lg text-sm',
                  isActive
                    ? 'active'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                )}
              >
                <item.icon size={18} />
                {item.label}
              </a>
            );
          })}
        </nav>

        {/* Theme Switcher */}
        <div className="px-4 py-3 border-t border-gray-800/50">
          <div className="flex items-center gap-2 text-xs text-muted mb-2">
            <Palette size={12} />
            主题配色
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {themes.map((t) => (
              <button
                key={t.id}
                onClick={() => switchTheme(t.id)}
                title={t.label}
                className="h-8 rounded-lg transition-all border-2"
                style={{
                  backgroundColor: t.color + '20',
                  borderColor: theme === t.id ? t.color : 'transparent',
                }}
              >
                <span
                  className="block w-3 h-3 rounded-full mx-auto"
                  style={{ backgroundColor: t.color }}
                />
              </button>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-gray-800/50">
          <button
            onClick={() => {
              localStorage.removeItem('butler_authenticated');
              router.push('/');
            }}
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-gray-800/50 w-full transition-colors"
          >
            <LogOut size={18} />
            退出登录
          </button>
        </div>
      </aside>

      {/* Backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main */}
      <main className="flex-1 min-w-0">
        {/* Top bar */}
        <div className="sticky top-0 z-30 bg-surface/80 backdrop-blur border-b border-gray-800/50 px-6 py-4 flex items-center gap-4">
          <button
            className="lg:hidden text-gray-400 hover:text-white"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="flex-1" />
          <div className="text-sm text-muted">洪氏家族 · 旗舰版</div>
        </div>

        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
