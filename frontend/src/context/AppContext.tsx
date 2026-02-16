import { createContext, useContext, useReducer, type ReactNode } from 'react';
import { format, addDays, subDays } from 'date-fns';
import type { Sport } from '../types';

interface AppState {
  selectedSport: Sport;
  selectedDate: string;
}

type AppAction =
  | { type: 'SET_SPORT'; sport: Sport }
  | { type: 'SET_DATE'; date: string }
  | { type: 'NEXT_DAY' }
  | { type: 'PREV_DAY' };

/** Parse 'YYYY-MM-DD' as local time (avoids UTC timezone shift bugs). */
function parseLocalDate(dateStr: string): Date {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_SPORT':
      return { ...state, selectedSport: action.sport };
    case 'SET_DATE':
      return { ...state, selectedDate: action.date };
    case 'NEXT_DAY':
      return {
        ...state,
        selectedDate: format(addDays(parseLocalDate(state.selectedDate), 1), 'yyyy-MM-dd'),
      };
    case 'PREV_DAY':
      return {
        ...state,
        selectedDate: format(subDays(parseLocalDate(state.selectedDate), 1), 'yyyy-MM-dd'),
      };
  }
}

const AppContext = createContext<{
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
} | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, {
    selectedSport: 'NBA',
    selectedDate: format(new Date(), 'yyyy-MM-dd'),
  });

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
