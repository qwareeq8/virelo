// Shared UI primitives for Virelo.
// All primitives consume tokens from useTokens() so density/radius/theme
// flow through without prop drilling.

import React from "react";
import { useTokens } from "./theme.jsx";
import { Icon } from "./icons.jsx";

const RowControlContext = React.createContext(null);

function Toggle({ on, onChange, size = "md" }) {
  const t = useTokens();
  const row = React.useContext(RowControlContext);
  const trackWidth = size === "sm" ? 26 : 32;
  const trackHeight = size === "sm" ? 15 : 18;
  const knobSize = trackHeight - 4;
  return (
    <button
      role="switch"
      aria-checked={!!on}
      aria-labelledby={row?.labelId}
      aria-describedby={row?.descriptionId}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!on);
      }}
      style={{
        border: "none",
        padding: 0,
        cursor: "pointer",
        background: "transparent",
        flexShrink: 0,
      }}
    >
      <span
        style={{
          display: "block",
          width: trackWidth,
          height: trackHeight,
          borderRadius: trackHeight / 2,
          background: on
            ? t.accent
            : t.isDark
              ? "rgba(255,255,255,0.12)"
              : "#D6D2CB",
          position: "relative",
          transition: "background .15s",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? trackWidth - knobSize - 2 : 2,
            width: knobSize,
            height: knobSize,
            borderRadius: knobSize / 2,
            background: "#fff",
            transition: "left .18s cubic-bezier(.2,.7,.3,1)",
            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
          }}
        />
      </span>
    </button>
  );
}

function Button({
  children,
  variant = "secondary",
  size = "md",
  onClick,
  icon,
  kbd,
  disabled,
  ...buttonProps
}) {
  const t = useTokens();
  const [hover, setHover] = React.useState(false);
  const variants = {
    primary: {
      bg: t.accent,
      color: t.accentOn,
      border: t.accent,
      hover: `color-mix(in oklab, ${t.accent} 90%, #000)`,
    },
    secondary: {
      bg: t.surface,
      color: t.text,
      border: t.borderHi,
      hover: t.hover,
    },
    ghost: {
      bg: "transparent",
      color: t.textDim,
      border: "transparent",
      hover: t.hover,
    },
    danger: {
      bg: "transparent",
      color: t.dangerText,
      border: t.borderHi,
      hover: "rgba(197,74,58,0.08)",
    },
  };
  const variantStyle = variants[variant];
  const buttonHeight = size === "sm" ? 26 : 32;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      {...buttonProps}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        height: buttonHeight,
        padding: size === "sm" ? "0 10px" : "0 14px",
        background: hover && !disabled ? variantStyle.hover : variantStyle.bg,
        color: variantStyle.color,
        border: `1px solid ${variantStyle.border}`,
        borderRadius: t.radius,
        fontSize: size === "sm" ? 12 : 13,
        fontWeight: 500,
        fontFamily: "inherit",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background .12s, border-color .12s",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      {icon}
      {children}
      {kbd && (
        <span
          style={{
            marginLeft: 4,
            padding: "1px 5px",
            background: t.hover,
            borderRadius: 3,
            fontSize: 10,
            fontFamily: t.mono,
            opacity: 0.7,
          }}
        >
          {kbd}
        </span>
      )}
    </button>
  );
}

function Card({ title, subtitle, children, footer, padding = true }) {
  const t = useTokens();
  return (
    <div
      style={{
        background: t.surface,
        border: `1px solid ${t.border}`,
        borderRadius: t.radius + 2,
        overflow: "hidden",
        boxShadow: t.shadow,
      }}
    >
      {(title || subtitle) && (
        <div
          style={{
            padding: `${t.rowPad + 2}px ${t.cardPad}px`,
            borderBottom: `1px solid ${t.border}`,
            background: t.surface2,
          }}
        >
          {title && (
            <h2
              style={{
                margin: 0,
                fontSize: 13,
                fontWeight: 600,
                color: t.text,
                letterSpacing: -0.1,
              }}
            >
              {title}
            </h2>
          )}
          {subtitle && (
            <div style={{ fontSize: 12, color: t.textDim, marginTop: 2 }}>
              {subtitle}
            </div>
          )}
        </div>
      )}
      <div style={{ padding: padding ? `4px ${t.cardPad}px` : 0 }}>
        {children}
      </div>
      {footer && (
        <div
          style={{
            padding: `${t.rowPad - 2}px ${t.cardPad}px`,
            borderTop: `1px solid ${t.border}`,
            background: t.surface2,
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}

function Row({ label, description, children, last }) {
  const t = useTokens();
  const labelId = React.useId();
  const descriptionId = React.useId();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        padding: `${t.rowPad}px 0`,
        borderBottom: last ? "none" : `1px solid ${t.border}`,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          id={labelId}
          style={{ fontSize: 13.5, fontWeight: 500, color: t.text }}
        >
          {label}
        </div>
        {description && (
          <div
            id={descriptionId}
            style={{
              fontSize: 12.5,
              color: t.textDim,
              marginTop: 2,
              lineHeight: 1.45,
            }}
          >
            {description}
          </div>
        )}
      </div>
      <RowControlContext.Provider
        value={{
          labelId,
          label,
          descriptionId: description ? descriptionId : undefined,
        }}
      >
        <div style={{ flexShrink: 0 }}>{children}</div>
      </RowControlContext.Provider>
    </div>
  );
}

function Segmented({ options, value, onChange, mono }) {
  const t = useTokens();
  const row = React.useContext(RowControlContext);
  return (
    <div
      role="group"
      aria-labelledby={row?.labelId}
      aria-describedby={row?.descriptionId}
      style={{
        display: "inline-flex",
        background: t.isDark ? "rgba(255,255,255,0.04)" : "#EDEAE3",
        border: `1px solid ${t.border}`,
        borderRadius: t.radius + 1,
        padding: 2,
      }}
    >
      {options.map((o) => {
        const val = typeof o === "object" ? o.value : o;
        const label = typeof o === "object" ? o.label : o;
        const active = value === val;
        return (
          <button
            key={val}
            aria-pressed={active}
            onClick={() => onChange(val)}
            style={{
              height: 24,
              padding: "0 10px",
              background: active ? t.surface : "transparent",
              border: "none",
              borderRadius: t.radius - 1,
              color: t.text,
              fontSize: 12,
              fontWeight: active ? 600 : 500,
              fontFamily: mono ? t.mono : "inherit",
              letterSpacing: mono ? 0.3 : 0,
              cursor: "pointer",
              boxShadow: active
                ? t.isDark
                  ? "0 1px 0 rgba(0,0,0,0.4)"
                  : "0 1px 1.5px rgba(0,0,0,0.08)"
                : "none",
              transition: "background .12s",
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function stepButtonStyle(t) {
  return {
    width: 26,
    height: "100%",
    border: "none",
    background: "transparent",
    color: t.textDim,
    fontSize: 14,
    cursor: "pointer",
    fontFamily: "inherit",
  };
}

function Stepper({ value, onChange, min = 1, max = 9999, step = 1, suffix }) {
  const t = useTokens();
  const row = React.useContext(RowControlContext);
  return (
    <div
      role="group"
      aria-labelledby={row?.labelId}
      aria-describedby={row?.descriptionId}
      style={{
        display: "inline-flex",
        alignItems: "center",
        background: t.surface,
        border: `1px solid ${t.borderHi}`,
        borderRadius: t.radius,
        height: 28,
        overflow: "hidden",
      }}
    >
      <button
        aria-label={`Decrease ${row?.label || "value"}`}
        onClick={() => onChange(Math.max(min, value - step))}
        style={stepButtonStyle(t)}
      >
        {"−"}
      </button>
      <div
        style={{
          minWidth: 48,
          padding: "0 8px",
          fontSize: 13,
          fontWeight: 500,
          color: t.text,
          textAlign: "center",
          fontVariantNumeric: "tabular-nums",
          borderLeft: `1px solid ${t.border}`,
          borderRight: `1px solid ${t.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          gap: 2,
        }}
      >
        {value}
        {suffix && (
          <span style={{ color: t.textMuted, fontSize: 11 }}>{suffix}</span>
        )}
      </div>
      <button
        aria-label={`Increase ${row?.label || "value"}`}
        onClick={() => onChange(Math.min(max, value + step))}
        style={stepButtonStyle(t)}
      >
        +
      </button>
    </div>
  );
}

function Slider({ value, onChange, min = 0, max = 100 }) {
  const t = useTokens();
  const row = React.useContext(RowControlContext);
  const percentage = ((value - min) / (max - min)) * 100;
  const sliderRef = React.useRef(null);
  const activePointer = React.useRef(null);
  const updateFromPointer = (event) => {
    const rect = sliderRef.current.getBoundingClientRect();
    onChange(
      Math.round(
        min +
          Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) *
            (max - min),
      ),
    );
  };
  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    activePointer.current = event.pointerId;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    updateFromPointer(event);
  };
  const onPointerMove = (event) => {
    if (activePointer.current === event.pointerId) updateFromPointer(event);
  };
  const finishPointer = (event) => {
    if (activePointer.current !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    activePointer.current = null;
  };
  const clamp = (nextValue) => Math.max(min, Math.min(max, nextValue));
  const onKeyDown = (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      event.preventDefault();
      onChange(clamp(value - 1));
    }
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      event.preventDefault();
      onChange(clamp(value + 1));
    }
    if (event.key === "Home") {
      event.preventDefault();
      onChange(min);
    }
    if (event.key === "End") {
      event.preventDefault();
      onChange(max);
    }
  };
  return (
    <div
      ref={sliderRef}
      role="slider"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-labelledby={row?.labelId}
      aria-describedby={row?.descriptionId}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finishPointer}
      onPointerCancel={finishPointer}
      style={{
        position: "relative",
        height: 20,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        userSelect: "none",
        minWidth: 160,
      }}
    >
      <div
        style={{
          width: "100%",
          height: 4,
          borderRadius: 2,
          background: t.track,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            width: `${percentage}%`,
            background: t.accent,
            borderRadius: 2,
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: `calc(${percentage}% - 8px)`,
          width: 16,
          height: 16,
          borderRadius: 8,
          background: t.isDark ? t.text : "#fff",
          border: `1.5px solid ${t.accent}`,
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      />
    </div>
  );
}

function Kbd({ children }) {
  const t = useTokens();
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 22,
        height: 20,
        padding: "0 5px",
        background: t.isDark ? "rgba(255,255,255,0.06)" : "#fff",
        border: `1px solid ${t.borderHi}`,
        borderRadius: 4,
        color: t.text,
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: 0.3,
        fontFamily: t.mono,
        boxShadow: t.isDark ? "none" : "0 1px 0 rgba(0,0,0,0.04)",
      }}
    >
      {children}
    </span>
  );
}

function Badge({ children, tone = "default" }) {
  const t = useTokens();
  const tones = {
    default: { bg: t.hover, color: t.textDim },
    accent: { bg: t.accentBg, color: t.accent },
    success: {
      bg: t.isDark ? "rgba(109,212,181,0.14)" : "#E7F0EC",
      color: t.isDark ? "#6DD4B5" : "#2E6F5E",
    },
    warn: {
      bg: t.isDark ? "rgba(255,177,60,0.14)" : "#FBF1DD",
      color: t.isDark ? "#FFC77A" : "#8B6518",
    },
  };
  const toneStyle = tones[tone];
  return (
    <span
      style={{
        fontSize: 10.5,
        padding: "2px 7px",
        borderRadius: t.radius - 1,
        background: toneStyle.bg,
        color: toneStyle.color,
        fontWeight: 600,
        letterSpacing: 0.2,
        display: "inline-block",
        textTransform: "uppercase",
      }}
    >
      {children}
    </span>
  );
}

export { Toggle, Button, Card, Row, Segmented, Stepper, Slider, Kbd, Badge };
