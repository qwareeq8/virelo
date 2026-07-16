// Theme tokens + context for Virelo.
// Exposes: ThemeProvider, useTheme, useTokens.
// Tweakable knobs (theme, accent, density, radius, sidebarMode) live here.

import React from 'react';

const ACCENTS = {
  slate:  { light: '#1C1A16', dark: '#E6E4DF', bgL: '#E8E6E1', bgD: 'rgba(255,255,255,0.12)' },
  teal:   { light: '#2E6F5E', dark: '#6DD4B5', bgL: '#E7F0EC', bgD: 'rgba(109,212,181,0.14)' },
  blue:   { light: '#1E4FC9', dark: '#7AA8FF', bgL: '#E6EDFB', bgD: 'rgba(122,168,255,0.14)' },
  rust:   { light: '#B4421F', dark: '#FF9273', bgL: '#FBEAE3', bgD: 'rgba(255,146,115,0.14)' },
  purple: { light: '#5B3FB8', dark: '#A593FF', bgL: '#ECE8FA', bgD: 'rgba(165,147,255,0.14)' },
};

const LIGHT = {
  bg:        '#FAF9F7',
  surface:   '#FFFFFF',
  surface2:  '#FCFBF9',
  sidebar:   '#F4F2EE',
  border:    '#EAE7E1',
  borderHi:  '#D9D4CA',
  text:      '#1C1A16',
  textDim:   '#6C6760',
  textMuted: '#9A948B',
  hover:     'rgba(0,0,0,0.04)',
  track:     '#E3DED4',
  shadow:    '0 1px 1px rgba(0,0,0,0.02)',
  overlay:   'rgba(20,18,14,0.25)',
};

const DARK = {
  bg:        '#111113',
  surface:   '#18181B',
  surface2:  '#1D1D20',
  sidebar:   '#131315',
  border:    'rgba(255,255,255,0.07)',
  borderHi:  'rgba(255,255,255,0.12)',
  text:      '#ECECEE',
  textDim:   '#9B9BA3',
  textMuted: '#6B6B74',
  hover:     'rgba(255,255,255,0.05)',
  track:     'rgba(255,255,255,0.08)',
  shadow:    '0 1px 1px rgba(0,0,0,0.3)',
  overlay:   'rgba(0,0,0,0.5)',
};

const DENSITIES = {
  compact:     { rowPad: 10, sectionGap: 10, cardPad: 14, fontBase: 12.5, titleSize: 18 },
  cozy:        { rowPad: 14, sectionGap: 14, cardPad: 18, fontBase: 13,   titleSize: 20 },
  comfortable: { rowPad: 18, sectionGap: 18, cardPad: 22, fontBase: 13.5, titleSize: 22 },
};

const FONT = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

const ThemeCtx = React.createContext(null);

function ThemeProvider({ tweaks, setTweaks, children }) {
  const palette = tweaks.theme === 'dark' ? DARK : LIGHT;
  const accentDef = ACCENTS[tweaks.accent] || ACCENTS.slate;
  const density = DENSITIES[tweaks.density] || DENSITIES.cozy;
  const tokens = {
    ...palette,
    accent: tweaks.theme === 'dark' ? accentDef.dark : accentDef.light,
    accentBg: tweaks.theme === 'dark' ? accentDef.bgD : accentDef.bgL,
    accentOn: tweaks.theme === 'dark' ? '#111113' : '#fff',
    ...density,
    radius: tweaks.radius,
    font: FONT,
    mono: MONO,
    isDark: tweaks.theme === 'dark',
  };
  const api = React.useMemo(() => ({ tokens, tweaks, setTweaks }), [tokens, tweaks]);
  return <ThemeCtx.Provider value={api}>{children}</ThemeCtx.Provider>;
}

function useTheme() { return React.useContext(ThemeCtx); }
function useTokens() { return React.useContext(ThemeCtx).tokens; }

export { ThemeProvider, useTheme, useTokens, ACCENTS, LIGHT, DARK, DENSITIES, FONT, MONO };
