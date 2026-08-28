// Custom tool icons — hand-drawn inline SVGs, one per tool.
// Each is a rounded-square badge with a brand color + a glyph hinting the
// tool's purpose. Rendered at any size (viewBox 0 0 64 64), theme-independent.
//
// Usage: <div v-html="toolIcons[key]" />  (or bind :innerHTML).

export const toolIcons: Record<string, string> = {
  // Manga Classifier — sorting book covers into buckets
  'manga-classifier': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#6366f1"/>
      <rect x="15" y="16" width="14" height="20" rx="2" fill="#fff"/>
      <rect x="35" y="16" width="14" height="20" rx="2" fill="#c7d2fe"/>
      <path d="M18 44h28" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
      <path d="M22 50h20" stroke="#c7d2fe" stroke-width="3" stroke-linecap="round"/>
    </svg>`,

  // Photo Classifier — a photo/mountain
  'photo-classifier': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#10b981"/>
      <rect x="14" y="16" width="36" height="28" rx="3" fill="#fff"/>
      <circle cx="24" cy="25" r="4" fill="#fbbf24"/>
      <path d="M18 40l9-11 7 8 5-5 7 8H18z" fill="#10b981"/>
    </svg>`,

  // Manga Viewer — open book
  'manga-viewer': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#f59e0b"/>
      <path d="M32 18c-5-3-12-3-16-1v27c4-2 11-2 16 1 5-3 12-3 16-1V17c-4-2-11-2-16 1z" fill="#fff"/>
      <path d="M32 18v27" stroke="#f59e0b" stroke-width="2"/>
    </svg>`,

  // Roadmap — kanban columns
  'roadmap': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#0ea5e9"/>
      <rect x="14" y="16" width="10" height="24" rx="2" fill="#fff"/>
      <rect x="27" y="16" width="10" height="16" rx="2" fill="#e0f2fe"/>
      <rect x="40" y="16" width="10" height="30" rx="2" fill="#bae6fd"/>
    </svg>`,

  // PDF Converter — document with arrows
  'pdf-converter': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#ef4444"/>
      <path d="M20 14h16l10 10v26H20z" fill="#fff"/>
      <path d="M36 14v10h10" fill="#fecaca"/>
      <text x="32" y="44" font-size="11" font-weight="700" fill="#ef4444" text-anchor="middle" font-family="sans-serif">PDF</text>
    </svg>`,

  // Unzip — box opening
  'unzip': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#8b5cf6"/>
      <path d="M16 28l16-8 16 8v18l-16 8-16-8z" fill="#fff"/>
      <path d="M16 28l16 8 16-8M32 36v18" stroke="#8b5cf6" stroke-width="2" fill="none"/>
      <path d="M28 16h8v8h-8z" fill="#ddd6fe"/>
    </svg>`,

  // Duplicate Finder — two overlapping docs
  'duplicate-finder': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#14b8a6"/>
      <rect x="18" y="14" width="22" height="28" rx="3" fill="#99f6e4"/>
      <rect x="26" y="22" width="22" height="28" rx="3" fill="#fff"/>
    </svg>`,

  // Video Duplicate Finder — film + overlap
  'video-duplicate-finder': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#db2777"/>
      <rect x="16" y="18" width="28" height="20" rx="3" fill="#fbcfe8"/>
      <rect x="24" y="26" width="26" height="20" rx="3" fill="#fff"/>
      <path d="M34 32l8 5-8 5z" fill="#db2777"/>
    </svg>`,

  // Clipboard Share — clipboard + link
  'clipboard-share': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#3b82f6"/>
      <rect x="20" y="16" width="24" height="32" rx="3" fill="#fff"/>
      <rect x="27" y="12" width="10" height="7" rx="2" fill="#bfdbfe"/>
      <path d="M27 30h10M27 37h7" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round"/>
    </svg>`,

  // Caffeinate — coffee cup
  'caffeinate': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#a16207"/>
      <path d="M18 24h22v12a11 11 0 01-22 0z" fill="#fff"/>
      <path d="M40 27h5a4 4 0 010 8h-5" stroke="#fff" stroke-width="3" fill="none"/>
      <path d="M24 14v5M31 14v5" stroke="#fde68a" stroke-width="3" stroke-linecap="round"/>
    </svg>`,

  // Browser Agent — monitor/window
  'browser-agent': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#0891b2"/>
      <rect x="14" y="16" width="36" height="26" rx="3" fill="#fff"/>
      <path d="M14 23h36" stroke="#0891b2" stroke-width="2"/>
      <circle cx="19" cy="19.5" r="1.6" fill="#0891b2"/>
      <circle cx="24" cy="19.5" r="1.6" fill="#0891b2"/>
      <path d="M26 48h12M32 42v6" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
    </svg>`,

  // Assistant — chat bubble
  'assistant': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#7c3aed"/>
      <path d="M16 20a4 4 0 014-4h24a4 4 0 014 4v14a4 4 0 01-4 4H28l-8 7v-7a4 4 0 01-4-4z" fill="#fff"/>
      <circle cx="26" cy="27" r="2.2" fill="#7c3aed"/>
      <circle cx="32" cy="27" r="2.2" fill="#7c3aed"/>
      <circle cx="38" cy="27" r="2.2" fill="#7c3aed"/>
    </svg>`,

  // File-Git — folder + sync arrows
  'file-git': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#334155"/>
      <path d="M14 22a3 3 0 013-3h9l4 4h13a3 3 0 013 3v16a3 3 0 01-3 3H17a3 3 0 01-3-3z" fill="#fff"/>
      <path d="M28 34a6 6 0 019-5m-1 9a6 6 0 01-9-5" stroke="#334155" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      <path d="M37 28v-3h-3M27 40v3h3" stroke="#334155" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    </svg>`,

  // Memory Curve — flashcard + rising memory curve
  'memory-curve': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#e11d48"/>
      <rect x="14" y="16" width="28" height="20" rx="3" fill="#fff"/>
      <path d="M19 23h18M19 29h12" stroke="#e11d48" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M16 48c6 0 6-8 12-8s6 5 10 5 8-13 12-13" stroke="#fecdd3" stroke-width="3" fill="none" stroke-linecap="round"/>
      <circle cx="50" cy="32" r="3" fill="#fff"/>
    </svg>`,

  // Knowledge Vault — connected knowledge-graph nodes
  'knowledge-vault': `
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="#0d9488"/>
      <path d="M22 22l20 6M22 22l6 20M42 28l-14 14" stroke="#99f6e4" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="22" cy="22" r="6" fill="#fff"/>
      <circle cx="44" cy="29" r="5" fill="#fff"/>
      <circle cx="29" cy="43" r="5" fill="#fff"/>
      <circle cx="47" cy="46" r="4" fill="#ccfbf1"/>
      <path d="M29 43l18 3" stroke="#99f6e4" stroke-width="2.5" stroke-linecap="round"/>
    </svg>`,
}
