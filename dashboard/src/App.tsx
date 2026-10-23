import { useCallback, useEffect, useState } from 'react';
import { getMe, getPanel, logout, onUnauthorized, siteLogout } from './api';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
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
import UsersPage from './pages/UsersPage';
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
  // The Users page is for the owner, and only matters once other accounts can sign in. In proxy mode the site's profile
  // menu links to it, so the nav doesn't.
  const isOwner = Boolean(me?.enabled && me.user?.role === 'owner');
  // On engineerfamily.net the site's own home link and profile control frame the header. In proxy mode the session is
  // the site's, so its profile control also carries Sign out; otherwise the dashboard keeps its own user menu.
  const site = Boolean(me?.site_header_url);
  const siteSession = site && me?.mode === 'proxy';
  useSiteHeader(me?.site_header_url);
  const loader = <div className="loader-state" aria-live="polite" aria-busy="true"><Flower variant="loader" size={64} />Loading…</div>;
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
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Jobs</NavLink>
          <NavLink to="/contacts">Contacts</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          <NavLink to="/preferences">Preferences</NavLink>
          <NavLink to="/panel">
            Panel{panelDue && <span className="nav-dot" role="img" aria-label="due" title={`Panel due: ${panelDue}`} />}
          </NavLink>
          <NavLink to="/claude-setup">Claude setup</NavLink>
          {isOwner && !siteSession && <NavLink to="/users">Users</NavLink>}
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
          {(isOwner || !me) && <Route path="/users" element={isOwner ? <UsersPage /> : loader} />}
          <Route path="*" element={<p className="notice">Page not found. <Link to="/">Back to jobs</Link></p>} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
