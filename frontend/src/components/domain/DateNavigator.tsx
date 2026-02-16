import { useRef } from 'react';
import { format } from 'date-fns';
import { Button } from '../ui/Button';

export function DateNavigator({
  date,
  onPrev,
  onNext,
  onDateChange,
}: {
  date: string;
  onPrev: () => void;
  onNext: () => void;
  onDateChange: (date: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const [y, m, d] = date.split('-').map(Number);
  const formattedDate = format(new Date(y, m - 1, d), 'EEE, MMM d, yyyy');

  function handleDateClick() {
    inputRef.current?.showPicker();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.value) {
      onDateChange(e.target.value);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button variant="ghost" onClick={onPrev} className="px-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m15 18-6-6 6-6" />
        </svg>
      </Button>

      <button
        type="button"
        onClick={handleDateClick}
        className="text-sm font-medium text-text-primary hover:text-primary transition-colors px-2 py-1"
      >
        {formattedDate}
      </button>

      <input
        ref={inputRef}
        type="date"
        value={date}
        onChange={handleInputChange}
        className="sr-only"
        tabIndex={-1}
      />

      <Button variant="ghost" onClick={onNext} className="px-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
      </Button>
    </div>
  );
}
