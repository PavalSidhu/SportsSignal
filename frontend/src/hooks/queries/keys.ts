export const queryKeys = {
  games: {
    all: ['games'] as const,
    list: (params: { sport: string; date?: string }) =>
      ['games', 'list', params] as const,
    detail: (id: number) => ['games', 'detail', id] as const,
  },
  teams: {
    all: ['teams'] as const,
    list: (sport: string) => ['teams', 'list', sport] as const,
  },
  accuracy: {
    all: ['accuracy'] as const,
    overview: (sport?: string) => ['accuracy', 'overview', sport] as const,
    bySport: () => ['accuracy', 'by-sport'] as const,
    byType: (sport?: string) => ['accuracy', 'by-type', sport] as const,
    trend: (sport?: string) => ['accuracy', 'trend', sport] as const,
    recent: (sport?: string) => ['accuracy', 'recent', sport] as const,
    calibration: () => ['accuracy', 'calibration'] as const,
  },
};
