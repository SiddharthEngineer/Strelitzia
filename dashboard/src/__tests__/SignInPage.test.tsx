import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import App from '../App';
import SignInPage from '../pages/SignInPage';
import type { AuthMe } from '../types';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  getMe: vi.fn(),
  getPanel: vi.fn(),
  logout: vi.fn(),
  siteLogout: vi.fn(),
  onUnauthorized: vi.fn(),
}));

const OWNER: AuthMe = { enabled: true, user: { email: 'owner@example.com', name: 'Ada Owner', role: 'owner' } };

// A route with no page of its own, so only the top bar's requests run.
const renderApp = (path = '/nowhere') => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

beforeEach(() => {
  vi.mocked(api.getPanel).mockResolvedValue({ due: null } as Awaited<ReturnType<typeof api.getPanel>>);
  vi.mocked(api.logout).mockResolvedValue({ ok: true });
});

afterEach(() => vi.clearAllMocks());

describe('SignInPage', () => {
  it('links to Google sign-in', () => {
    render(<MemoryRouter><SignInPage /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Sign in with Google' })).toHaveAttribute('href', '/strelitzia/dashboard/api/auth/login');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it("names the site account that isn't invited and offers another (proxy mode)", () => {
    const me: AuthMe = { enabled: true, user: null, mode: 'proxy', reason: 'not_invited',
      identity: { email: 'stranger@example.com', name: null } };
    render(<MemoryRouter><SignInPage me={me} /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent("isn't invited");
    expect(screen.getByText(/Signed in as/)).toHaveTextContent('Signed in as stranger@example.com');
    expect(screen.getByRole('link', { name: 'Use another account' })).toHaveAttribute('href', '/strelitzia/dashboard/api/auth/login');
    expect(screen.queryByRole('link', { name: 'Sign in with Google' })).toBeNull();
  });

  it('names a disabled site account (proxy mode)', () => {
    const me: AuthMe = { enabled: true, user: null, mode: 'proxy', reason: 'disabled',
      identity: { email: 'friend@example.com', name: 'Friend' } };
    render(<MemoryRouter><SignInPage me={me} /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent('disabled');
    expect(screen.getByText(/Signed in as/)).toHaveTextContent('friend@example.com');
  });

  it('keeps the Google sign-in screen without a reason', () => {
    const me: AuthMe = { enabled: true, user: null, mode: 'google', reason: null, identity: null };
    render(<MemoryRouter><SignInPage me={me} /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument();
    expect(screen.queryByText(/Signed in as/)).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('explains an uninvited account', () => {
    render(<MemoryRouter initialEntries={['/?auth=not_invited']}><SignInPage /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent("isn't invited");
  });
});

it('explains a disabled account', () => {
  render(<MemoryRouter initialEntries={['/?auth=disabled']}><SignInPage /></MemoryRouter>);
  expect(screen.getByRole('alert')).toHaveTextContent('disabled');
});

describe('App sign-in gate', () => {
  it('shows the sign-in screen when login is on and nobody is signed in', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ enabled: true, user: null });
    renderApp();
    expect(await screen.findByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull();
  });

  it('shows the not-invited message on the gate', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ enabled: true, user: null });
    renderApp('/?auth=not_invited');
    expect(await screen.findByRole('alert')).toHaveTextContent("isn't invited");
  });

  it('shows the user and signs out', async () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    try {
      vi.mocked(api.getMe).mockResolvedValue(OWNER);
      const user = userEvent.setup();
      renderApp();
      expect(await screen.findByText('Ada Owner')).toHaveAttribute('title', 'owner@example.com');
      await user.click(screen.getByRole('button', { name: 'Sign out' }));
      expect(api.logout).toHaveBeenCalled();
      await vi.waitFor(() => expect(reload).toHaveBeenCalled());
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("signs out of the site when it's the site's session (proxy mode)", async () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    try {
      vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'proxy', logout_url: '/auth/logout' });
      vi.mocked(api.siteLogout).mockResolvedValue();
      const user = userEvent.setup();
      renderApp();
      await user.click(await screen.findByRole('button', { name: 'Sign out' }));
      await vi.waitFor(() => expect(api.siteLogout).toHaveBeenCalledWith('/auth/logout'));
      expect(api.logout).toHaveBeenCalled(); // the dashboard's own session (Drive state) ends too
      await vi.waitFor(() => expect(reload).toHaveBeenCalled());
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('shows who the site signed in when they are not invited', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ enabled: true, user: null, mode: 'proxy', reason: 'not_invited',
      identity: { email: 'stranger@example.com', name: null }, logout_url: '/auth/logout' });
    renderApp();
    expect(await screen.findByRole('link', { name: 'Use another account' })).toBeInTheDocument();
    expect(screen.getByText(/Signed in as/)).toHaveTextContent('stranger@example.com');
  });

  it('asks again who is signed in when a request comes back 401', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'proxy' });
    renderApp();
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    vi.mocked(api.getMe).mockResolvedValue({ enabled: true, user: null, mode: 'proxy', reason: 'disabled',
      identity: { email: 'owner@example.com', name: null } });
    const listener = vi.mocked(api.onUnauthorized).mock.calls.map(([l]) => l).filter(Boolean).pop()!;
    act(() => listener());
    expect(await screen.findByRole('alert')).toHaveTextContent('disabled');
    expect(screen.getByRole('link', { name: 'Use another account' })).toBeInTheDocument();
  });

  it('switches to the sign-in screen when a request comes back 401', async () => {
    vi.mocked(api.getMe).mockResolvedValue(OWNER);
    renderApp();
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    const listener = vi.mocked(api.onUnauthorized).mock.calls.map(([l]) => l).filter(Boolean).pop()!;
    act(() => listener());
    expect(screen.getByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull();
  });

  it('changes nothing when login is off', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ enabled: false, user: { email: 'owner@localhost', name: null, role: 'owner' } });
    renderApp();
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Sign in with Google' })).toBeNull();
  });
});
