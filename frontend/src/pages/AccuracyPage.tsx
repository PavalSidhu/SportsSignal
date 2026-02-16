import {
  useAccuracyOverview,
  useAccuracyBySport,
  useAccuracyByType,
  useAccuracyTrend,
  useRecentPredictions,
} from '../hooks/queries/useAccuracy';
import { AccuracyCard } from '../components/domain/AccuracyCard';
import { AccuracyBarChart } from '../components/charts/AccuracyBarChart';
import { AccuracyLineChart } from '../components/charts/AccuracyLineChart';
import { Card } from '../components/ui/Card';
import { Skeleton } from '../components/ui/Skeleton';
import { cn } from '../lib/cn';
import { formatDate } from '../lib/formatters';

export function AccuracyPage() {
  const { data: overview, isLoading: overviewLoading } =
    useAccuracyOverview();
  const { data: bySportData, isLoading: bySportLoading } =
    useAccuracyBySport();
  const { data: byTypeData, isLoading: byTypeLoading } =
    useAccuracyByType();
  const { data: trendData, isLoading: trendLoading } = useAccuracyTrend();
  const { data: recentData, isLoading: recentLoading } =
    useRecentPredictions();

  const bySportChart =
    bySportData?.by_sport?.map((item) => ({
      name: item.sport,
      value: item.model_accuracy ?? item.accuracy_pct,
    })) ?? [];

  const byTypeChart =
    byTypeData?.by_type?.map((item) => ({
      name: item.prediction_type,
      value: item.accuracy_pct,
    })) ?? [];

  const trendChart = trendData?.trend ?? [];
  const recentPredictions = recentData ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-text-primary">
        Accuracy Analytics
      </h1>

      {/* Top row: stat cards */}
      {overviewLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : overview ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <AccuracyCard
            label="Model Accuracy"
            value={overview.model_accuracy != null
              ? `${overview.model_accuracy.toFixed(1)}%`
              : 'N/A'}
            subtitle="cross-validated"
          />
          <AccuracyCard
            label="Games Predicted"
            value={overview.games_predicted}
          />
          <AccuracyCard
            label="Score MAE"
            value={overview.avg_score_error.toFixed(1)}
            subtitle="points"
          />
          <AccuracyCard
            label="Avg Spread Error"
            value={overview.avg_spread_error.toFixed(1)}
            subtitle="points"
          />
        </div>
      ) : null}

      {/* Second row: bar charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          {bySportLoading ? (
            <Skeleton className="h-64 rounded-lg" />
          ) : (
            <AccuracyBarChart data={bySportChart} label="Accuracy by Sport" />
          )}
        </Card>
        <Card>
          {byTypeLoading ? (
            <Skeleton className="h-64 rounded-lg" />
          ) : (
            <AccuracyBarChart
              data={byTypeChart}
              label="Accuracy by Prediction Type"
            />
          )}
        </Card>
      </div>

      {/* Third row: trend line chart */}
      <Card>
        <h3 className="text-sm font-medium text-text-secondary mb-2">
          Accuracy Over Time
        </h3>
        {trendLoading ? (
          <Skeleton className="h-72 rounded-lg" />
        ) : (
          <AccuracyLineChart data={trendChart} />
        )}
      </Card>

      {/* Fourth row: recent predictions table */}
      <Card>
        <h3 className="text-sm font-medium text-text-secondary mb-3">
          Recent Predictions
        </h3>
        {recentLoading ? (
          <Skeleton className="h-64 rounded-lg" />
        ) : recentPredictions.length === 0 ? (
          <p className="text-sm text-text-muted text-center py-8">
            No recent predictions available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2 text-text-muted font-medium">
                    Date
                  </th>
                  <th className="text-left py-2 px-2 text-text-muted font-medium">
                    Matchup
                  </th>
                  <th className="text-center py-2 px-2 text-text-muted font-medium">
                    Predicted
                  </th>
                  <th className="text-center py-2 px-2 text-text-muted font-medium">
                    Actual
                  </th>
                  <th className="text-center py-2 px-2 text-text-muted font-medium">
                    Result
                  </th>
                  <th className="text-right py-2 px-2 text-text-muted font-medium">
                    Score Error
                  </th>
                </tr>
              </thead>
              <tbody>
                {recentPredictions.map((pred) => (
                  <tr
                    key={pred.game_id}
                    className={cn(
                      'border-b border-border last:border-0',
                      pred.was_correct
                        ? 'bg-success/5'
                        : 'bg-error/5',
                    )}
                  >
                    <td className="py-2 px-2 text-text-secondary">
                      {formatDate(pred.game_date)}
                    </td>
                    <td className="py-2 px-2 text-text-primary font-medium">
                      {pred.home_team} vs {pred.away_team}
                    </td>
                    <td className="py-2 px-2 text-center text-text-secondary tabular-nums">
                      {pred.predicted_score}
                    </td>
                    <td className="py-2 px-2 text-center text-text-primary tabular-nums">
                      {pred.actual_score}
                    </td>
                    <td className="py-2 px-2 text-center">
                      {pred.was_correct ? (
                        <span className="text-success font-bold">
                          &#10003;
                        </span>
                      ) : (
                        <span className="text-error font-bold">
                          &#10007;
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right text-text-secondary tabular-nums">
                      {pred.score_error.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
