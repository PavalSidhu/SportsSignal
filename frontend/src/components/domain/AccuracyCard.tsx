import { Card } from '../ui/Card';

export function AccuracyCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
}) {
  return (
    <Card className="text-center">
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      <p className="text-sm text-text-secondary mt-1">{label}</p>
      {subtitle && (
        <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>
      )}
    </Card>
  );
}
