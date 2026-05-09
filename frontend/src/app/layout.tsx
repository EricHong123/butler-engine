import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '家族AI管家 · Butler Engine',
  description: '高净值私人AI管家 — 家族专属AI私享服务',
  viewport: 'width=device-width, initial-scale=1, viewport-fit=cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        {/* Static CSS — NEVER processed by build pipeline, cannot break */}
        <link rel="stylesheet" href="/components.css" />
        {/* Theme init — runs before React hydrates */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('butler_theme')||'dark-gold';document.documentElement.setAttribute('data-theme',t)}catch(e){}})()`,
          }}
        />
      </head>
      <body className="min-h-screen">
        {/* SVG noise filter — single instance, reused by CSS */}
        <svg width="0" height="0" style={{position:'absolute'}} aria-hidden="true">
          <filter id="grain-filter">
            <feTurbulence type="fractalNoise" baseFrequency=".65" numOctaves="3" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
            <feComponentTransfer>
              <feFuncA type="linear" slope=".08" />
            </feComponentTransfer>
          </filter>
        </svg>
        {/* Global grain overlay */}
        <div className="grain-overlay" aria-hidden="true" />
        <a href="#main-content" className="skip-link">跳转到主内容</a>
        <div id="main-content" style={{position:'relative',zIndex:1}}>{children}</div>
      </body>
    </html>
  );
}
