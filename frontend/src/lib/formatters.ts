import { format, parseISO } from 'date-fns';

export function formatDate(dateStr: string): string {
  return format(parseISO(dateStr), 'MMM d, yyyy');
}

export function formatDateTime(dateStr: string): string {
  return format(parseISO(dateStr), 'MMM d, yyyy h:mm a');
}

export function formatGameTime(dateStr: string): string | null {
  const date = parseISO(dateStr);
  // Games in the midnight hour (00:00-00:59) have no real start time —
  // these are stored with unknown time data from ESPN
  if (date.getHours() === 0) return null;
  return format(date, 'h:mm a');
}

export function formatPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatScore(home: number, away: number): string {
  return `${Math.round(home)}-${Math.round(away)}`;
}

export function getWinProbColor(prob: number): string {
  if (prob >= 0.7) return 'text-success';
  if (prob >= 0.55) return 'text-primary-light';
  return 'text-neutral';
}

export function getConfidenceLabel(confidence: number): string {
  if (confidence >= 0.75) return 'High';
  if (confidence >= 0.55) return 'Medium';
  return 'Low';
}

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.75) return 'bg-success/10 text-success';
  if (confidence >= 0.55) return 'bg-primary-light/10 text-primary-light';
  return 'bg-neutral/10 text-neutral';
}
