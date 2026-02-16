import { Link, useLocation } from 'react-router';
import { cn } from '../../lib/cn';

const navLinks = [
  { label: 'Dashboard', to: '/' },
  { label: 'Accuracy', to: '/accuracy' },
  { label: 'Calibration', to: '/calibration' },
];

export function Header() {
  const location = useLocation();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-surface border-b border-border">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link to="/" className="text-xl font-bold text-primary">
          SportsSignal
        </Link>
        <nav className="flex items-center gap-1">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                'px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                location.pathname === link.to
                  ? 'text-primary bg-primary/10'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-tertiary',
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
