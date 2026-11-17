/**
 * Score gauge 0-100: a half-ring with the only gradient in the app (section
 * 9.1). Bands follow the policy thresholds (close < 40, STR at 70).
 */
import { scoreColor } from "../../lib/meta";

export function ScoreGauge({ score, size = 44 }: { score: number | null | undefined; size?: number }) {
  const r = size / 2 - 4;
  const c = Math.PI * r;
  const value = score == null ? 0 : Math.max(0, Math.min(100, score));
  const color = scoreColor(score);
  const id = `g${size}`;
  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size }} role="img" aria-label={score == null ? "Not scored" : `Risk score ${value.toFixed(0)} of 100`}>
      <svg width={size} height={size / 2 + 4} viewBox={`0 0 ${size} ${size / 2 + 4}`} aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="var(--c-risk-low)" />
            <stop offset="50%" stopColor="var(--c-risk-high)" />
            <stop offset="100%" stopColor="var(--c-risk-critical)" />
          </linearGradient>
        </defs>
        <path d={`M 4 ${size / 2} A ${r} ${r} 0 0 1 ${size - 4} ${size / 2}`} fill="none" stroke="var(--c-border)" strokeWidth={4} strokeLinecap="round" />
        <path
          d={`M 4 ${size / 2} A ${r} ${r} 0 0 1 ${size - 4} ${size / 2}`}
          fill="none"
          stroke={`url(#${id})`}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={`${(value / 100) * c} ${c}`}
        />
      </svg>
      <span className="num -mt-3 text-xs font-semibold" style={{ color }}>
        {score == null ? "—" : value.toFixed(0)}
      </span>
    </div>
  );
}
