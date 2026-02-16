import { useParams, Link } from 'react-router';
import { useGameDetail } from '../hooks/queries/useGames';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { TeamLogo } from '../components/domain/TeamLogo';
import { WinProbabilityBar } from '../components/domain/WinProbabilityBar';
import { FactorList } from '../components/domain/FactorList';
import { QuarterChart, getPeriodTitle } from '../components/charts/QuarterChart';
import { TeamRadarChart } from '../components/charts/TeamRadarChart';
import {
  formatDate,
  formatScore,
  formatPct,
  getConfidenceLabel,
} from '../lib/formatters';

function getStatusVariant(status: string) {
  const lower = status.toLowerCase();
  if (lower === 'final') return 'success' as const;
  if (lower === 'in_progress' || lower === 'live') return 'warning' as const;
  return 'neutral' as const;
}

function getConfidenceBadgeVariant(confidence: number) {
  if (confidence >= 0.75) return 'success' as const;
  if (confidence >= 0.55) return 'primary' as const;
  return 'warning' as const;
}

export function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const gameId = Number(id) || 0;
  const { data: game, isLoading, error } = useGameDetail(gameId);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <h1 className="text-2xl font-bold text-text-primary">
          Game not found
        </h1>
        <p className="text-text-secondary">
          The game you're looking for doesn't exist or has been removed.
        </p>
        <Link
          to="/"
          className="text-primary hover:text-primary-light font-medium transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const prediction = game.predictions?.[0] ?? null;
  const isFinal = game.status.toLowerCase() === 'final';

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Game Header */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <Link
            to="/"
            className="text-sm text-primary hover:text-primary-light transition-colors"
          >
            &larr; Back
          </Link>
          <Badge variant={getStatusVariant(game.status)}>
            {game.status}
          </Badge>
        </div>

        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col items-center gap-2 flex-1">
            <TeamLogo team={game.home_team} size="xl" />
            <p className="text-base font-bold text-text-primary text-center">
              {game.home_team.name}
            </p>
            <p className="text-xs text-text-muted">Home</p>
          </div>

          <div className="text-center shrink-0 px-4">
            <p className="text-xs text-text-muted mb-1">
              {formatDate(game.game_date)}
            </p>
            {isFinal &&
            game.home_score != null &&
            game.away_score != null ? (
              <p className="text-3xl font-bold text-text-primary tabular-nums">
                {game.home_score} - {game.away_score}
              </p>
            ) : prediction ? (
              <div>
                <p className="text-xs text-text-muted">Predicted</p>
                <p className="text-2xl font-bold text-text-secondary tabular-nums">
                  {formatScore(
                    prediction.predicted_home_score,
                    prediction.predicted_away_score,
                  )}
                </p>
              </div>
            ) : (
              <p className="text-2xl font-bold text-text-muted">vs</p>
            )}
          </div>

          <div className="flex flex-col items-center gap-2 flex-1">
            <TeamLogo team={game.away_team} size="xl" />
            <p className="text-base font-bold text-text-primary text-center">
              {game.away_team.name}
            </p>
            <p className="text-xs text-text-muted">Away</p>
          </div>
        </div>
      </Card>

      {/* Win Probability */}
      {prediction && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Win Probability
          </h2>
          <WinProbabilityBar
            homeTeam={game.home_team}
            awayTeam={game.away_team}
            homeProb={prediction.win_probability}
          />
        </Card>
      )}

      {/* Prediction Details */}
      {prediction && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Prediction Details
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-xs text-text-muted">Spread</p>
              <p className="text-lg font-bold text-text-primary">
                {prediction.predicted_spread > 0 ? '+' : ''}
                {prediction.predicted_spread.toFixed(1)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-text-muted">Total</p>
              <p className="text-lg font-bold text-text-primary">
                {prediction.predicted_total.toFixed(1)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-text-muted">Win Prob</p>
              <p className="text-lg font-bold text-text-primary">
                {formatPct(prediction.win_probability * 100)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-text-muted">Confidence</p>
              <Badge
                variant={getConfidenceBadgeVariant(prediction.confidence)}
                className="mt-1"
              >
                {getConfidenceLabel(prediction.confidence)}
              </Badge>
            </div>
          </div>
        </Card>
      )}

      {/* Key Factors */}
      {prediction && prediction.key_factors.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Key Factors
          </h2>
          <FactorList factors={prediction.key_factors} />
        </Card>
      )}

      {/* Period Predictions */}
      {prediction && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            {getPeriodTitle(game.sport)}
          </h2>
          <QuarterChart
            quarterPredictions={prediction.quarter_predictions}
            homeAbbr={game.home_team.abbreviation}
            awayAbbr={game.away_team.abbreviation}
            sport={game.sport}
          />
        </Card>
      )}

      {/* Team Comparison */}
      {game.team_comparison && game.team_comparison.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Team Comparison
          </h2>
          <TeamRadarChart comparison={game.team_comparison} />
        </Card>
      )}

      {/* Head-to-Head */}
      {game.head_to_head && game.head_to_head.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Head-to-Head (Last {game.head_to_head.length} Meetings)
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-text-muted font-medium">
                    Date
                  </th>
                  <th className="text-left py-2 text-text-muted font-medium">
                    Home
                  </th>
                  <th className="text-left py-2 text-text-muted font-medium">
                    Away
                  </th>
                  <th className="text-center py-2 text-text-muted font-medium">
                    Score
                  </th>
                  <th className="text-right py-2 text-text-muted font-medium">
                    Winner
                  </th>
                </tr>
              </thead>
              <tbody>
                {game.head_to_head.map((h2h, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="py-2 text-text-secondary">
                      {formatDate(h2h.game_date)}
                    </td>
                    <td className="py-2 text-text-primary font-medium">
                      {h2h.home_team_abbreviation}
                    </td>
                    <td className="py-2 text-text-primary font-medium">
                      {h2h.away_team_abbreviation}
                    </td>
                    <td className="py-2 text-text-primary text-center tabular-nums">
                      {h2h.home_score} - {h2h.away_score}
                    </td>
                    <td className="py-2 text-right font-semibold text-text-primary">
                      {h2h.winner_abbreviation}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Coming Soon placeholders */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="flex flex-col items-center justify-center py-8">
          <p className="text-lg font-semibold text-text-secondary">
            Player Predictions
          </p>
          <p className="text-sm text-text-muted mt-1">Coming Soon</p>
        </Card>
        <Card className="flex flex-col items-center justify-center py-8">
          <p className="text-lg font-semibold text-text-secondary">
            Scenario Analysis
          </p>
          <p className="text-sm text-text-muted mt-1">Coming Soon</p>
        </Card>
      </div>
    </div>
  );
}
