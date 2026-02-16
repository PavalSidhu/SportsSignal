import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'bg-surface rounded-xl shadow-sm border border-border p-4',
        className,
      )}
    >
      {children}
    </div>
  );
}
