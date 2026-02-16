import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <h1 className="text-4xl font-bold text-text-primary">Page Not Found</h1>
      <p className="text-text-secondary">
        The page you're looking for doesn't exist.
      </p>
      <Link
        to="/"
        className="text-primary hover:text-primary-light font-medium transition-colors"
      >
        Back to Home
      </Link>
    </div>
  );
}
