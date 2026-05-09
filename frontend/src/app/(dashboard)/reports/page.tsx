'use client';

import { useEffect, useState } from 'react';
import { FileText, Download, ChevronRight, Loader2 } from 'lucide-react';

interface Report {
  id: string; title: string; type: string; date: string; summary: string; markdown?: string;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/backend/api/reports')
      .then(r => r.json())
      .then(d => setReports(d.reports || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={32} className="animate-spin text-muted" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">AI 报告</h2>
        <button className="btn-secondary text-sm">生成新报告</button>
      </div>

      <div className="space-y-4">
        {reports.map((report) => (
          <div
            key={report.id}
            className="card cursor-pointer hover:border-gray-700 transition-colors"
            onClick={() => setSelected(selected === report.id ? null : report.id)}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-gold-500/10 flex items-center justify-center shrink-0 mt-1">
                  <FileText size={18} className="text-gold-500" />
                </div>
                <div>
                  <h3 className="text-white font-medium">{report.title}</h3>
                  <p className="text-xs text-muted mt-1">{report.date}</p>
                  {(selected === report.id) && (
                    <p className="text-sm text-gray-400 mt-3">{report.summary}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
                  onClick={(e) => { e.stopPropagation(); }}
                >
                  <Download size={16} />
                </button>
                <ChevronRight
                  size={16}
                  className="text-muted transition-transform"
                  style={{ transform: selected === report.id ? 'rotate(90deg)' : undefined }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
