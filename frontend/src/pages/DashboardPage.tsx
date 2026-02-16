import { useApp } from '../context/AppContext';
import { useGames } from '../hooks/queries/useGames';
import { useAccuracyOverview } from '../hooks/queries/useAccuracy';
import { Tabs } from '../components/ui/Tabs';
import { DateNavigator } from '../components/domain/DateNavigator';
import { PredictionCard } from '../components/domain/PredictionCard';
import { AccuracyCard } from '../components/domain/AccuracyCard';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import type { Sport } from '../types';

const sportTabs = [
  { label: 'NBA', value: 'NBA' },
  { label: 'NFL', value: 'NFL' },
  { label: 'NHL', value: 'NHL' },
  { label: 'MLB', value: 'MLB' },
  { label: 'NCAAB', value: 'NCAAB' },
  { label: 'NCAAF', value: 'NCAAF' },
];

export function DashboardPage() {
  const { state, dispatch } = useApp();
  const { selectedSport, selectedDate } = state;

  const {
    data: gamesData,
    isLoading: gamesLoading,
    error: gamesError,
  } = useGames({ sport: selectedSport, date: selectedDate });

  const { data: accuracyData } = useAccuracyOverview(selectedSport);

  const games = gamesData?.games ?? [];

  return (
    <div className="space-y-6">
      {/* Top controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <Tabs
          tabs={sportTabs}
          activeTab={selectedSport}
          onTabChange={(value) =>
            dispatch({ type: 'SET_SPORT', sport: value as Sport })
          }
        />
        <DateNavigator
          date={selectedDate}
          onPrev={() => dispatch({ type: 'PREV_DAY' })}
          onNext={() => dispatch({ type: 'NEXT_DAY' })}
          onDateChange={(date) => dispatch({ type: 'SET_DATE', date })}
        />
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Games grid */}
        <div className="lg:col-span-3">
          {gamesError ? (
            <p className="text-sm text-error text-center py-8">
              Failed to load games. Please try again later.
            </p>
          ) : gamesLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-56 rounded-xl" />
              ))}
            </div>
          ) : games.length === 0 ? (
            <EmptyState message="No games scheduled for this date" />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {games.map((game) => (
                <PredictionCard key={game.id} game={game} />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-1">
          <div className="lg:sticky lg:top-20 space-y-4">
            {accuracyData && (
              <>
                <AccuracyCard
                  label="Model Accuracy"
                  value={accuracyData.model_accuracy != null
                    ? `${accuracyData.model_accuracy.toFixed(1)}%`
                    : 'N/A'}
                  subtitle="cross-validated"
                />
                <AccuracyCard
                  label="Games Predicted"
                  value={accuracyData.games_predicted}
                />
                <AccuracyCard
                  label="Avg Score Error"
                  value={accuracyData.avg_score_error.toFixed(1)}
                  subtitle="points"
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
