// Virelo renders these 16 SVG paths through the shared Icon component.

import React from "react";

const paths = {
  snap: (
    <g>
      <rect x="2" y="2" width="5" height="12" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </g>
  ),
  folder: (
    <path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 2H13a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" />
  ),
  keyb: (
    <g>
      <rect x="1.5" y="4" width="13" height="8" rx="1.5" />
      <path d="M4 7h.01M7 7h.01M10 7h.01M4.5 10h7" />
    </g>
  ),
  general: (
    <g>
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1v2M8 13v2M15 8h-2M3 8H1M12.5 3.5l-1.4 1.4M4.9 11.1l-1.4 1.4M12.5 12.5l-1.4-1.4M4.9 4.9L3.5 3.5" />
    </g>
  ),
  about: (
    <g>
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 11V7.5M8 5.2v.01" />
    </g>
  ),
  search: (
    <g>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </g>
  ),
  cmd: (
    <path d="M5 3a2 2 0 1 1-2 2h10a2 2 0 1 1-2-2v10a2 2 0 1 1 2-2H3a2 2 0 1 1 2 2z" />
  ),
  plus: <path d="M8 3v10M3 8h10" />,
  check: <path d="M3 8.5L6.5 12 13 4.5" />,
  x: <path d="M4 4l8 8M12 4l-8 8" />,
  chev: <path d="M5 3l4 5-4 5" />,
  dot: <circle cx="8" cy="8" r="2" />,
  spark: (
    <path d="M8 2l1.5 4.5L14 8l-4.5 1.5L8 14l-1.5-4.5L2 8l4.5-1.5z" />
  ),
  play: <path d="M4 3l9 5-9 5z" />,
  reset: (
    <g>
      <path d="M3 8a5 5 0 1 0 1.5-3.5" />
      <path d="M3 3v3h3" />
    </g>
  ),
};

export function Icon({ name, size = 14 }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}
