// Command palette (Ctrl/Cmd+K) for Virelo.

import React from "react";
import { useTokens } from "./theme.jsx";
import { Kbd } from "./primitives.jsx";
import { Icon } from "./icons.jsx";

function CommandPalette({ open, onClose, app, setNav, onTestSnap, onSave }) {
  const t = useTokens();
  const gameMode = app.gameMode;
  const setApp = app.set;
  const snapEnabled = app.snapEnabled;
  const unsaved = app.unsaved;
  const saving = app.saving;
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef(null);
  const dialogRef = React.useRef(null);
  const returnFocusRef = React.useRef(null);
  const rowRefs = React.useRef([]);
  const listboxId = React.useId();

  React.useEffect(() => {
    if (!open) return undefined;
    returnFocusRef.current = document.activeElement;
    setQuery("");
    setActiveIndex(0);
    const timer = setTimeout(() => inputRef.current?.focus(), 30);
    return () => {
      clearTimeout(timer);
      const previous = returnFocusRef.current;
      if (previous?.isConnected) previous.focus();
      else document.querySelector("main, [role='main'], button")?.focus();
    };
  }, [open]);

  const commands = React.useMemo(
    () => [
      {
        grp: "Navigate",
        label: "Go to Window snap",
        run: () => setNav("snap"),
        icon: "snap",
      },
      {
        grp: "Navigate",
        label: "Go to Explorer",
        run: () => setNav("exp"),
        icon: "folder",
      },
      {
        grp: "Navigate",
        label: "Go to Shortcuts",
        run: () => setNav("keys"),
        icon: "keyb",
      },
      {
        grp: "Navigate",
        label: "Go to General",
        run: () => setNav("gen"),
        icon: "general",
      },
      {
        grp: "Navigate",
        label: "Go to About",
        run: () => setNav("about"),
        icon: "about",
      },
      {
        grp: "Actions",
        label: "Test snap",
        run: () => onTestSnap?.(),
        icon: "play",
        kbd: "Enter",
      },
      ...(unsaved && !saving
        ? [
            {
              grp: "Actions",
              label: "Save changes",
              run: () => onSave?.(),
              icon: "check",
            },
          ]
        : []),
      {
        grp: "Actions",
        label: snapEnabled ? "Disable snap" : "Enable snap",
        run: () => setApp({ snapEnabled: !snapEnabled }),
        icon: "dot",
      },
      {
        grp: "Actions",
        label: gameMode ? "Disable game mode" : "Enable game mode",
        run: () => setApp({ gameMode: !gameMode }),
        icon: "dot",
      },
      {
        grp: "Theme",
        label: "Theme: System",
        run: () => setApp({ themeMode: "system" }),
        icon: "spark",
      },
      {
        grp: "Theme",
        label: "Theme: Light",
        run: () => setApp({ themeMode: "light" }),
        icon: "spark",
      },
      {
        grp: "Theme",
        label: "Theme: Dark",
        run: () => setApp({ themeMode: "dark" }),
        icon: "spark",
      },
      {
        grp: "Theme",
        label: "Accent: Slate",
        run: () => setApp({ accent: "slate" }),
        icon: "dot",
      },
      {
        grp: "Theme",
        label: "Accent: Teal",
        run: () => setApp({ accent: "teal" }),
        icon: "dot",
      },
      {
        grp: "Theme",
        label: "Accent: Blue",
        run: () => setApp({ accent: "blue" }),
        icon: "dot",
      },
      {
        grp: "Theme",
        label: "Accent: Rust",
        run: () => setApp({ accent: "rust" }),
        icon: "dot",
      },
      {
        grp: "Theme",
        label: "Accent: Purple",
        run: () => setApp({ accent: "purple" }),
        icon: "dot",
      },
    ],
    [gameMode, onSave, onTestSnap, saving, setApp, setNav, snapEnabled, unsaved],
  );

  const normalizedQuery = query.trim().toLowerCase();
  const filtered = React.useMemo(
    () =>
      normalizedQuery
        ? commands.filter((command) => command.label.toLowerCase().includes(normalizedQuery))
        : commands,
    [commands, normalizedQuery],
  );

  const groups = {};
  filtered.forEach((command) => {
    (groups[command.grp] = groups[command.grp] || []).push(command);
  });

  React.useEffect(() => {
    if (!open) return;
    const row = rowRefs.current[activeIndex];
    if (typeof row?.scrollIntoView === "function") {
      row.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, open, query]);
  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      } else if (event.key === "ArrowDown" && filtered.length > 0) {
        event.preventDefault();
        setActiveIndex((index) => Math.min(filtered.length - 1, index + 1));
      } else if (event.key === "ArrowUp" && filtered.length > 0) {
        event.preventDefault();
        setActiveIndex((index) => Math.max(0, index - 1));
      } else if (event.key === "Enter" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        const command = filtered[activeIndex];
        if (!command) return;
        event.preventDefault();
        command.run();
        onClose();
      }
      if (event.key === "Tab") {
        const focusable = Array.from(
          dialogRef.current?.querySelectorAll(
            'input, button:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ) || [],
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, filtered, onClose, open]);

  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 50,
        background: t.overlay,
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: 80,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
        style={{
          width: 480,
          background: t.surface,
          border: `1px solid ${t.borderHi}`,
          borderRadius: t.radius + 4,
          boxShadow: "0 20px 60px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.08)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          maxHeight: 420,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 14px",
            borderBottom: `1px solid ${t.border}`,
          }}
        >
          <span style={{ color: t.textDim }}>
            <Icon name="search" size={15} />
          </span>
          <input
            ref={inputRef}
            role="combobox"
            aria-label="Search commands"
            aria-expanded="true"
            aria-controls={listboxId}
            aria-activedescendant={
              filtered[activeIndex] ? `${listboxId}-option-${activeIndex}` : undefined
            }
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="Search settings, jump to..."
            style={{
              flex: 1,
              border: "none",
              background: "transparent",
              color: t.text,
              fontSize: 14,
              fontFamily: "inherit",
            }}
          />
          <Kbd>Esc</Kbd>
        </div>
        <div
          id={listboxId}
          role="listbox"
          aria-label="Commands"
          style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}
        >
          {filtered.length === 0 && (
            <div
              role="status"
              style={{
                padding: 24,
                textAlign: "center",
                color: t.textMuted,
                fontSize: 13,
              }}
            >
              No results for "{query}".
            </div>
          )}
          {Object.entries(groups).map(([groupName, items]) => (
            <div key={groupName} role="group" aria-label={groupName}>
              <div
                style={{
                  padding: "6px 14px 2px",
                  fontSize: 10,
                  fontWeight: 600,
                  color: t.textMuted,
                  textTransform: "uppercase",
                  letterSpacing: 0.8,
                }}
              >
                {groupName}
              </div>
              {items.map((command) => {
                // Capture a per-item flat index so each row's onMouseEnter
                // closure highlights that row instead of sharing one mutable
                // counter that ends at the last item.
                const itemIndex = filtered.indexOf(command);
                const active = itemIndex === activeIndex;
                return (
                  <div
                    key={command.label}
                    id={`${listboxId}-option-${itemIndex}`}
                    role="option"
                    aria-selected={active}
                    ref={(element) => {
                      rowRefs.current[itemIndex] = element;
                    }}
                    onClick={() => {
                      command.run();
                      onClose();
                    }}
                    onMouseEnter={() => setActiveIndex(itemIndex)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 14px",
                      cursor: "pointer",
                      background: active ? t.accentBg : "transparent",
                      color: active ? t.accent : t.text,
                    }}
                  >
                    <span style={{ color: active ? t.accent : t.textDim }}>
                      <Icon name={command.icon} size={13} />
                    </span>
                    <span style={{ flex: 1, fontSize: 13 }}>{command.label}</span>
                    {command.kbd && <Kbd>{command.kbd}</Kbd>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div
          style={{
            padding: "8px 14px",
            borderTop: `1px solid ${t.border}`,
            background: t.surface2,
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 11,
            color: t.textMuted,
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Kbd>Up</Kbd>
            <Kbd>Down</Kbd> navigate
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <Kbd>Enter</Kbd> select
          </span>
          <div style={{ flex: 1 }} />
          <span>Virelo {__APP_VERSION__}</span>
        </div>
      </div>
    </div>
  );
}

export { CommandPalette };
