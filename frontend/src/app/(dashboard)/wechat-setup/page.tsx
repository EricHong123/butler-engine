'use client';

import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Loader2, Copy, ExternalLink, Shield, Key, Radio, Server } from 'lucide-react';

interface StatusResponse { configured: boolean; corp_id: string; token_configured: boolean; encoding_aes_key_configured: boolean; agent_id: string; callback_url_hint: string; }
interface TestResult { test: string; status: string; detail: string; hint?: string; }

export default function WeChatSetupPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [corpId, setCorpId] = useState('');
  const [token, setToken] = useState('');
  const [aesKey, setAesKey] = useState('');
  const [agentId, setAgentId] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<TestResult[] | null>(null);
  const [saveMsg, setSaveMsg] = useState('');
  const [callbackUrl, setCallbackUrl] = useState('');

  useEffect(() => {
    fetch('/api/backend/api/wechat-setup/status').then(r => r.json()).then(setStatus);
    fetch('/api/backend/api/wechat-setup/callback-url').then(r => r.json()).then(d => setCallbackUrl(d.url));
  }, []);

  async function handleTest() {
    setTesting(true); setTestResults(null);
    try {
      const res = await fetch('/api/backend/api/wechat-setup/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ corp_id: corpId, token, encoding_aes_key: aesKey, agent_id: agentId }),
      });
      const data = await res.json();
      setTestResults(data.results);
    } catch { setTestResults([{ test: '请求失败', status: 'fail', detail: '无法连接后端' }]); }
    finally { setTesting(false); }
  }

  async function handleSave() {
    setSaving(true); setSaveMsg('');
    try {
      const res = await fetch('/api/backend/api/wechat-setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ corp_id: corpId, token, encoding_aes_key: aesKey, agent_id: agentId }),
      });
      const data = await res.json();
      setSaveMsg(data.message || '已保存');
    } catch { setSaveMsg('保存失败'); }
    finally { setSaving(false); }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="text-xl font-bold text-white flex items-center gap-2">
        <Radio size={22} style={{ color: 'var(--accent)' }} />
        企业微信接入配置
      </h2>

      {/* Status */}
      {status && (
        <div className={`card-sm flex items-center gap-3 ${
          status.configured ? 'bg-green-500/5 border-green-500/20' : 'bg-yellow-500/5 border-yellow-500/20'
        }`}>
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
            status.configured ? 'bg-green-500/10' : 'bg-yellow-500/10'
          }`}>
            {status.configured
              ? <CheckCircle size={20} className="text-green-400" />
              : <XCircle size={20} className="text-yellow-400" />}
          </div>
          <div>
            <div className="text-white font-medium">
              {status.configured ? '已配置' : '未配置'}
            </div>
            <div className="text-xs text-muted">
              Corp ID: {status.corp_id} · Token: {status.token_configured ? '已设置' : '未设置'} · AES Key: {status.encoding_aes_key_configured ? '已设置' : '未设置'}
            </div>
          </div>
        </div>
      )}

      {/* Form */}
      <div className="card space-y-4">
        <h3 className="text-white font-medium">企业微信应用凭证</h3>
        <p className="text-xs text-muted">在企业微信管理后台 (work.weixin.qq.com) → 应用管理 → 选择应用 → 获取以下信息</p>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted block mb-1">企业 Corp ID</label>
            <input value={corpId} onChange={e => setCorpId(e.target.value)}
              placeholder="ww1234567890abcdef"
              className="w-full px-3 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500/50" />
          </div>

          <div>
            <label className="text-xs text-muted block mb-1">回调 Token</label>
            <input value={token} onChange={e => setToken(e.target.value)}
              placeholder="自定义的 Token 字符串（3-32位）"
              className="w-full px-3 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500/50" />
          </div>

          <div>
            <label className="text-xs text-muted block mb-1">
              Encoding AES Key
              <span className={aesKey.length === 43 ? 'text-green-400 ml-2' : 'text-red-400 ml-2'}>
                {aesKey.length}/43
              </span>
            </label>
            <input value={aesKey} onChange={e => setAesKey(e.target.value)}
              placeholder="企业微信后台生成的 43 位随机字符串"
              maxLength={43}
              className="w-full px-3 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm font-mono focus:outline-none focus:border-blue-500/50" />
          </div>

          <div>
            <label className="text-xs text-muted block mb-1">
              Agent ID / Secret
              <span className="text-yellow-400 ml-1">（注意：是应用的 Secret，不是 AgentId 数字）</span>
            </label>
            <input value={agentId} onChange={e => setAgentId(e.target.value)}
              placeholder="企业微信应用的 Secret"
              className="w-full px-3 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500/50" />
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button onClick={handleTest} disabled={testing || !corpId}
            className="btn-secondary text-sm flex items-center gap-2 disabled:opacity-50">
            {testing ? <Loader2 size={14} className="animate-spin" /> : <Server size={14} />}
            测试连接
          </button>
          <button onClick={handleSave} disabled={saving || !corpId || !token || aesKey.length !== 43}
            className="btn-primary text-sm flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Key size={14} />}
            保存配置
          </button>
        </div>
        {saveMsg && <div className="text-sm text-green-400">{saveMsg}</div>}
      </div>

      {/* Test Results */}
      {testResults && (
        <div className="card space-y-3">
          <h3 className="text-white font-medium">测试结果</h3>
          {testResults.map((r, i) => (
            <div key={i} className={`flex items-start gap-3 p-3 rounded-lg ${
              r.status === 'pass' ? 'bg-green-500/5 border border-green-500/20' : 'bg-red-500/5 border border-red-500/20'
            }`}>
              {r.status === 'pass'
                ? <CheckCircle size={16} className="text-green-400 mt-0.5" />
                : <XCircle size={16} className="text-red-400 mt-0.5" />}
              <div>
                <div className={`text-sm font-medium ${r.status === 'pass' ? 'text-green-400' : 'text-red-400'}`}>{r.test}</div>
                <div className="text-xs text-muted mt-0.5">{r.detail}</div>
                {r.hint && <div className="text-xs text-yellow-400 mt-0.5">💡 {r.hint}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Callback URL */}
      <div className="card space-y-3">
        <h3 className="text-white font-medium flex items-center gap-2">
          <Shield size={16} style={{ color: 'var(--accent)' }} />
          回调 URL 配置
        </h3>
        <p className="text-xs text-muted">将此 URL 填入企业微信后台的「接收消息」→「设置API接收」</p>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2.5 bg-gray-900 rounded-lg text-sm text-blue-400 font-mono break-all">
            {callbackUrl || 'https://your-domain.com/wechat/callback'}
          </code>
          <button onClick={() => copyToClipboard(callbackUrl)}
            className="p-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors">
            <Copy size={14} />
          </button>
        </div>

        <div className="space-y-1.5 mt-2">
          <h4 className="text-xs font-medium text-white">设置步骤</h4>
          <div className="text-xs text-muted space-y-1">
            <p>1. 登录 <a href="https://work.weixin.qq.com" target="_blank" className="text-blue-400 inline-flex items-center gap-1 hover:underline">企业微信管理后台 <ExternalLink size={10} /></a></p>
            <p>2. 进入「应用管理」→ 选择你的应用 → 「接收消息」→ 「设置API接收」</p>
            <p>3. 填入上方 URL、Token、EncodingAESKey</p>
            <p>4. 点击「保存」— 企业微信会向回调 URL 发送验证请求</p>
            <p>5. 如果上述测试全部通过，验证将自动成功</p>
          </div>
        </div>
      </div>
    </div>
  );
}
