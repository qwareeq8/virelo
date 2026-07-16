import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '../theme.jsx';
import { Toggle, Button, Card, Badge } from '../primitives.jsx';

// Wrap component in ThemeProvider with minimal tweaks
function renderWithTheme(ui) {
  const tweaks = { theme: 'dark', accent: 'slate', density: 'cozy', radius: 6 };
  return render(
    <ThemeProvider tweaks={tweaks} setTweaks={vi.fn()}>
      {ui}
    </ThemeProvider>
  );
}

describe('Toggle', () => {
  it('renders without throwing', () => {
    const { container } = renderWithTheme(<Toggle on={false} onChange={vi.fn()} />);
    expect(container.querySelector('button')).toBeInTheDocument();
  });

  it('renders in on state', () => {
    const { container } = renderWithTheme(<Toggle on={true} onChange={vi.fn()} />);
    expect(container.querySelector('button')).toBeInTheDocument();
  });
});

describe('Button', () => {
  it('renders with children text', () => {
    renderWithTheme(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('renders primary variant', () => {
    renderWithTheme(<Button variant="primary">Save</Button>);
    expect(screen.getByText('Save')).toBeInTheDocument();
  });
});

describe('Card', () => {
  it('renders with title and children', () => {
    renderWithTheme(
      <Card title="Test Card">
        <p>Card content</p>
      </Card>
    );
    expect(screen.getByText('Test Card')).toBeInTheDocument();
    expect(screen.getByText('Card content')).toBeInTheDocument();
  });

  it('renders without title', () => {
    renderWithTheme(<Card><p>Just content</p></Card>);
    expect(screen.getByText('Just content')).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders with default tone', () => {
    renderWithTheme(<Badge>NEW</Badge>);
    expect(screen.getByText('NEW')).toBeInTheDocument();
  });

  it('renders with accent tone', () => {
    renderWithTheme(<Badge tone="accent">ON</Badge>);
    expect(screen.getByText('ON')).toBeInTheDocument();
  });
});
