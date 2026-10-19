import { render, screen } from '@testing-library/react';
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
  onUnauthorized: vi.fn(),
}));

const SCRIPT = '/shared/site-header.js';
const OWNER: AuthMe = { enabled: true, user: { email: 'owner@example.com', name: 'Ada Owner', role: 'owner' } };

const renderApp = () => render(<MemoryRouter initialEntries={['/nowhere']}><App /></MemoryRouter>);
const scripts = () => Array.from(document.head.querySelectorAll('script')).filter((s) => s.getAttribute('src') === SCRIPT);

beforeEach(() => {
  vi.mocked(api.getPanel).mockResolvedValue({ due: null } as Awaited<ReturnType<typeof api.getPanel>>);
});

afterEach(() => {
  vi.clearAllMocks();
  scripts().forEach((s) => s.remove());
});

describe('the shared site header', () => {
  it('frames the top bar with the site home link and profile control', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'proxy', site_header_url: SCRIPT });
    const { container } = renderApp();
    await vi.waitFor(() => expect(container.querySelector('ef-home')).not.toBeNull());
    const header = container.querySelector('header.topbar')!;
    expect(header.firstElementChild?.tagName).toBe('EF-HOME');
    expect(header.lastElementChild?.tagName).toBe('EF-PROFILE');
    expect(header.lastElementChild).toHaveAttribute('next', '/strelitzia/dashboard/');
    // A real class (not React 18's literal `classname`), so the phone-width grid in styles.css can place them.
    expect(header.firstElementChild).toHaveClass('site-home');
    expect(header.lastElementChild).toHaveClass('site-profile');
    expect(container.querySelector('.user-menu')).toBeNull();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(scripts()).toHaveLength(1);
  });

  it('loads the script once', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, site_header_url: SCRIPT });
    const first = renderApp();
    await vi.waitFor(() => expect(scripts()).toHaveLength(1));
    first.unmount();
    renderApp();
    await vi.waitFor(() => expect(document.querySelector('ef-home')).not.toBeNull());
    expect(scripts()).toHaveLength(1);
  });

  it("keeps today's header without a site header URL", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'google', site_header_url: null });
    const { container } = renderApp();
    const signOut = await screen.findByRole('button', { name: 'Sign out' });
    expect(signOut.closest('.user-menu')).not.toBeNull();
    expect(container.querySelector('ef-home, ef-profile')).toBeNull();
    expect(container.querySelector('header.topbar')?.firstElementChild).toHaveClass('brand');
    expect(scripts()).toHaveLength(0);
  });

  it("keeps the dashboard's own Sign out when the session isn't the site's (google mode)", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'google', site_header_url: SCRIPT });
    const { container } = renderApp();
    expect(await screen.findByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    const header = container.querySelector('header.topbar')!;
    expect(header.firstElementChild?.tagName).toBe('EF-HOME');
    expect(header.lastElementChild?.tagName).toBe('EF-PROFILE');
  });

  it('gives the sign-in screen the same slots', () => {
    const me: AuthMe = { enabled: true, user: null, mode: 'proxy', reason: 'not_invited',
      identity: { email: 'stranger@example.com', name: null }, site_header_url: SCRIPT };
    const { container } = render(<MemoryRouter><SignInPage me={me} /></MemoryRouter>);
    const header = container.querySelector('header')!;
    expect(header.firstElementChild?.tagName).toBe('EF-HOME');
    expect(header.lastElementChild?.tagName).toBe('EF-PROFILE');
    expect(screen.getByRole('link', { name: 'Use another account' })).toBeInTheDocument();
  });

  it('leaves the sign-in screen bare without one', () => {
    const { container } = render(<MemoryRouter><SignInPage me={{ enabled: true, user: null }} /></MemoryRouter>);
    expect(container.querySelector('header')).toBeNull();
  });
});
