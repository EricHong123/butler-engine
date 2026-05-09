/** API client for Butler Engine backend. */

const BASE_URL = '/api/backend';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── Health ──
export async function checkHealth() {
  return fetchJSON<{ status: string }>('/health');
}

// ── Review Queue ──
export interface ReviewTicket {
  ticket_id: string;
  tenant_id: string;
  from_user: string;
  customer_query: string;
  reason: string;
  priority: 'urgent' | 'standard';
  status: 'pending' | 'claimed' | 'approved' | 'rejected' | 'sent';
  claimed_by: string | null;
  created_at: string;
  elapsed_seconds: number;
  is_overdue: boolean;
}

export interface ReviewTicketDetail extends ReviewTicket {
  to_user: string;
  draft_response: string;
  final_response: string | null;
  reviewer_notes: string | null;
  claimed_at: string | null;
  resolved_at: string | null;
}

export async function listTickets(status?: string) {
  const params = status ? `?status=${status}` : '';
  return fetchJSON<{ tickets: ReviewTicket[]; total: number }>(`/review/tickets${params}`);
}

export async function getTicket(ticketId: string) {
  return fetchJSON<ReviewTicketDetail>(`/review/tickets/${ticketId}`);
}

export async function claimTicket(ticketId: string, reviewer: string) {
  return fetchJSON<{ status: string }>(
    `/review/tickets/${ticketId}/claim?reviewer=${encodeURIComponent(reviewer)}`,
    { method: 'POST' }
  );
}

export async function approveTicket(
  ticketId: string,
  finalResponse?: string,
  sendToCustomer?: boolean,
  reviewerNotes?: string
) {
  const params = new URLSearchParams();
  if (finalResponse) params.set('final_response', finalResponse);
  if (sendToCustomer) params.set('send_to_customer', 'true');
  if (reviewerNotes) params.set('reviewer_notes', reviewerNotes);
  return fetchJSON<{ status: string }>(
    `/review/tickets/${ticketId}/approve?${params.toString()}`,
    { method: 'POST' }
  );
}

export async function rejectTicket(ticketId: string, reason: string, notes?: string) {
  const params = new URLSearchParams({ reason });
  if (notes) params.set('reviewer_notes', notes);
  return fetchJSON<{ status: string }>(
    `/review/tickets/${ticketId}/reject?${params.toString()}`,
    { method: 'POST' }
  );
}

export async function getReviewStats() {
  return fetchJSON<{
    total_pending: number;
    total_claimed: number;
    urgent_pending: number;
    standard_pending: number;
    overdue: number;
    approved_today: number;
    avg_resolution_seconds: number;
  }>('/review/stats');
}
