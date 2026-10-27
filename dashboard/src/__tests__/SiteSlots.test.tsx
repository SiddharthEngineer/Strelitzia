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

describe('the narrow nav', () => {
  it('scrolls the current page into view', async () => {
    // jsdom has no layout: the nav is 300px wide with 600px of links, and "Claude setup" sits at 400-480px.
    const scrolled = new WeakMap<Element, number>();
    const isNav = (el: Element) => el.matches('nav.nav');
    const spies = [
      vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (this: Element) { return isNav(this) ? 600 : 0; }),
      vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (this: Element) { return isNav(this) ? 300 : 0; }),
      vi.spyOn(Element.prototype, 'scrollLeft', 'get').mockImplementation(function (this: Element) { return scrolled.get(this) ?? 0; }),
      vi.spyOn(Element.prototype, 'scrollLeft', 'set').mockImplementation(function (this: Element, value: number) { scrolled.set(this, value); }),
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        const nav = this.closest('nav.nav');
        const shift = nav ? scrolled.get(nav) ?? 0 : 0;
        if (this === nav) return { left: 0, right: 300 } as DOMRect;
        if (this.matches('a.active')) return { left: 400 - shift, right: 480 - shift } as DOMRect;
        return { left: 0, right: 0 } as DOMRect;
      }),
    ];
    try {
      vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'proxy', site_header_url: SCRIPT });
      render(<MemoryRouter initialEntries={['/claude-setup']}><App /></MemoryRouter>);
      const nav = screen.getByRole('navigation', { name: 'Main' });
      await vi.waitFor(() => expect(nav.closest('header')).toHaveClass('site-topbar'));
      expect(nav.scrollLeft).toBe(480 - 300 + 32); // the link's right edge, plus room past the edge shadow
    } finally {
      spies.forEach((spy) => spy.mockRestore());
    }
  });
});

describe("the nav's Users link", () => {
  // The site header's account menu links to engineerfamily's Users page, so the nav doesn't repeat it.
  it('is absent even for a site admin', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...OWNER, mode: 'proxy', site_admin: true, users_url: '/users/' });
    renderApp();
    await screen.findByRole('link', { name: 'Jobs' });
    expect(screen.queryByRole('link', { name: 'Users' })).toBeNull();
  });
});
