import { cn } from '../../lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'bg-surface-tertiary rounded animate-pulse-skeleton',
        className,
      )}
    />
  );
}
