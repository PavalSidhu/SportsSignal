import type { ReactNode, ButtonHTMLAttributes } from 'react';
import { cn } from '../../lib/cn';

type ButtonVariant = 'primary' | 'secondary' | 'ghost';

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-white hover:bg-primary-dark',
  secondary:
    'bg-surface border border-border text-text-primary hover:bg-surface-tertiary',
  ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-tertiary',
};

export function Button({
  children,
  variant = 'primary',
  onClick,
  className,
  disabled,
  type = 'button',
}: {
  children: ReactNode;
  variant?: ButtonVariant;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
  type?: ButtonHTMLAttributes<HTMLButtonElement>['type'];
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50',
        variantClasses[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}
