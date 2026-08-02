import { platformOrder, platforms, type PlatformId } from '@/data/platforms';

type Props = {
  active: PlatformId;
  onChange: (id: PlatformId) => void;
};

export default function PlatformTabs({ active, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 rounded-xl border border-edge bg-coal p-1">
      {platformOrder.map((id) => {
        const p = platforms[id];
        const isActive = active === id;
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={`relative flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-all ${
              isActive
                ? 'bg-ink text-spark'
                : 'text-neutral-500 hover:text-neutral-300'
            }`}
          >
            {p.label}
            {isActive && (
              <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-spark" />
            )}
          </button>
        );
      })}
    </div>
  );
}
