// Pages: Window Snap, Explorer, Shortcuts, General, About.
// Each takes an `app` object with state/setters so Tweaks + palette can
// deep-link into specific settings.

import React from 'react';
import { useTokens, useTheme, ACCENTS } from './theme.jsx';
import { Toggle, Button, Card, Row, Segmented, Stepper, Slider, Kbd } from './primitives.jsx';
import { Icon } from './icons.jsx';

function KeyCapture({ value, target, bridge }) {
  const t = useTokens();
  const [capturing, setCapturing] = React.useState(false);
  const btnRef = React.useRef(null);

  React.useEffect(() => {
    if (!capturing) return;
    const onStatus = (status) => {
      if (status === 'done' || status === 'cancelled' || status === 'timeout') {
        setCapturing(false);
      }
    };
    bridge.capture_status.connect(onStatus);
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); setCapturing(false); }
    };
    window.addEventListener('keydown', onKey);
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', (e) => {
        if (btnRef.current && !btnRef.current.contains(e.target)) setCapturing(false);
      }, { once: true });
    }, 50);
    return () => {
      window.removeEventListener('keydown', onKey);
      clearTimeout(timer);
    };
  }, [capturing, bridge]);

  const handleClick = () => {
    if (capturing) return;
    setCapturing(true);
    bridge.capture_key(target, () => {});
  };

  return (
    <button ref={btnRef} onClick={handleClick} style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 64, height: 28, padding: '0 12px',
      background: t.isDark ? 'rgba(255,255,255,0.06)' : '#fff',
      border: capturing ? `2px solid ${t.accent}` : `1px solid ${t.borderHi}`,
      borderRadius: 4,
      color: capturing ? t.accent : t.text,
      fontSize: 11, fontWeight: 600, letterSpacing: 0.3,
      fontFamily: t.mono, cursor: 'pointer',
      boxShadow: t.isDark ? 'none' : '0 1px 0 rgba(0,0,0,0.04)',
      transition: 'border-color .15s, color .15s',
    }}>
      {capturing ? 'Press a key...' : value}
    </button>
  );
}

function MonitorPreview({ width, height }) {
  const t = useTokens();
  const mW = 280, mH = 170, pad = 12;
  const iw = mW - pad * 2, ih = mH - pad * 2;
  const wW = (iw * width) / 100, wH = (ih * height) / 100;
  const wX = pad + (iw - wW) / 2, wY = pad + (ih - wH) / 2;

  // If the UI accent is too dark in light mode (slate), fall back to a sky
  // blue so the rect stays visible against the dark monitor. Otherwise use
  // the accent so the preview reflects the user's choice.
  const darkAccents = ['slate'];
  const { tweaks } = useTheme();
  const rectColor = !t.isDark && darkAccents.includes(tweaks.accent) ? '#8EC4FF' : t.accent;
  const monitorBg = t.isDark ? '#0C0C0E' : '#3B3833';
  const labelOutside = true; // always above the monitor — more consistent

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: `${t.cardPad + 6}px ${t.cardPad}px ${t.cardPad + 4}px`, background: t.surface }}>
      <div style={{ position: 'relative' }}>
        <div style={{
          position: 'absolute', top: -22, left: 0, right: 0, textAlign: 'center',
          fontSize: 11, fontFamily: t.mono, color: t.textDim, fontWeight: 600,
          letterSpacing: 0.3,
        }}>{width}% × {height}%</div>
        <div style={{
          width: mW, height: mH, borderRadius: 6,
          background: monitorBg,
          border: `1px solid ${t.borderHi}`, position: 'relative', overflow: 'hidden',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
        }}>
          <svg width={mW} height={mH} style={{ position: 'absolute', inset: 0, opacity: 0.18, pointerEvents: 'none' }}>
            <defs>
              <pattern id="mp-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="0.5"/>
              </pattern>
            </defs>
            <rect width={mW} height={mH} fill="url(#mp-grid)" />
          </svg>

          <div style={{
            position: 'absolute', left: wX, top: wY, width: wW, height: wH,
            background: `${rectColor}33`,
            border: `1.5px solid ${rectColor}`,
            borderRadius: 3, transition: 'all .2s cubic-bezier(.2,.7,.3,1)',
            boxShadow: `0 0 16px ${rectColor}30`,
          }}>
            {wH >= 22 && (
              <div style={{
                height: 10, background: `${rectColor}40`,
                borderBottom: `1px solid ${rectColor}`,
                borderRadius: '2px 2px 0 0',
              }} />
            )}
          </div>


        </div>
        <div style={{ width: 70, height: 4, margin: '0 auto', background: t.borderHi, borderRadius: '0 0 3px 3px' }} />
        <div style={{ width: 120, height: 2, margin: '0 auto', background: t.border, borderRadius: 2 }} />
      </div>
    </div>
  );
}

function SnapPage({ app }) {
  const t = useTokens();
  return (
    <Pg title="Window snap" subtitle="Configure snap/restore presets and the keyboard shortcuts that trigger them.">
      <Card>
        <Row label="Enable snap" description="Resize the foreground window with a keyboard shortcut.">
          <Toggle on={app.snapEnabled} onChange={(v) => app.set({ snapEnabled: v })} />
        </Row>
        <Row label="Game mode" description="Skip snapping while a fullscreen app is in focus." last>
          <Toggle on={app.gameMode} onChange={(v) => app.set({ gameMode: v })} />
        </Row>
      </Card>

      <Card title="Shortcut" subtitle="Press the key button to rebind. Tap the bound key repeatedly to trigger.">
        <Row label="Snap key">
          <KeyCapture value={app.snapKey} target="snap" bridge={app.bridge} />
        </Row>
        <Row label="Restore key">
          <KeyCapture value={app.restoreKey} target="restore" bridge={app.bridge} />
        </Row>
        <Row label="Press count" description="How many taps trigger the action.">
          <Stepper value={app.pressCount} onChange={(v) => app.set({ pressCount: v })} min={1} max={10} />
        </Row>
        <Row label="Interval" description="Maximum time between taps." last>
          <Stepper value={app.interval} onChange={(v) => app.set({ interval: v })} min={100} max={5000} step={50} suffix="ms" />
        </Row>
      </Card>

      <Card padding={false}>
        <div style={{
          padding: `${t.rowPad + 2}px ${t.cardPad}px`,
          borderBottom: `1px solid ${t.border}`,
          background: t.surface2,
          display: 'flex', alignItems: 'center',
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: t.text, letterSpacing: -0.1 }}>Target size</div>
            <div style={{ fontSize: 12, color: t.textDim, marginTop: 2 }}>Snapped windows will match this fraction of the current display.</div>
          </div>
          <Button variant="ghost" icon={<Icon name="play" size={12} />} onClick={app.onTestSnap}>Test snap</Button>
        </div>
        <MonitorPreview width={app.width} height={app.height} />
        <div style={{ padding: `4px ${t.cardPad}px` }}>
          <Row label="Width" description={`${app.width}% of screen width`}>
            <Slider value={app.width} onChange={(v) => app.set({ width: v })} />
          </Row>
          <Row label="Height" description={`${app.height}% of screen height`} last>
            <Slider value={app.height} onChange={(v) => app.set({ height: v })} />
          </Row>
        </div>
      </Card>
    </Pg>
  );
}

function ExplorerPage({ app }) {
  return (
    <Pg title="Explorer" subtitle="Quality-of-life tweaks for File Explorer's Detail view.">
      <Card>
        <Row label="Auto-size columns on folder change" description="Resize Detail view columns to fit each time you navigate." last>
          <Toggle on={app.autoSize} onChange={(v) => app.set({ autoSize: v })} />
        </Row>
      </Card>
    </Pg>
  );
}

function ShortcutsPage({ app }) {
  const t = useTokens();
  const items = [
    { label: 'Trigger snap',       keys: [app.snapKey, app.snapKey, app.snapKey].slice(0, app.pressCount) },
    { label: 'Restore last snap',  keys: [app.restoreKey, app.restoreKey, app.restoreKey].slice(0, app.pressCount) },
    { label: 'Command palette',    keys: ['Ctrl', 'K'] },
  ];
  return (
    <Pg title="Shortcuts" subtitle="Global keyboard shortcuts registered by Virelo.">
      <Card padding={false}>
        {items.map((it, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', padding: `${t.rowPad}px ${t.cardPad}px`,
            borderBottom: i < items.length - 1 ? `1px solid ${t.border}` : 'none',
          }}>
            <div style={{ flex: 1, fontSize: 13, color: t.text }}>{it.label}</div>
            <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
              {it.keys.map((k, j) => (
                <React.Fragment key={j}>
                  {j > 0 && <span style={{ color: t.textMuted, fontSize: 11, margin: '0 1px' }}>+</span>}
                  <Kbd>{k}</Kbd>
                </React.Fragment>
              ))}
            </div>
          </div>
        ))}
      </Card>
    </Pg>
  );
}

function GeneralPage({ app }) {
  const t = useTokens();
  const [confirmReset, setConfirmReset] = React.useState(false);

  React.useEffect(() => {
    if (!confirmReset) return;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); setConfirmReset(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmReset]);

  return (
    <Pg title="General" subtitle="Application-wide preferences.">
      <Card title="Appearance">
        <Row label="Theme" description="Light or dark surfaces throughout the app.">
          <Segmented options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]}
            value={app.themeMode} onChange={(v) => app.set({ themeMode: v })} />
        </Row>
        <Row label="Accent color" description="Used for selection, toggles, and primary actions.">
          <div style={{ display: 'flex', gap: 6 }}>
            {Object.entries(ACCENTS).map(([k, v]) => (
              <button key={k} onClick={() => app.set({ accent: k })}
                style={{
                  width: 22, height: 22, borderRadius: 11,
                  background: t.isDark ? v.dark : v.light,
                  border: app.accent === k ? `2px solid ${t.text}` : `1px solid ${t.border}`,
                  cursor: 'pointer', padding: 0,
                }}/>
            ))}
          </div>
        </Row>
        <Row label="Density" description="Controls spacing throughout the app." last>
          <Segmented options={[{ value: 'compact', label: 'Compact' }, { value: 'cozy', label: 'Cozy' }, { value: 'comfortable', label: 'Comfortable' }]}
            value={app.density} onChange={(v) => app.set({ density: v })} />
        </Row>
      </Card>

      <Card title="Startup">
        <Row label="Launch at login" description="Start Virelo when you sign in to Windows." last>
          <Toggle on={app.launchLogin} onChange={(v) => app.set({ launchLogin: v })} />
        </Row>
      </Card>

      <Card title="Advanced">
        <Row label="Reset all settings" description="Restore every preference to its default value." last>
          <Button variant="danger" size="sm" onClick={() => setConfirmReset(true)}>Reset</Button>
        </Row>
      </Card>

      {confirmReset && (
        <div onClick={() => setConfirmReset(false)} style={{
          position: 'fixed', inset: 0, zIndex: 50,
          background: t.overlay, backdropFilter: 'blur(2px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width: 360, background: t.surface,
            border: `1px solid ${t.borderHi}`, borderRadius: t.radius + 4,
            boxShadow: '0 20px 60px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.08)',
            padding: `${t.cardPad + 4}px ${t.cardPad}px`,
          }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: t.text, marginBottom: 8 }}>Reset all settings?</div>
            <div style={{ fontSize: 13, color: t.textDim, lineHeight: 1.5, marginBottom: 20 }}>
              This will restore every preference to its default value. This cannot be undone.
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="secondary" onClick={() => setConfirmReset(false)}>Cancel</Button>
              <Button variant="danger" onClick={() => { app.onReset(); setConfirmReset(false); }}>Reset</Button>
            </div>
          </div>
        </div>
      )}
    </Pg>
  );
}

function AboutPage() {
  const t = useTokens();
  return (
    <Pg title="About" subtitle="Virelo -- a tiny utility for snappier windows.">
      <Card padding={false}>
        <div style={{ padding: `${t.cardPad + 4}px ${t.cardPad}px`, display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{
            width: 56, height: 56, borderRadius: t.radius + 4,
            background: t.accent, color: t.accentOn,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 26, fontWeight: 700, letterSpacing: -1,
          }}>V</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 600, color: t.text, letterSpacing: -0.3 }}>Virelo</div>
            <div style={{ fontSize: 12.5, color: t.textDim, marginTop: 2 }}>
              Version {__APP_VERSION__}
            </div>
          </div>
        </div>
      </Card>
      <Card>
        <Row label="License" description="MIT" last>
          <Button variant="ghost" size="sm">View</Button>
        </Row>
      </Card>
    </Pg>
  );
}

function Pg({ title, subtitle, children }) {
  const t = useTokens();
  return (
    <div>
      <div style={{ marginBottom: t.sectionGap + 6 }}>
        <div style={{ fontSize: t.titleSize, fontWeight: 600, letterSpacing: -0.3, color: t.text }}>{title}</div>
        {subtitle && <div style={{ fontSize: 13, color: t.textDim, marginTop: 4, maxWidth: 560, lineHeight: 1.5 }}>{subtitle}</div>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: t.sectionGap }}>
        {children}
      </div>
    </div>
  );
}

export { SnapPage, ExplorerPage, ShortcutsPage, GeneralPage, AboutPage, MonitorPreview, Pg };
