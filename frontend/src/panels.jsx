// Command palette (Ctrl/Cmd+K) for Virelo.

import React from 'react';
import { useTokens } from './theme.jsx';
import { Kbd } from './primitives.jsx';
import { Icon } from './icons.jsx';

function CommandPalette({ open, onClose, app, setNav, onTestSnap, onSave }) {
  const t = useTokens();
  const [q, setQ] = React.useState('');
  const [idx, setIdx] = React.useState(0);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (open) { setQ(''); setIdx(0); setTimeout(() => inputRef.current?.focus(), 30); }
  }, [open]);

  const commands = React.useMemo(() => [
    { grp: 'Navigate', label: 'Go to Window snap',       run: () => setNav('snap'),     icon: 'snap' },
    { grp: 'Navigate', label: 'Go to Explorer',          run: () => setNav('exp'),      icon: 'folder' },
    { grp: 'Navigate', label: 'Go to Shortcuts',         run: () => setNav('keys'),     icon: 'keyb' },
    { grp: 'Navigate', label: 'Go to General',           run: () => setNav('gen'),      icon: 'general' },
    { grp: 'Navigate', label: 'Go to About',             run: () => setNav('about'),    icon: 'about' },
    { grp: 'Actions',  label: 'Test snap',               run: () => onTestSnap?.(),     icon: 'play', kbd: '⏎' },
    { grp: 'Actions',  label: 'Save changes',            run: () => onSave?.(),         icon: 'check' },
    { grp: 'Actions',  label: app.snapEnabled ? 'Disable snap' : 'Enable snap', run: () => app.set({ snapEnabled: !app.snapEnabled }), icon: 'dot' },
    { grp: 'Actions',  label: app.gameMode ? 'Disable game mode' : 'Enable game mode', run: () => app.set({ gameMode: !app.gameMode }), icon: 'dot' },
    { grp: 'Theme',    label: 'Theme: System', run: () => app.set({ themeMode: 'system' }), icon: 'spark' },
    { grp: 'Theme',    label: 'Theme: Light',  run: () => app.set({ themeMode: 'light' }),  icon: 'spark' },
    { grp: 'Theme',    label: 'Theme: Dark',   run: () => app.set({ themeMode: 'dark' }),   icon: 'spark' },
    { grp: 'Theme',    label: 'Accent: Slate',  run: () => app.set({ accent: 'slate' }),  icon: 'dot' },
    { grp: 'Theme',    label: 'Accent: Teal',   run: () => app.set({ accent: 'teal' }),   icon: 'dot' },
    { grp: 'Theme',    label: 'Accent: Blue',   run: () => app.set({ accent: 'blue' }),   icon: 'dot' },
    { grp: 'Theme',    label: 'Accent: Rust',   run: () => app.set({ accent: 'rust' }),   icon: 'dot' },
    { grp: 'Theme',    label: 'Accent: Purple', run: () => app.set({ accent: 'purple' }), icon: 'dot' },
  ], [app, setNav, onTestSnap, onSave]);

  const filtered = q.trim()
    ? commands.filter(c => c.label.toLowerCase().includes(q.toLowerCase()))
    : commands;

  const groups = {};
  filtered.forEach(c => { (groups[c.grp] = groups[c.grp] || []).push(c); });

  React.useEffect(() => { setIdx(0); }, [q]);
  React.useEffect(() => {
    if (!open) return;
    const on = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(filtered.length - 1, i + 1)); }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setIdx(i => Math.max(0, i - 1)); }
      if (e.key === 'Enter') { e.preventDefault(); filtered[idx]?.run(); onClose(); }
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [open, filtered, idx, onClose]);

  if (!open) return null;
  let i = -1;
  return (
    <div onClick={onClose} style={{
      position: 'absolute', inset: 0, zIndex: 50,
      background: t.overlay, backdropFilter: 'blur(2px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 80,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 480, background: t.surface,
        border: `1px solid ${t.borderHi}`, borderRadius: t.radius + 4,
        boxShadow: '0 20px 60px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.08)',
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
        maxHeight: 420,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 14px', borderBottom: `1px solid ${t.border}`,
        }}>
          <span style={{ color: t.textDim }}><Icon name="search" size={15} /></span>
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search settings, jump to…"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              color: t.text, fontSize: 14, fontFamily: 'inherit',
            }}/>
          <Kbd>Esc</Kbd>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: t.textMuted, fontSize: 13 }}>
              No results for "{q}"
            </div>
          )}
          {Object.entries(groups).map(([grp, items]) => (
            <div key={grp}>
              <div style={{
                padding: '6px 14px 2px', fontSize: 10, fontWeight: 600,
                color: t.textMuted, textTransform: 'uppercase', letterSpacing: 0.8,
              }}>{grp}</div>
              {items.map((c) => {
                i++;
                const active = i === idx;
                return (
                  <div key={c.label} onClick={() => { c.run(); onClose(); }}
                    onMouseEnter={() => setIdx(i)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '8px 14px', cursor: 'pointer',
                      background: active ? t.accentBg : 'transparent',
                      color: active ? t.accent : t.text,
                    }}>
                    <span style={{ color: active ? t.accent : t.textDim }}><Icon name={c.icon} size={13} /></span>
                    <span style={{ flex: 1, fontSize: 13 }}>{c.label}</span>
                    {c.kbd && <Kbd>{c.kbd}</Kbd>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div style={{
          padding: '8px 14px', borderTop: `1px solid ${t.border}`,
          background: t.surface2, display: 'flex', alignItems: 'center', gap: 12,
          fontSize: 11, color: t.textMuted,
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Kbd>{'↑'}</Kbd><Kbd>{'↓'}</Kbd> navigate</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Kbd>{'⏎'}</Kbd> select</span>
          <div style={{ flex: 1 }} />
          <span>Virelo {__APP_VERSION__}</span>
        </div>
      </div>
    </div>
  );
}

export { CommandPalette };
