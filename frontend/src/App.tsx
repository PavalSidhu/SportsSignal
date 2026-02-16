import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router';
import { AppProvider } from './context/AppContext';
import { AppShell } from './components/layout/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { GameDetailPage } from './pages/GameDetailPage';
import { AccuracyPage } from './pages/AccuracyPage';
import { CalibrationPage } from './pages/CalibrationPage';
import { NotFoundPage } from './pages/NotFoundPage';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="games/:id" element={<GameDetailPage />} />
              <Route path="accuracy" element={<AccuracyPage />} />
              <Route path="calibration" element={<CalibrationPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AppProvider>
    </QueryClientProvider>
  );
}
