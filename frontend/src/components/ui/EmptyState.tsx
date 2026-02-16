import type { ReactNode } from 'react';

export function EmptyState({
  message,
  icon,
}: {
  message: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      {icon && <div className="text-text-muted">{icon}</div>}
      <p className="text-text-muted text-sm">{message}</p>
    </div>
  );
}
