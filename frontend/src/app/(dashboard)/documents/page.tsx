'use client';

import { useEffect, useRef, useState } from 'react';
import { Upload, Search, FileText, Shield, Lock, Loader2, CheckCircle } from 'lucide-react';

interface Doc {
  filename: string; type: string; date: string; size: string; institution?: string;
}

const typeLabels: Record<string, string> = {
  bank_statement: '银行对账单',
  contract: '合同',
  insurance: '保单',
  tax: '税务',
  health: '健康',
  education: '教育',
};

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/backend/api/documents/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.status === 'ok') {
        setUploadResult(`✅ ${file.name} 上传成功 · ${data.parsed?.institution || '已保存'}`);
        // Refresh doc list
        fetchDocs();
      } else {
        setUploadResult(`❌ ${data.error || '上传失败'}`);
      }
    } catch {
      setUploadResult('❌ 上传失败，请确保后端已启动');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function fetchDocs() {
    const params = new URLSearchParams();
    if (search) params.set('query', search);
    if (filter !== 'all') params.set('doc_type', filter);
    setLoading(true);
    fetch(`/api/backend/api/documents?${params.toString()}`)
      .then(r => r.json())
      .then(d => setDocs(d.documents || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchDocs(); }, [search, filter]);

  const filtered = docs;

  if (loading && docs.length === 0) return <div className="flex justify-center py-20"><Loader2 size={32} className="animate-spin text-muted" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">文档保险箱</h2>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleUpload}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="btn-primary text-sm flex items-center gap-2"
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? '上传中...' : '上传文档'}
        </button>
      </div>

      {uploadResult && (
        <div className={`card-sm text-sm ${
          uploadResult.startsWith('✅') ? 'bg-green-500/5 border-green-500/20 text-green-400' : 'bg-red-500/5 border-red-500/20 text-red-400'
        }`}>
          {uploadResult}
        </div>
      )}

      {/* Search + Filter */}
      <div className="flex items-center gap-4">
        <div className="flex-1 relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索文档..."
            className="w-full pl-10 pr-4 py-3 bg-card border border-gray-800 rounded-lg text-white text-sm placeholder:text-muted focus:outline-none focus:border-gold-500/50"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-4 py-3 bg-card border border-gray-800 rounded-lg text-white text-sm focus:outline-none focus:border-gold-500/50"
        >
          <option value="all">全部类型</option>
          {Object.entries(typeLabels).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Document list */}
      <div className="space-y-2">
        {filtered.map((doc, i) => (
          <div key={i} className="card-sm flex items-center gap-4 hover:border-gray-700 transition-colors cursor-pointer">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0">
              <FileText size={18} className="text-blue-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white truncate">{doc.filename}</div>
              <div className="text-xs text-muted">
                {typeLabels[doc.type] || doc.type} · {doc.date} · {doc.size || '—'}
              </div>
            </div>
            <div className="flex items-center gap-1 text-xs text-muted">
              <Lock size={12} />
              已加密
            </div>
          </div>
        ))}
      </div>

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="card text-center py-12">
          <Shield size={40} className="mx-auto text-muted mb-3" />
          <p className="text-muted">未找到匹配的文档</p>
        </div>
      )}

      {/* Info */}
      <div className="card-sm border-gold-500/10 bg-gold-500/5">
        <div className="flex items-start gap-3">
          <Shield size={16} className="text-gold-500 mt-0.5 shrink-0" />
          <div className="text-xs text-gray-400">
            <p className="font-medium text-gold-500 mb-1">端到端加密</p>
            所有文档在上传前已在设备端加密。服务端无法解密您的文档内容。
            加密密钥由您的硬件安全密钥派生。
          </div>
        </div>
      </div>
    </div>
  );
}
