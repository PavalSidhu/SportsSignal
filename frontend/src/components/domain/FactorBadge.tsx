import { cn } from '../../lib/cn';
import type { Factor } from '../../types';

const dotColorMap: Record<string, string> = {
  positive: 'bg-success',
  negative: 'bg-error',
  neutral: 'bg-neutral',
};

function getDotColor(direction: string): string {
  if (direction.toLowerCase().includes('home') || direction.toLowerCase().includes('positive')) {
    return dotColorMap.positive;
  }
  if (direction.toLowerCase().includes('away') || direction.toLowerCase().includes('negative')) {
    return dotColorMap.negative;
  }
  return dotColorMap.neutral;
}

export function FactorBadge({ factor }: { factor: Factor }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary border border-border px-2.5 py-0.5 text-xs text-text-secondary max-w-48">
      <span
        className={cn('w-1.5 h-1.5 rounded-full shrink-0', getDotColor(factor.direction))}
      />
      <span className="truncate">{factor.factor}</span>
    </span>
  );
}
