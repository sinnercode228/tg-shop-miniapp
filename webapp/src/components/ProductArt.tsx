import type { Product } from '../domain/types';

/** Vector product illustrations (no photos/copyrighted assets), coloured from the catalog. */
export function ProductArt({ art, className }: { art: Product['art']; className?: string }) {
  const [a = '#C2410C', b = '#FFF7ED'] = art.colors;
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <rect width="120" height="120" fill={b} />
      <circle cx="96" cy="22" r="34" fill={a} opacity="0.14" />
      <circle cx="18" cy="104" r="26" fill={a} opacity="0.1" />
      {shape(art.kind, a, b)}
    </svg>
  );
}

function shape(kind: string, a: string, b: string) {
  switch (kind) {
    case 'bag':
      return (
        <g>
          <path d="M36 30h48l6 70a6 6 0 0 1-6 6H36a6 6 0 0 1-6-6z" fill={a} />
          <path d="M36 30h48l-3 10H39z" fill="#000" opacity="0.15" />
          <rect x="42" y="54" width="36" height="30" rx="4" fill={b} />
          <ellipse cx="60" cy="69" rx="7" ry="10" fill={a} transform="rotate(25 60 69)" />
          <path d="M57 61c4 4 2 11 6 16" stroke={b} strokeWidth="2" fill="none" />
        </g>
      );
    case 'drip':
      return (
        <g>
          <rect x="34" y="30" width="52" height="64" rx="6" fill={a} />
          <path d="M34 42h52" stroke={b} strokeWidth="2" strokeDasharray="4 4" />
          <path d="M46 56h28l-6 22H52z" fill={b} />
          <path d="M40 30v-6h40v6" fill="none" stroke={a} strokeWidth="4" />
        </g>
      );
    case 'tin':
      return (
        <g>
          <rect x="38" y="34" width="44" height="66" rx="6" fill={a} />
          <rect x="35" y="28" width="50" height="12" rx="4" fill="#000" opacity="0.25" />
          <rect x="44" y="56" width="32" height="24" rx="12" fill={b} />
          <path d="M52 68c4-8 12-8 16 0-4 6-12 6-16 0z" fill={a} />
        </g>
      );
    case 'dripper':
      return (
        <g>
          <path d="M30 40h60L70 80H50z" fill={a} />
          <path d="M40 48h40" stroke={b} strokeWidth="2" opacity="0.6" />
          <rect x="42" y="80" width="36" height="8" rx="3" fill={a} />
          <path d="M90 46c10 0 10 16 0 16" stroke={a} strokeWidth="5" fill="none" />
          <rect x="44" y="90" width="32" height="12" rx="3" fill="#000" opacity="0.12" />
        </g>
      );
    case 'filters':
      return (
        <g>
          {[0, 8, 16].map((d) => (
            <path
              key={d}
              d={`M${28 + d} ${40 + d}h52l-16 44H${44 + d}z`}
              fill={d === 16 ? a : b}
              stroke={a}
              strokeWidth="2"
            />
          ))}
        </g>
      );
    case 'kettle':
      return (
        <g>
          <path d="M36 52h44l6 44H30z" fill={a} />
          <path d="M44 52c0-10 28-10 28 0" fill={a} />
          <path
            d="M30 70C18 66 14 48 8 38"
            stroke={a}
            strokeWidth="5"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d="M86 58c14 0 14 26 0 26"
            stroke="#000"
            strokeWidth="5"
            fill="none"
            opacity="0.4"
          />
          <circle cx="58" cy="42" r="4" fill="#000" opacity="0.4" />
        </g>
      );
    case 'gaiwan':
      return (
        <g>
          <ellipse cx="60" cy="96" rx="36" ry="7" fill={a} opacity="0.5" />
          <path
            d="M34 62h52c0 20-12 30-26 30S34 82 34 62z"
            fill="#fff"
            stroke={a}
            strokeWidth="3"
          />
          <path d="M32 58c6-12 50-12 56 0z" fill={a} />
          <circle cx="60" cy="44" r="5" fill={a} />
          <path d="M46 74c6 4 22 4 28 0" stroke={a} strokeWidth="2" fill="none" />
        </g>
      );
    default:
      return <circle cx="60" cy="64" r="26" fill={a} />;
  }
}
