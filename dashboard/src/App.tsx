import { useCallback, useEffect, useRef, useState } from 'react';
import { getMe, getPanel, logout, onUnauthorized, siteLogout } from './api';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import AddJobDialog from './components/AddJobDialog';
import Flower from './components/Flower';
import Footer from './components/Footer';
import { SiteHome, SiteProfile, useSiteHeader } from './components/SiteSlots';
import ClaudeSetupPage from './pages/ClaudeSetupPage';
import ContactsPage from './pages/ContactsPage';
import JobPage from './pages/JobPage';
import JobsPage from './pages/JobsPage';
import PanelPage from './pages/PanelPage';
import PreferencesPage from './pages/PreferencesPage';
import ProfilePage from './pages/ProfilePage';
import SignInPage from './pages/SignInPage';
import type { AuthMe } from './types';

/** The sign-in gate: with login on, no session (or any 401) shows the sign-in screen instead of the app. */
export default function App() {
  const [me, setMe] = useState<AuthMe | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  useEffect(() => {
    onUnauthorized(() => {
      setSignedOut(true);
      getMe().then(setMe).catch(() => {}); // refresh the reason (proxy mode: not invited, or just disabled)
    });
    getMe().then(setMe).catch(() => setMe({ enabled: false, user: null })); // an older server: no login
    return () => onUnauthorized(null);
  }, []);
  // The app renders while /auth/me loads (login off is the common case); a 401 meanwhile lands on sign-in too.
  if (signedOut || (me?.enabled && !me.user)) return <SignInPage me={me} />;
  return <Shell me={me} />;
}

function Shell({ me }: { me: AuthMe | null }) {
  const [adding, setAdding] = useState(false);
  const [panelDue, setPanelDue] = useState<string | null>(null);
  const refreshPanelDue = useCallback(() => {
    getPanel().then((p) => setPanelDue(p.due)).catch(() => {}); // the reminder is optional
  }, []);
  useEffect(refreshPanelDue, [refreshPanelDue]);
  // On engineerfamily.net the site's own home link and profile control frame the header. In proxy mode the session is
  // the site's, so its profile control also carries Sign out; otherwise the dashboard keeps its own user menu.
  const site = Boolean(me?.site_header_url);
  const siteSession = site && me?.mode === 'proxy';
  useSiteHeader(me?.site_header_url);
  // On a narrow screen the nav scrolls sideways: keep the current page's link in view. Only the nav scrolls (not
  // scrollIntoView, which would also move the page to the top bar).
  const navRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const keepInView = () => {
      const link = nav.querySelector('a.active');
      if (!link || nav.scrollWidth <= nav.clientWidth) return;
      const box = nav.getBoundingClientRect(), at = link.getBoundingClientRect(), margin = 32;
      if (at.left < box.left) nav.scrollLeft -= box.left - at.left + margin;
      else if (at.right > box.right) nav.scrollLeft += at.right - box.right + margin;
    };
    keepInView();
    // Again when the nav's width changes: the window narrows, or the site's profile control loads beside it.
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(keepInView);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [pathname, site]); // the narrow layout only applies once `site` is known
  function signOut() {
    const siteUrl = me?.logout_url;
    logout().catch(() => {})
      .then(() => (siteUrl ? siteLogout(siteUrl) : undefined))
      .catch(() => {}).finally(() => window.location.reload());
  }
  return (
    <div className="app">
      <header className={site ? 'topbar site-topbar' : 'topbar'}>
        {site && <SiteHome />}
        <Link to="/" className="brand">
          <Flower variant="mark" size={28} />
          Strelitzia
        </Link>
        <nav className="nav" aria-label="Main" ref={navRef}>
          <NavLink to="/" end>Jobs</NavLink>
          <NavLink to="/contacts">Contacts</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          <NavLink to="/preferences">Preferences</NavLink>
          <NavLink to="/panel">
            Panel{panelDue && <span className="nav-dot" role="img" aria-label="due" title={`Panel due: ${panelDue}`} />}
          </NavLink>
          <NavLink to="/claude-setup">Claude setup</NavLink>
        </nav>
        <button type="button" className="primary add-job-button" onClick={() => setAdding(true)}>Add job</button>
        {!siteSession && me?.enabled && me.user && (
          <span className="user-menu">
            <span className="user-name" title={me.user.email}>{me.user.name || me.user.email}</span>
            <button type="button" onClick={signOut}>Sign out</button>
          </span>
        )}
        {site && <SiteProfile />}
      </header>
      {adding && <AddJobDialog onClose={() => setAdding(false)} />}
      <main className="content">
        <Routes>
          <Route path="/" element={<JobsPage panelDue={panelDue} />} />
          <Route path="/jobs/:key" element={<JobPage />} />
          <Route path="/contacts" element={<ContactsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/preferences" element={<PreferencesPage />} />
          <Route path="/claude-setup" element={<ClaudeSetupPage />} />
          <Route path="/panel" element={<PanelPage onChange={refreshPanelDue} />} />
          <Route path="*" element={<p className="notice">Page not found. <Link to="/">Back to jobs</Link></p>} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
