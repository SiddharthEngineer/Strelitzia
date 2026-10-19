import { useEffect } from 'react';

// engineerfamily's shared header (`/shared/site-header.js`) defines these; they render and style themselves.
// React 18 writes `className` on a custom element as a literal `classname` attribute, so these take `class`.
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'ef-home': HTMLAttributes<HTMLElement> & { class?: string };
      'ef-profile': HTMLAttributes<HTMLElement> & { class?: string; next?: string };
    }
  }
}

/** Load the site's header script once (`/auth/me`'s `site_header_url`); nothing without a URL. */
export function useSiteHeader(url: string | null | undefined): void {
  useEffect(() => {
    if (!url || Array.from(document.head.querySelectorAll('script')).some((s) => s.getAttribute('src') === url)) return;
    const script = document.createElement('script');
    script.src = url;
    document.head.appendChild(script);
  }, [url]);
}

/** engineerfamily's home link: the first thing in the header. */
export function SiteHome() {
  return <ef-home class="site-home" />;
}

/** engineerfamily's sign-in / profile / Sign out control: the last thing in the header. */
export function SiteProfile() {
  return <ef-profile class="site-profile" next="/strelitzia/dashboard/" />;
}
