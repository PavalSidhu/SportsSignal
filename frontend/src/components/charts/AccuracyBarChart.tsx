import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

const PRIMARY_LIGHT = '#3B82F6';
const SUCCESS = '#059669';
const WARNING = '#D97706';

interface AccuracyBarChartProps {
  data: { name: string; value: number }[];
  label: string;
}

function getBarColor(value: number): string {
  if (value >= 65) return SUCCESS;
  if (value >= 55) return PRIMARY_LIGHT;
  return WARNING;
}

export function AccuracyBarChart({ data, label }: AccuracyBarChartProps) {
  return (
    <div>
      <h3 className="text-sm font-medium text-text-secondary mb-2">
        {label}
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <XAxis dataKey="name" />
          <YAxis domain={[0, 100]} />
          <Tooltip formatter={(value: number) => `${value.toFixed(1)}%`} />
          <Bar dataKey="value" name="Accuracy">
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getBarColor(entry.value)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
