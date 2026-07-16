import { describe, it, expect } from 'vitest';
import { bridgeToState, stateToBridge } from '../app.jsx';

describe('bridgeToState', () => {
  it('maps Python snake_case keys to React camelCase', () => {
    const result = bridgeToState({
      enable_snap: true,
      snap_key: 'shift',
      restore_key: 'ctrl',
      snap_presses: 3,
      snap_interval: 1050,
      width_pct: 76,
      height_pct: 76,
      game_mode_enabled: true,
      ex_auto_size: false,
      run_at_startup: false,
    });
    expect(result.snapEnabled).toBe(true);
    expect(result.snapKey).toBe('SHIFT');
    expect(result.restoreKey).toBe('CTRL');
    expect(result.pressCount).toBe(3);
    expect(result.interval).toBe(1050);
    expect(result.width).toBe(76);
    expect(result.height).toBe(76);
    expect(result.gameMode).toBe(true);
    expect(result.autoSize).toBe(false);
    expect(result.launchLogin).toBe(false);
  });

  it('uppercases snap_key and restore_key', () => {
    const result = bridgeToState({ snap_key: 'ctrl', restore_key: 'alt' });
    expect(result.snapKey).toBe('CTRL');
    expect(result.restoreKey).toBe('ALT');
  });

  it('applies default values via nullish coalescing', () => {
    const result = bridgeToState({});
    expect(result.snapEnabled).toBe(true);
    expect(result.snapKey).toBe('SHIFT');
    expect(result.restoreKey).toBe('CTRL');
    expect(result.pressCount).toBe(3);
    expect(result.interval).toBe(1050);
    expect(result.width).toBe(76);
    expect(result.height).toBe(76);
    expect(result.gameMode).toBe(true);
    expect(result.autoSize).toBe(true);
    expect(result.launchLogin).toBe(false);
  });

  it('handles explicit false values without falling back', () => {
    const result = bridgeToState({ enable_snap: false, game_mode_enabled: false });
    expect(result.snapEnabled).toBe(false);
    expect(result.gameMode).toBe(false);
  });
});

describe('stateToBridge', () => {
  it('maps React camelCase keys back to Python snake_case JSON', () => {
    const json = stateToBridge({
      snapEnabled: true,
      snapKey: 'SHIFT',
      restoreKey: 'CTRL',
      pressCount: 3,
      interval: 1050,
      width: 76,
      height: 76,
      gameMode: true,
      autoSize: false,
      launchLogin: false,
    });
    const parsed = JSON.parse(json);
    expect(parsed.enable_snap).toBe(true);
    expect(parsed.snap_key).toBe('shift');
    expect(parsed.restore_key).toBe('ctrl');
    expect(parsed.snap_presses).toBe(3);
    expect(parsed.snap_interval).toBe(1050);
    expect(parsed.width_pct).toBe(76);
    expect(parsed.height_pct).toBe(76);
    expect(parsed.game_mode_enabled).toBe(true);
    expect(parsed.ex_auto_size).toBe(false);
    expect(parsed.run_at_startup).toBe(false);
  });

  it('lowercases key names for Python bridge', () => {
    const json = stateToBridge({ snapKey: 'SHIFT', restoreKey: 'ALT' });
    const parsed = JSON.parse(json);
    expect(parsed.snap_key).toBe('shift');
    expect(parsed.restore_key).toBe('alt');
  });

  it('returns a valid JSON string', () => {
    const json = stateToBridge({
      snapEnabled: true,
      snapKey: 'SHIFT',
      restoreKey: 'CTRL',
      pressCount: 3,
      interval: 1050,
      width: 76,
      height: 76,
      gameMode: true,
      autoSize: false,
      launchLogin: false,
    });
    expect(typeof json).toBe('string');
    expect(() => JSON.parse(json)).not.toThrow();
  });
});
