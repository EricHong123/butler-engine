'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { Send, Wrench, ChevronDown, ChevronRight, Bot, User, Trash2, Loader2, Sparkles } from 'lucide-react';

// ── Types ──

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  toolCalls?: ToolCall[];
  timestamp: number;
}

interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: string;
  status: 'running' | 'done' | 'error';
}

interface Agent {
  agent_type: string;
  display_name: string;
  description: string;
  when_to_use: string;
  icon: string;
  color: string;
}

// ── SSE Streaming ──

async function* streamChat(
  message: string,
  conversationId: string | null,
  agentType: string,
): AsyncGenerator<{ type: string; data: unknown; conversation_id?: string }> {
  const response = await fetch('/api/backend/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId, agent_type: agentType }),
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6));
        } catch {
          // Skip malformed
        }
      }
    }
  }
}

// ── Component ──

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [chatConfig, setChatConfig] = useState<{ provider: string; model: string; has_api_key: boolean } | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>('butler');
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('/api/backend/api/config').then(r => r.json()).then(setChatConfig).catch(() => {});
    fetch('/api/backend/api/agents').then(r => r.json()).then(d => {
      setAgents(d.agents);
      if (d.default) setSelectedAgent(d.default);
    }).catch(() => {});
  }, []);

  const currentAgent = agents.find(a => a.agent_type === selectedAgent);

  function switchAgent(agentType: string) {
    if (agentType === selectedAgent) return;
    setSelectedAgent(agentType);
    setMessages([]);
    setConversationId(null);
    setShowAgentPicker(false);
    // Reset conversation on backend
    fetch(`/api/backend/api/conversations/reset?agent_type=${agentType}`, { method: 'POST' }).catch(() => {});
  }

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [streaming]);

  function addMessage(msg: Message) {
    setMessages((prev) => [...prev, msg]);
  }

  function updateLastAssistant(updater: (msg: Message) => Message) {
    setMessages((prev) => {
      const idx = prev.length - 1;
      if (idx < 0 || prev[idx].role !== 'assistant') return prev;
      const updated = [...prev];
      updated[idx] = updater(updated[idx]);
      return updated;
    });
  }

  function toggleToolExpand(toolId: string) {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(toolId)) next.delete(toolId);
      else next.add(toolId);
      return next;
    });
  }

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    addMessage(userMsg);
    setInput('');
    setStreaming(true);

    // Placeholder assistant message
    const assistantId = crypto.randomUUID();
    addMessage({
      id: assistantId,
      role: 'assistant',
      content: '',
      toolCalls: [],
      timestamp: Date.now(),
    });

    try {
      for await (const event of streamChat(text, conversationId, selectedAgent)) {
        if (event.conversation_id && !conversationId) {
          setConversationId(event.conversation_id);
        }

        switch (event.type) {
          case 'text_delta': {
            const delta = String(event.data || '');
            updateLastAssistant((msg) => ({
              ...msg,
              content: msg.content + delta,
            }));
            break;
          }

          case 'tool_call': {
            const tc = event.data as { id: string; name: string; input: Record<string, unknown> };
            updateLastAssistant((msg) => ({
              ...msg,
              toolCalls: [
                ...(msg.toolCalls || []),
                {
                  id: tc.id,
                  name: tc.name,
                  input: tc.input,
                  status: 'running' as const,
                },
              ],
            }));
            // Auto-expand new tool
            setExpandedTools((prev) => { const next = new Set(prev); next.add(tc.id); return next; });
            break;
          }

          case 'tool_result': {
            const tr = event.data as { tool_use_id: string; result: string };
            updateLastAssistant((msg) => ({
              ...msg,
              toolCalls: msg.toolCalls?.map((tc) =>
                tc.id === tr.tool_use_id
                  ? { ...tc, result: tr.result, status: 'done' as const }
                  : tc
              ),
            }));
            break;
          }

          case 'error': {
            const errText = String(event.data || 'Unknown error');
            updateLastAssistant((msg) => ({
              ...msg,
              content: msg.content + `\n\n⚠️ ${errText}`,
            }));
            break;
          }

          case 'done':
            break;
        }
      }
    } catch (err) {
      updateLastAssistant((msg) => ({
        ...msg,
        content: msg.content + `\n\n❌ 连接错误: ${err instanceof Error ? err.message : 'Unknown'}`,
      }));
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, streaming, conversationId]);

  function handleReset() {
    fetch(`/api/backend/api/conversations/reset?agent_type=${selectedAgent}`, { method: 'POST' }).catch(() => {});
    setMessages([]);
    setConversationId(null);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // ── Render ──

  const toolNameLabels: Record<string, string> = {
    query_assets: '查询资产',
    check_tax_calendar: '税务日历',
    search_docs: '搜索文档',
    schedule_event: '日程管理',
    generate_report: '生成报告',
    escalate_to_human: '转人工审核',
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-6rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          {/* Agent selector + Model badge */}
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Bot size={22} style={{ color: 'var(--accent)' }} />
              AI 管家对话
            </h2>

            {/* Agent picker button */}
            {agents.length > 0 && (
              <div className="relative">
                <button
                  onClick={() => setShowAgentPicker(!showAgentPicker)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border"
                  style={{
                    backgroundColor: (currentAgent?.color || '#D4A83C') + '15',
                    borderColor: (currentAgent?.color || '#D4A83C') + '30',
                    color: currentAgent?.color || '#D4A83C',
                  }}
                >
                  <span>{currentAgent?.icon || '🤖'}</span>
                  <span>{currentAgent?.display_name || '管家'}</span>
                  <ChevronDown size={14} />
                </button>

                {/* Dropdown */}
                {showAgentPicker && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowAgentPicker(false)} />
                    <div className="absolute top-full left-0 mt-2 w-72 bg-card border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                      <div className="p-2 text-xs text-muted border-b border-gray-800">
                        切换专业顾问
                      </div>
                      {agents.map((agent) => (
                        <button
                          key={agent.agent_type}
                          onClick={() => switchAgent(agent.agent_type)}
                          className={`w-full flex items-start gap-3 px-3 py-3 text-left hover:bg-gray-800/50 transition-colors ${
                            selectedAgent === agent.agent_type ? 'bg-gray-800/30' : ''
                          }`}
                        >
                          <span className="text-xl mt-0.5">{agent.icon}</span>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-white font-medium">{agent.display_name}</div>
                            <div className="text-xs text-muted mt-0.5">{agent.description}</div>
                            <div className="text-[10px] text-gray-700 mt-1">{agent.when_to_use}</div>
                          </div>
                          {selectedAgent === agent.agent_type && (
                            <Sparkles size={14} style={{ color: agent.color }} />
                          )}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Model badge */}
            {chatConfig && (
              <span title={`${chatConfig.provider} / ${chatConfig.model}`}
                className={`w-2 h-2 rounded-full inline-block ${
                  chatConfig.has_api_key ? 'bg-green-400' : 'bg-yellow-400'
                }`} />
            )}
          </div>

          <p className="text-xs text-muted">
            {currentAgent && (
              <span style={{ color: currentAgent.color }}>
                {currentAgent.icon} {currentAgent.display_name}
              </span>
            )}
            {currentAgent && ' · '}
            {conversationId ? `会话: ${conversationId.slice(0, 8)}...` : '新会话'}
            {chatConfig && !chatConfig.has_api_key &&
              ' · 配置 API Key 后切换真实模型'}
          </p>
        </div>
        <button
          onClick={handleReset}
          className="btn-secondary text-sm flex items-center gap-2"
          title="新会话"
        >
          <Trash2 size={14} />
          新会话
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4">
        {messages.length === 0 && (
          <div className="text-center py-16">
            <Bot size={48} className="mx-auto text-gray-700 mb-4" />
            <p className="text-muted mb-1">开始与您的私人 AI 管家对话</p>
            <p className="text-xs text-gray-700">
              支持查询资产、检查税务、搜索文档、管理日程、生成报告
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {['查一下我的资产情况', '最近有什么税务截止日', '帮我约下周五和律师见面'].map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}
                  className="px-3 py-1.5 text-xs rounded-full bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className="space-y-2">
            {/* User message */}
            {msg.role === 'user' && (
              <div className="flex items-start gap-3 justify-end msg-user">
                <div className="max-w-[80%]">
                  <div className="rounded-2xl rounded-br-md px-4 py-3" style={{ backgroundColor: 'var(--accent-bg)', borderColor: 'var(--accent-border)', border: '1px solid var(--accent-border)' }}>
                    <p className="text-white text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                  <p className="text-[10px] text-gray-600 text-right mt-1 mr-1">{new Date(msg.timestamp).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'})}</p>
                </div>
                <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ backgroundColor: 'var(--accent-bg)' }}>
                  <User size={14} style={{ color: 'var(--accent)' }} />
                </div>
              </div>
            )}

            {/* Assistant message */}
            {msg.role === 'assistant' && (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0 mt-1">
                  <Bot size={14} className="text-blue-400" />
                </div>
                <div className="max-w-[85%] space-y-2">
                  {/* Text content */}
                  {msg.content && (
                    <div className="bg-card border border-gray-800/50 rounded-2xl rounded-bl-md px-4 py-3">
                      <p className="text-gray-200 text-sm whitespace-pre-wrap leading-relaxed">
                        {msg.content}
                        {streaming && msg.id === messages[messages.length - 1]?.id && (
                          <span className="inline-block w-2 h-4 bg-gold-500 animate-pulse ml-0.5 align-middle" />
                        )}
                      </p>
                    </div>
                  )}

                  {/* Tool calls */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="space-y-1.5">
                      {msg.toolCalls.map((tc) => (
                        <div
                          key={tc.id}
                          className="rounded-lg border border-gray-700/50 bg-gray-900/50 overflow-hidden"
                        >
                          {/* Tool header */}
                          <button
                            onClick={() => toggleToolExpand(tc.id)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-800/50 transition-colors"
                          >
                            {tc.status === 'running' ? (
                              <Loader2 size={12} className="text-yellow-400 animate-spin" />
                            ) : tc.status === 'error' ? (
                              <Wrench size={12} className="text-red-400" />
                            ) : (
                              <Wrench size={12} className="text-green-400" />
                            )}
                            <span className="text-gray-400 font-mono text-[11px]">
                              {toolNameLabels[tc.name] || tc.name}
                            </span>
                            <span className="flex-1" />
                            {expandedTools.has(tc.id) ? (
                              <ChevronDown size={12} className="text-muted" />
                            ) : (
                              <ChevronRight size={12} className="text-muted" />
                            )}
                          </button>

                          {/* Tool details */}
                          {expandedTools.has(tc.id) && (
                            <div className="px-3 pb-2 space-y-1.5">
                              <div>
                                <div className="text-[10px] text-muted mb-0.5">Input</div>
                                <pre className="text-[11px] text-gray-400 bg-black/30 rounded p-2 overflow-x-auto font-mono">
                                  {JSON.stringify(tc.input, null, 2)}
                                </pre>
                              </div>
                              {tc.result && (
                                <div>
                                  <div className="text-[10px] text-muted mb-0.5">Result</div>
                                  <pre className="text-[11px] text-green-400/80 bg-black/30 rounded p-2 overflow-x-auto font-mono max-h-32 overflow-y-auto">
                                    {tc.result.length > 500
                                      ? tc.result.slice(0, 500) + '...'
                                      : tc.result}
                                  </pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Streaming spinner (no content yet, tool running) */}
                  {streaming &&
                    msg.id === messages[messages.length - 1]?.id &&
                    !msg.content &&
                    (!msg.toolCalls || msg.toolCalls.length === 0) && (
                      <div className="flex items-center gap-2 text-muted text-xs px-1">
                        <Loader2 size={12} className="animate-spin" />
                        思考中...
                      </div>
                    )}
                </div>
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0">
        <div className="flex items-end gap-3 bg-card border border-gray-800 rounded-2xl p-3 focus-within:border-gold-500/30 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
            rows={1}
            disabled={streaming}
            className="flex-1 bg-transparent text-white text-sm placeholder:text-muted resize-none focus:outline-none max-h-32"
            style={{ minHeight: '1.5rem' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              backgroundColor: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
            }}
          >
            {streaming ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-muted text-center mt-2">
          所有对话内容端到端加密 · 敏感回复经人工审核后发送
        </p>
      </div>
    </div>
  );
}
