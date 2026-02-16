import { cn } from '../../lib/cn';
import type { Factor } from '../../types';

function getDirectionLabel(direction: string): string {
  const lower = direction.toLowerCase();
  if (lower.includes('home') || lower.includes('positive')) return 'Favors home';
  if (lower.includes('away') || lower.includes('negative')) return 'Favors away';
  return 'Neutral';
}

function getBarColor(direction: string): string {
  const lower = direction.toLowerCase();
  if (lower.includes('home') || lower.includes('positive')) return 'bg-success';
  if (lower.includes('away') || lower.includes('negative')) return 'bg-error';
  return 'bg-neutral';
}

function humanize(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function FactorList({ factors }: { factors: Factor[] }) {
  const maxImpact = Math.max(...factors.map((f) => Math.abs(f.impact)), 1);

  return (
    <div className="space-y-3">
      {factors.map((factor) => {
        const absImpact = Math.abs(factor.impact);
        const widthPct = Math.max((absImpact / maxImpact) * 100, 4);

        return (
          <div key={factor.factor} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-text-primary">
                {humanize(factor.factor)}
              </span>
              <span className="text-xs text-text-muted">
                {getDirectionLabel(factor.direction)}
              </span>
            </div>
            <div className="h-2 w-full bg-surface-tertiary rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', getBarColor(factor.direction))}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
