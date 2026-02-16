import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import type { AccuracyTrendPoint } from '../../types';

const PRIMARY = '#1E40AF';
const NEUTRAL = '#6B7280';

interface AccuracyLineChartProps {
  data: AccuracyTrendPoint[];
}

function formatShortDate(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'MMM d');
  } catch {
    return dateStr;
  }
}

interface TooltipPayloadItem {
  payload: AccuracyTrendPoint;
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}) {
  if (!active || !payload || payload.length === 0) return null;

  const point = payload[0].payload;
  return (
    <div className="bg-surface border border-border rounded-lg p-2 shadow-sm text-sm">
      <p className="font-medium">{point.date}</p>
      <p>Accuracy: {point.accuracy_pct.toFixed(1)}%</p>
      <p>Total games: {point.total}</p>
    </div>
  );
}

export function AccuracyLineChart({ data }: AccuracyLineChartProps) {
  const chartData = data.map((point) => ({
    ...point,
    dateLabel: formatShortDate(point.date),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <XAxis dataKey="dateLabel" />
        <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine
          y={50}
          stroke={NEUTRAL}
          strokeDasharray="3 3"
          label="Chance"
        />
        <Line
          type="monotone"
          dataKey="accuracy_pct"
          stroke={PRIMARY}
          strokeWidth={2}
          dot={{ r: 4 }}
          name="Accuracy"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
