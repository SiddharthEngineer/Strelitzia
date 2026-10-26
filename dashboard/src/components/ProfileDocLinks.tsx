import type { ProfileDocs } from '../types';

const DOC_NAMES: Record<keyof ProfileDocs, string> = {
  library: 'Strelitzia content library',
  resume: 'Strelitzia base resume',
};

/** The two Profile Docs as links (a Doc without a link is shown by name). */
export default function ProfileDocLinks({ docs, label }: { docs: ProfileDocs; label: string }) {
  return (
    <ul aria-label={label}>
      {(Object.keys(DOC_NAMES) as (keyof ProfileDocs)[]).map((kind) => {
        const url = docs[kind]?.url;
        return (
          <li key={kind}>
            {url ? <a href={url} target="_blank" rel="noreferrer noopener">{DOC_NAMES[kind]} ↗</a> : DOC_NAMES[kind]}
          </li>
        );
      })}
    </ul>
  );
}
