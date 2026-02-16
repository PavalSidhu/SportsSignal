import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type BadgeVariant = 'success' | 'error' | 'warning' | 'neutral' | 'primary';

const variantClasses: Record<BadgeVariant, string> = {
  success: 'bg-success/10 text-success',
  error: 'bg-error/10 text-error',
  warning: 'bg-warning/10 text-warning',
  neutral: 'bg-neutral/10 text-neutral',
  primary: 'bg-primary/10 text-primary',
};

export function Badge({
  children,
  variant = 'neutral',
  className,
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'rounded-full px-2.5 py-0.5 text-xs font-medium',
        variantClasses[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
