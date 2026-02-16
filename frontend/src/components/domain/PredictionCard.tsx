import { Link } from 'react-router';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { TeamLogo } from './TeamLogo';
import { WinProbabilityBar } from './WinProbabilityBar';
import { FactorBadge } from './FactorBadge';
import { formatDate, formatGameTime, formatScore } from '../../lib/formatters';
import type { Game, Factor } from '../../types';

function getStatusVariant(status: string) {
  const lower = status.toLowerCase();
  if (lower === 'final') return 'success' as const;
  return 'neutral' as const;
}

function getStatusLabel(status: string): string {
  const lower = status.toLowerCase();
  if (lower === 'final') return 'Final';
  if (lower === 'scheduled') return 'Scheduled';
  if (lower === 'in_progress' || lower === 'live') return 'Live';
  return status;
}

export function PredictionCard({ game }: { game: Game }) {
  const { prediction } = game;
  const isFinal = game.status.toLowerCase() === 'final';
  const gameTime = formatGameTime(game.game_date);

  return (
    <Card className="flex flex-col gap-3 animate-fade-in">
      {/* Header: date + time + status */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-muted">
          {formatDate(game.game_date)}
          {gameTime && <span className="ml-1.5 text-text-secondary">{gameTime}</span>}
        </span>
        <Badge variant={getStatusVariant(game.status)}>
          {getStatusLabel(game.status)}
        </Badge>
      </div>

      {/* Teams */}
      <div className="space-y-2">
        {/* Home team */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TeamLogo team={game.home_team} size="md" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                {game.home_team.name}
              </p>
              <p className="text-xs text-text-muted">Home</p>
            </div>
          </div>
          {isFinal && game.home_score !== null && (
            <span className="text-lg font-bold text-text-primary tabular-nums">
              {game.home_score}
            </span>
          )}
        </div>

        {/* Away team */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TeamLogo team={game.away_team} size="md" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                {game.away_team.name}
              </p>
              <p className="text-xs text-text-muted">Away</p>
            </div>
          </div>
          {isFinal && game.away_score !== null && (
            <span className="text-lg font-bold text-text-primary tabular-nums">
              {game.away_score}
            </span>
          )}
        </div>
      </div>

      {/* Win probability bar */}
      {prediction && (
        <WinProbabilityBar
          homeTeam={game.home_team}
          awayTeam={game.away_team}
          homeProb={prediction.win_probability}
        />
      )}

      {/* Predicted score */}
      {prediction && (
        <div className="text-center">
          <p className="text-xs text-text-muted">Predicted Score</p>
          <p className="text-sm font-semibold text-text-primary">
            {formatScore(prediction.predicted_home_score, prediction.predicted_away_score)}
          </p>
        </div>
      )}

      {/* Factor badges -- show top 3 if available */}
      {prediction &&
        'key_factors' in prediction &&
        Array.isArray((prediction as unknown as { key_factors: Factor[] }).key_factors) && (
          <div className="flex flex-wrap gap-1.5">
            {(prediction as unknown as { key_factors: Factor[] }).key_factors
              .slice(0, 3)
              .map((factor) => (
                <FactorBadge key={factor.factor} factor={factor} />
              ))}
          </div>
        )}

      {/* View Details link */}
      <Link
        to={`/games/${game.id}`}
        className="text-sm text-primary hover:text-primary-light font-medium transition-colors text-center mt-auto"
      >
        View Details
      </Link>
    </Card>
  );
}
