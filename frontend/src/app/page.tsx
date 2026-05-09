'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Key, Fingerprint } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pin, setPin] = useState('');
  const [showPin, setShowPin] = useState(false);

  async function handlePasskeyLogin() {
    setLoading(true);
    setError('');

    try {
      if (!window.PublicKeyCredential) {
        throw new Error('此浏览器不支持安全密钥。请使用Safari或Chrome。');
      }

      const challenge = crypto.randomUUID();
      const credential = await navigator.credentials.get({
        publicKey: {
          challenge: new TextEncoder().encode(challenge),
          rpId: window.location.hostname,
          allowCredentials: [],
          userVerification: 'required',
          timeout: 60000,
        },
      });

      if (credential) {
        localStorage.setItem('butler_authenticated', 'true');
        localStorage.setItem('butler_user', 'passkey_user');
        router.push('/dashboard');
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '认证失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function handlePinLogin() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/backend/api/auth/login?pin=' + encodeURIComponent(pin), { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('butler_authenticated', 'true');
        localStorage.setItem('butler_token', data.token);
        localStorage.setItem('butler_user', data.display_name);
        localStorage.setItem('butler_tenant', data.tenant_id);
        router.push('/dashboard');
      } else {
        setError('PIN 不正确');
      }
    } catch {
      setError('无法连接服务器');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gold-500/10 border border-gold-500/20 mb-4">
            <Shield size={32} className="text-gold-500" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-1">家族AI管家</h1>
          <p className="text-muted text-sm">Butler Engine · 私属服务</p>
        </div>

        <div className="card space-y-5 animate-fade-in">
          {/* Primary: Hardware Key */}
          <button
            onClick={handlePasskeyLogin}
            disabled={loading}
            className="btn-primary w-full flex items-center justify-center gap-3 py-4 text-base animate-glow"
          >
            <Key size={20} />
            {loading ? '验证中...' : '使用 YubiKey / Touch ID 登录'}
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-gray-800/50" />
            <span className="text-xs text-muted">或者</span>
            <div className="flex-1 h-px bg-gray-800/50" />
          </div>

          {/* Secondary: PIN (collapsed by default) */}
          {!showPin ? (
            <button
              onClick={() => setShowPin(true)}
              className="w-full text-center text-sm text-muted hover:text-gray-300 transition-colors py-1"
            >
              使用 PIN 码登录
            </button>
          ) : (
            <div className={`space-y-3 ${error ? 'animate-shake' : ''}`}>
              <input
                type="password"
                value={pin}
                onChange={(e) => { setPin(e.target.value); setError(''); }}
                onKeyDown={(e) => e.key === 'Enter' && handlePinLogin()}
                placeholder="输入 6 位 PIN"
                maxLength={6}
                autoFocus
                className="w-full px-4 py-3.5 bg-gray-900/80 border border-gray-700 rounded-xl text-white text-center text-lg tracking-[.3em] placeholder:text-gray-600 focus:outline-none"
              />
              <button
                onClick={handlePinLogin}
                disabled={pin.length < 6}
                className="btn-primary w-full text-sm disabled:opacity-40"
              >
                登录
              </button>
              <p className="text-[10px] text-gray-600 text-center">默认 PIN: 888888</p>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-lg bg-red-500/8 border border-red-500/15 text-red-400 text-sm text-center animate-shake">
              {error}
            </div>
          )}

          <div className="pt-2 border-t border-gray-800/30">
            <p className="text-[10px] text-gray-600 text-center">
              本服务仅供授权家族成员使用 · 所有数据端到端加密
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
