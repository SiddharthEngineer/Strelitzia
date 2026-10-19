import { useEffect } from 'react';

// engineerfamily's shared header (`/shared/site-header.js`) defines these; they render and style themselves.
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'ef-home': HTMLAttributes<HTMLElement>;
      'ef-profile': HTMLAttributes<HTMLElement> & { next?: string };
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
  return <ef-home className="site-home" />;
}

/** engineerfamily's sign-in / profile / Sign out control: the last thing in the header. */
export function SiteProfile() {
  return <ef-profile className="site-profile" next="/strelitzia/dashboard/" />;
}
