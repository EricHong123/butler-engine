'use client';

import { useEffect, useState } from 'react';
import { Clock, AlertTriangle, CheckCircle, XCircle, User, RefreshCw } from 'lucide-react';
import type { ReviewTicket, ReviewTicketDetail } from '@/lib/api-client';
import { listTickets, getTicket, claimTicket, approveTicket, rejectTicket, getReviewStats } from '@/lib/api-client';

export default function ReviewPage() {
  const [tickets, setTickets] = useState<ReviewTicket[]>([]);
  const [selected, setSelected] = useState<ReviewTicketDetail | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [reviewResponse, setReviewResponse] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const [ticketList, reviewStats] = await Promise.all([
        listTickets(),
        getReviewStats(),
      ]);
      setTickets(ticketList.tickets);
      setStats(reviewStats);
    } catch {
      // API not available — use mock data
      setTickets([
        {
          ticket_id: 'REV-A1B2C3D4',
          tenant_id: 'zhang-family',
          from_user: 'hong_xiansheng',
          customer_query: '我应该现在卖掉北京的房产吗？现在的市场情况如何？',
          reason: 'major_financial',
          priority: 'urgent',
          status: 'pending',
          claimed_by: null,
          created_at: new Date().toISOString(),
          elapsed_seconds: 120,
          is_overdue: false,
        },
        {
          ticket_id: 'REV-E5F6G7H8',
          tenant_id: 'zhang-family',
          from_user: 'hong_xiansheng',
          customer_query: '帮我看一下最近有没有税务方面的问题需要注意',
          reason: 'tax_advice',
          priority: 'standard',
          status: 'pending',
          claimed_by: null,
          created_at: new Date(Date.now() - 600000).toISOString(),
          elapsed_seconds: 600,
          is_overdue: false,
        },
      ]);
      setStats({
        total_pending: 2,
        total_claimed: 1,
        urgent_pending: 1,
        standard_pending: 1,
        overdue: 0,
        approved_today: 3,
        avg_resolution_seconds: 245,
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function handleSelect(ticketId: string) {
    try {
      const detail = await getTicket(ticketId);
      setSelected(detail);
      setReviewResponse(detail.draft_response || '');
    } catch {
      // Mock detail
      const t = tickets.find((t) => t.ticket_id === ticketId);
      if (t) {
        setSelected({
          ...t,
          to_user: 'agent_001',
          draft_response: '根据当前北京房地产市场分析，您的朝阳区房产目前市值约¥1200万，年租金回报率约5%。考虑到近期政策调控和您的整体资产配置，建议暂持观望。如需详细分析，我可为您安排与房产顾问的视频会议。',
          final_response: null,
          reviewer_notes: null,
          claimed_at: null,
          resolved_at: null,
        });
        setReviewResponse('');
      }
    }
  }

  async function handleClaim(ticketId: string) {
    await claimTicket(ticketId, 'reviewer');
    refresh();
    if (selected?.ticket_id === ticketId) {
      setSelected({ ...selected, status: 'claimed', claimed_by: 'reviewer' } as ReviewTicketDetail);
    }
  }

  async function handleApprove(ticketId: string) {
    await approveTicket(ticketId, reviewResponse || undefined, true, reviewNotes);
    setSelected(null);
    setReviewResponse('');
    setReviewNotes('');
    refresh();
  }

  async function handleReject(ticketId: string) {
    await rejectTicket(ticketId, reviewNotes || '需要修改回复');
    setSelected(null);
    setReviewNotes('');
    refresh();
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">审核队列</h2>
        <button onClick={refresh} className="btn-secondary text-sm flex items-center gap-2">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card-sm">
            <div className="stat-value text-red-400">{stats.total_pending}</div>
            <div className="stat-label">待审核</div>
          </div>
          <div className="card-sm">
            <div className="stat-value text-yellow-400">{stats.urgent_pending}</div>
            <div className="stat-label">紧急</div>
          </div>
          <div className="card-sm">
            <div className="stat-value text-green-400">{stats.approved_today}</div>
            <div className="stat-label">今日已审核</div>
          </div>
          <div className="card-sm">
            <div className="stat-value text-blue-400">{stats.avg_resolution_seconds}s</div>
            <div className="stat-label">平均响应</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Ticket list */}
        <div className="lg:col-span-1 space-y-2">
          {tickets.map((ticket) => (
            <div
              key={ticket.ticket_id}
              onClick={() => handleSelect(ticket.ticket_id)}
              className={`card-sm cursor-pointer transition-colors ${
                selected?.ticket_id === ticket.ticket_id
                  ? 'border-gold-500/30 bg-gold-500/5'
                  : 'hover:border-gray-700'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted font-mono">{ticket.ticket_id}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  ticket.priority === 'urgent'
                    ? 'bg-red-500/10 text-red-400'
                    : 'bg-blue-500/10 text-blue-400'
                }`}>
                  {ticket.priority === 'urgent' ? '紧急' : '标准'}
                </span>
              </div>
              <p className="text-sm text-white line-clamp-2 mb-2">{ticket.customer_query}</p>
              <div className="flex items-center gap-3 text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {Math.floor(ticket.elapsed_seconds / 60)}分钟
                </span>
                {ticket.is_overdue && (
                  <span className="flex items-center gap-1 text-red-400">
                    <AlertTriangle size={12} /> 超时
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Ticket detail */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted font-mono">{selected.ticket_id}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  selected.status === 'pending' ? 'bg-yellow-500/10 text-yellow-400' :
                  selected.status === 'claimed' ? 'bg-blue-500/10 text-blue-400' :
                  selected.status === 'approved' ? 'bg-green-500/10 text-green-400' :
                  'bg-gray-500/10 text-gray-400'
                }`}>
                  {selected.status === 'pending' ? '待审核' :
                   selected.status === 'claimed' ? '审核中' :
                   selected.status === 'approved' ? '已通过' : selected.status}
                </span>
              </div>

              <div>
                <div className="text-xs text-muted mb-1">客户询问</div>
                <p className="text-white text-sm">{selected.customer_query}</p>
              </div>

              <div>
                <div className="text-xs text-muted mb-1">AI 草稿回复</div>
                <p className="text-gray-300 text-sm bg-gray-800/50 rounded-lg p-3">
                  {selected.draft_response}
                </p>
              </div>

              {selected.status === 'pending' && (
                <button
                  onClick={() => handleClaim(selected.ticket_id)}
                  className="btn-primary text-sm flex items-center gap-2"
                >
                  <User size={14} />
                  认领审核
                </button>
              )}

              {selected.status === 'claimed' && (
                <div className="space-y-4">
                  <textarea
                    value={reviewResponse || selected.draft_response}
                    onChange={(e) => setReviewResponse(e.target.value)}
                    rows={4}
                    className="w-full p-3 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-gold-500/50 resize-none"
                    placeholder="编辑最终回复..."
                  />
                  <input
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    className="w-full p-3 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-gold-500/50"
                    placeholder="审核备注（可选）"
                  />
                  <div className="flex gap-3">
                    <button
                      onClick={() => handleApprove(selected.ticket_id)}
                      className="btn-primary text-sm flex items-center gap-2"
                    >
                      <CheckCircle size={14} />
                      通过并发送
                    </button>
                    <button
                      onClick={() => handleReject(selected.ticket_id)}
                      className="btn-secondary text-sm flex items-center gap-2 text-red-400"
                    >
                      <XCircle size={14} />
                      驳回重写
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="card text-center py-16">
              <ShieldIcon size={48} className="mx-auto text-muted mb-3" />
              <p className="text-muted">选择一个工单查看详情</p>
              <p className="text-xs text-muted mt-1">
                {tickets.length} 个待审核工单
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ShieldIcon({ size, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
