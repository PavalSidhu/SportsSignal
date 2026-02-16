import { useState } from 'react';
import { useCalibration } from '../hooks/queries/useAccuracy';
import { CalibrationChart } from '../components/charts/CalibrationChart';
import { AccuracyCard } from '../components/domain/AccuracyCard';
import { Card } from '../components/ui/Card';
import { Skeleton } from '../components/ui/Skeleton';
import { cn } from '../lib/cn';
import type { CalibrationSportData } from '../types';

const SPORT_TABS = ['All', 'NBA', 'NHL', 'MLB', 'NCAAB', 'NCAAF', 'NFL'] as const;

function getBestBucket(sport: CalibrationSportData): string {
  if (sport.buckets.length === 0) return 'N/A';
  // Find the bucket where actual accuracy is closest to the midpoint (best calibrated)
  let best = sport.buckets[0];
  let bestDiff = Math.abs(best.accuracy_pct - best.bucket_midpoint);
  for (const b of sport.buckets) {
    if (b.total < 5) continue; // skip very small buckets
    const diff = Math.abs(b.accuracy_pct - b.bucket_midpoint);
    if (diff < bestDiff) {
      best = b;
      bestDiff = diff;
    }
  }
  return best.bucket_label;
}

export function CalibrationPage() {
  const [selectedSport, setSelectedSport] = useState<string>('All');
  const { data, isLoading } = useCalibration();

  const sports = data?.sports ?? [];
  const selectedData = selectedSport === 'All'
    ? null
    : sports.find((s) => s.sport === selectedSport);

  // Aggregate stats for "All" view
  const overallCorrect = sports.reduce((sum, s) => sum + s.overall_correct, 0);
  const overallTotal = sports.reduce((sum, s) => sum + s.overall_total, 0);
  const overallAccuracy = overallTotal > 0 ? (overallCorrect / overallTotal * 100) : 0;

  const summaryData = selectedData ?? {
    overall_correct: overallCorrect,
    overall_total: overallTotal,
    overall_accuracy_pct: Math.round(overallAccuracy * 10) / 10,
  };

  const bestBucketLabel = selectedData
    ? getBestBucket(selectedData)
    : sports.length > 0
      ? getBestBucket(sports.reduce((a, b) => a.overall_total > b.overall_total ? a : b))
      : 'N/A';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">
          Prediction Calibration
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          How well do predicted confidence levels match actual win rates? A perfectly calibrated model
          predicting 70% confidence should win ~70% of the time.
        </p>
      </div>

      {/* Sport tabs */}
      <div className="flex gap-1 flex-wrap">
        {SPORT_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedSport(tab)}
            className={cn(
              'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
              selectedSport === tab
                ? 'text-primary bg-primary/10'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-tertiary',
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Summary cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <AccuracyCard
            label="Overall Accuracy"
            value={`${summaryData.overall_accuracy_pct.toFixed(1)}%`}
          />
          <AccuracyCard
            label="Total Games"
            value={summaryData.overall_total}
          />
          <AccuracyCard
            label="Best Calibrated"
            value={bestBucketLabel}
            subtitle="closest to perfect"
          />
        </div>
      )}

      {/* Chart section */}
      {isLoading ? (
        <Card>
          <Skeleton className="h-72 rounded-lg" />
        </Card>
      ) : selectedSport === 'All' ? (
        /* Grid of mini charts for all sports */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {sports.map((sport) => (
            <Card key={sport.sport}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium text-text-secondary">
                  {sport.sport}
                </h3>
                <span className="text-xs text-text-muted">
                  {sport.overall_accuracy_pct}% ({sport.overall_total} games)
                </span>
              </div>
              <CalibrationChart buckets={sport.buckets} height={200} compact />
            </Card>
          ))}
        </div>
      ) : selectedData ? (
        <>
          <Card>
            <h3 className="text-sm font-medium text-text-secondary mb-2">
              {selectedData.sport} Calibration
            </h3>
            <CalibrationChart buckets={selectedData.buckets} />
          </Card>

          {/* Data table */}
          <Card>
            <h3 className="text-sm font-medium text-text-secondary mb-3">
              Calibration Details
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-2 text-text-muted font-medium">Confidence</th>
                    <th className="text-right py-2 px-2 text-text-muted font-medium">Correct</th>
                    <th className="text-right py-2 px-2 text-text-muted font-medium">Total</th>
                    <th className="text-right py-2 px-2 text-text-muted font-medium">Accuracy</th>
                    <th className="py-2 px-2 text-text-muted font-medium w-40"></th>
                  </tr>
                </thead>
                <tbody>
                  {selectedData.buckets.map((bucket) => (
                    <tr key={bucket.bucket_label} className="border-b border-border last:border-0">
                      <td className="py-2 px-2 text-text-primary font-medium">
                        {bucket.bucket_label}
                      </td>
                      <td className="py-2 px-2 text-right text-text-secondary tabular-nums">
                        {bucket.correct}
                      </td>
                      <td className="py-2 px-2 text-right text-text-secondary tabular-nums">
                        {bucket.total}
                      </td>
                      <td className="py-2 px-2 text-right text-text-primary tabular-nums font-medium">
                        {bucket.accuracy_pct.toFixed(1)}%
                      </td>
                      <td className="py-2 px-2">
                        <div className="w-full bg-surface-tertiary rounded-full h-2">
                          <div
                            className="h-2 rounded-full transition-all"
                            style={{
                              width: `${bucket.accuracy_pct}%`,
                              backgroundColor:
                                bucket.accuracy_pct >= 65 ? '#059669'
                                : bucket.accuracy_pct >= 55 ? '#3B82F6'
                                : '#D97706',
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : (
        <Card>
          <p className="text-sm text-text-muted text-center py-8">
            No calibration data available for {selectedSport}
          </p>
        </Card>
      )}
    </div>
  );
}
