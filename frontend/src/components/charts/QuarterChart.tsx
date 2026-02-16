import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { QuarterPredictions } from '../../types';

const PRIMARY_LIGHT = '#3B82F6';
const ERROR = '#DC2626';

function getPeriodLabels(sport: string, count: number): string[] {
  switch (sport) {
    case 'NHL':
      return Array.from({ length: count }, (_, i) => `P${i + 1}`);
    case 'MLB':
      return Array.from({ length: count }, (_, i) => `${i + 1}`);
    case 'NCAAB':
      return ['1st Half', '2nd Half'];
    case 'NBA':
    case 'NCAAF':
    default:
      return Array.from({ length: count }, (_, i) => `Q${i + 1}`);
  }
}

function getPeriodTitle(sport: string): string {
  switch (sport) {
    case 'NHL':
      return 'Period-by-Period Predictions';
    case 'MLB':
      return 'Inning-by-Inning Predictions';
    case 'NCAAB':
      return 'Half-by-Half Predictions';
    case 'NBA':
    case 'NCAAF':
    default:
      return 'Quarter-by-Quarter Predictions';
  }
}

interface QuarterChartProps {
  quarterPredictions: QuarterPredictions | null;
  homeAbbr: string;
  awayAbbr: string;
  sport?: string;
}

export { getPeriodTitle };

export function QuarterChart({
  quarterPredictions,
  homeAbbr,
  awayAbbr,
  sport = 'NBA',
}: QuarterChartProps) {
  if (!quarterPredictions) {
    return (
      <p className="text-sm text-text-muted text-center py-8">
        Period predictions not available
      </p>
    );
  }

  const labels = getPeriodLabels(sport, quarterPredictions.home.length);

  const data = quarterPredictions.home.map((homeVal, i) => ({
    period: labels[i] ?? `${i + 1}`,
    home: Math.round(homeVal),
    away: Math.round(quarterPredictions.away[i]),
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data}>
        <XAxis dataKey="period" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Bar dataKey="home" name={homeAbbr} fill={PRIMARY_LIGHT} />
        <Bar dataKey="away" name={awayAbbr} fill={ERROR} />
      </BarChart>
    </ResponsiveContainer>
  );
}
