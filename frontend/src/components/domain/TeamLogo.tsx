import { cn } from '../../lib/cn';
import type { GameTeam } from '../../types';

type LogoSize = 'sm' | 'md' | 'lg' | 'xl';

const sizeClasses: Record<LogoSize, string> = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
  xl: 'w-16 h-16',
};

const textSizeClasses: Record<LogoSize, string> = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
  xl: 'text-lg',
};

export function TeamLogo({
  team,
  size = 'md',
}: {
  team: Pick<GameTeam, 'name' | 'abbreviation' | 'logo_url'>;
  size?: LogoSize;
}) {
  if (team.logo_url) {
    return (
      <img
        src={team.logo_url}
        alt={team.name}
        className={cn('object-contain', sizeClasses[size])}
      />
    );
  }

  return (
    <div
      className={cn(
        'bg-primary-light/10 text-primary rounded-full flex items-center justify-center font-semibold',
        sizeClasses[size],
        textSizeClasses[size],
      )}
    >
      {team.abbreviation}
    </div>
  );
}
