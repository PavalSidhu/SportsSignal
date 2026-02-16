import type { GameTeam } from '../../types';

export function WinProbabilityBar({
  homeTeam,
  awayTeam,
  homeProb,
}: {
  homeTeam: GameTeam;
  awayTeam: GameTeam;
  homeProb: number;
}) {
  const homePct = Math.round(homeProb * 100);
  const awayPct = 100 - homePct;

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs text-text-secondary mb-1">
        <span className={homeProb > 0.5 ? 'font-bold' : ''}>
          {homeTeam.abbreviation} {homePct}%
        </span>
        <span className={homeProb < 0.5 ? 'font-bold' : ''}>
          {awayPct}% {awayTeam.abbreviation}
        </span>
      </div>
      <div className="h-8 rounded-lg overflow-hidden flex w-full">
        <div
          className="bg-primary-light flex items-center justify-center text-white text-xs font-medium transition-all"
          style={{ width: `${homePct}%` }}
        >
          {homePct > 15 && `${homePct}%`}
        </div>
        <div
          className="bg-error-light flex items-center justify-center text-white text-xs font-medium transition-all"
          style={{ width: `${awayPct}%` }}
        >
          {awayPct > 15 && `${awayPct}%`}
        </div>
      </div>
    </div>
  );
}
