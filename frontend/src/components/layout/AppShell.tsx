import { Outlet } from 'react-router';
import { Header } from './Header';
import { Footer } from './Footer';

export function AppShell() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6 pt-20">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
