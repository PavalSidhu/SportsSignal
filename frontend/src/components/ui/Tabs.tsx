import { cn } from '../../lib/cn';

interface Tab {
  label: string;
  value: string;
}

export function Tabs({
  tabs,
  activeTab,
  onTabChange,
}: {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (value: string) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-border">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          onClick={() => onTabChange(tab.value)}
          className={cn(
            'px-4 py-2 text-sm font-medium transition-colors -mb-px',
            activeTab === tab.value
              ? 'border-b-2 border-primary text-primary'
              : 'text-text-secondary hover:text-text-primary',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
