import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { CalibrationBucket } from '../../types';

const SUCCESS = '#059669';
const PRIMARY_LIGHT = '#3B82F6';
const WARNING = '#D97706';
const REFERENCE_LINE_COLOR = '#6B7280';

function getBarColor(value: number): string {
  if (value >= 65) return SUCCESS;
  if (value >= 55) return PRIMARY_LIGHT;
  return WARNING;
}

interface CalibrationChartProps {
  buckets: CalibrationBucket[];
  height?: number;
  compact?: boolean;
}

export function CalibrationChart({ buckets, height = 300, compact = false }: CalibrationChartProps) {
  // Build chart data with perfect calibration reference line
  const chartData = buckets.map((b) => ({
    ...b,
    perfect: b.bucket_midpoint,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData}>
        <XAxis
          dataKey="bucket_label"
          tick={{ fontSize: compact ? 10 : 12 }}
          interval={0}
          angle={compact ? -45 : 0}
          textAnchor={compact ? 'end' : 'middle'}
          height={compact ? 50 : 30}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: compact ? 10 : 12 }}
          tickFormatter={(v: number) => `${v}%`}
          width={compact ? 35 : 45}
        />
        {!compact && (
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const data = payload[0].payload as CalibrationBucket & { perfect: number };
              return (
                <div className="bg-surface border border-border rounded-lg p-2 shadow-lg text-sm">
                  <p className="font-medium text-text-primary">{data.bucket_label}</p>
                  <p className="text-text-secondary">
                    {data.correct}/{data.total} correct ({data.accuracy_pct}%)
                  </p>
                  <p className="text-text-muted">
                    Perfect: {data.perfect}%
                  </p>
                </div>
              );
            }}
          />
        )}
        <Bar dataKey="accuracy_pct" name="Actual Accuracy">
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={getBarColor(entry.accuracy_pct)} />
          ))}
        </Bar>
        <Line
          type="linear"
          dataKey="perfect"
          name="Perfect Calibration"
          stroke={REFERENCE_LINE_COLOR}
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
