import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { TeamComparisonStat } from '../../types';

const PRIMARY_LIGHT = '#3B82F6';
const ERROR = '#DC2626';

interface TeamRadarChartProps {
  comparison: TeamComparisonStat[];
}

export function TeamRadarChart({ comparison }: TeamRadarChartProps) {
  if (!comparison || comparison.length === 0) {
    return (
      <p className="text-sm text-text-muted text-center py-8">
        No comparison data
      </p>
    );
  }

  const data = comparison.map((stat) => ({
    stat_name: stat.stat_name,
    home: stat.home_value,
    away: stat.away_value,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="stat_name" />
        <Radar
          name="Home"
          dataKey="home"
          stroke={PRIMARY_LIGHT}
          fill={PRIMARY_LIGHT}
          fillOpacity={0.3}
        />
        <Radar
          name="Away"
          dataKey="away"
          stroke={ERROR}
          fill={ERROR}
          fillOpacity={0.3}
        />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
  );
}
