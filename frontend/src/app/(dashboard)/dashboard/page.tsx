'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, Wallet, Building2, Landmark, PiggyBank, Loader2 } from 'lucide-react';

const iconMap: Record<string, any> = {
  piggybank: PiggyBank, trendingup: TrendingUp,
  landmark: Landmark, shield: ShieldCheck, building: Building2, wallet: Wallet,
};

function ShieldCheck({ size }: { size?: number }) {
  return (
    <svg width={size||24} height={size||24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function formatCNY(n: number) {
  if (Math.abs(n) >= 100_000_000) return `¥${(n / 100_000_000).toFixed(2)}亿`;
  if (Math.abs(n) >= 10_000) return `¥${(n / 10_000).toFixed(0)}万`;
  return `¥${n.toLocaleString()}`;
}

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/backend/api/dashboard')
      .then(r => r.json()).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={32} className="animate-spin text-muted" /></div>;
  if (!data) return <div className="text-muted text-center py-20">无法连接后端服务。请确保 backend 已启动在 localhost:8000。</div>;

  const change = data.monthly_change_pct;
  const allocation = data.allocation || [];
  const activity = data.recent_activity || [];
  const alerts = data.urgent_alerts || [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="text-xl font-bold text-white">资产总览</h2>

      <div className="card">
        <div className="flex items-baseline gap-3">
          <span className="stat-value">{data.total_value_formatted || formatCNY(data.total_value || 0)}</span>
          <span className={change >= 0 ? 'text-green-400 text-sm' : 'text-red-400 text-sm'}>
            {change >= 0 ? '+' : ''}{change}% 本月
          </span>
        </div>
        <div className="stat-label">家族总资产（含不动产估值）</div>
        <div className="flex gap-4 mt-3 text-xs text-muted">
          <span>较上月 <span className="text-green-400">+1.2%</span></span>
          <span>较年初 <span className="text-green-400">+4.8%</span></span>
          <span>覆盖约 <span className="text-white">18 年</span> 家庭支出</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {allocation.map((item: any) => {
          const Icon = iconMap[item.icon] || Wallet;
          return (
            <div key={item.label} className="card-sm flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                style={{ backgroundColor: item.color + '15', color: item.color }}>
                <Icon size={20} />
              </div>
              <div className="min-w-0">
                <div className="text-sm text-muted">{item.label}</div>
                <div className="text-lg font-semibold text-white">{formatCNY(item.value)}</div>
                <div className="text-xs text-muted">{item.pct}%</div>
                <div className="mt-2 progress-bar">
                  <div className="progress-bar-fill" style={{ width: `${item.pct}%` }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-4">近期资金变动</h3>
          <div className="space-y-3">
            {activity.map((act: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-gray-800/30 last:border-0">
                <div>
                  <div className="text-sm text-white">{act.desc}</div>
                  <div className="text-xs text-muted">{act.date}</div>
                </div>
                <div className={act.amount >= 0 ? 'text-green-400 text-sm font-medium' : 'text-red-400 text-sm font-medium'}>
                  {act.amount >= 0 ? '+' : ''}{act.amount.toLocaleString()} {act.currency}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-4">近期提醒</h3>
          <div className="space-y-3">
            {alerts.map((alert: any, i: number) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-gray-800/30"
                style={{
                  backgroundColor: alert.priority === 'urgent' ? 'rgb(220 38 38 / 0.08)' :
                    alert.priority === 'high' ? 'rgb(234 179 8 / 0.08)' : 'rgb(59 130 246 / 0.05)',
                  borderColor: alert.priority === 'urgent' ? 'rgb(220 38 38 / 0.2)' :
                    alert.priority === 'high' ? 'rgb(234 179 8 / 0.2)' : 'rgb(59 130 246 / 0.1)',
                }}>
                <span className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{
                  backgroundColor: alert.priority === 'urgent' ? '#ef4444' : alert.priority === 'high' ? '#eab308' : '#3b82f6'
                }} />
                <span className="text-sm text-gray-300">{alert.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
