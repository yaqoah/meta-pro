import { Check } from 'lucide-react';
import type { HookOption } from '@/data/platforms';

type Props = {
  hooks: HookOption[];
  selectedId: string;
  onSelect: (id: string) => void;
};

export default function HookEngine({ hooks, selectedId, onSelect }: Props) {
  return (
    <div>
      <h3 className="font-serif text-xl text-white tracking-tight">
        Recommended Platform Hooks
      </h3>
      <p className="mt-1 text-sm text-neutral-500">
        Select the editorial angle that best matches your recording's signal.
      </p>
      {hooks.length === 0 ? (
        <p className="mt-4 text-sm text-neutral-500">
          No hook options yet — complete the pipeline to generate hooks for this
          platform.
        </p>
      ) : (
      <div className="mt-4 grid gap-3">
        {hooks.map((hook, i) => {
          const isSelected = hook.id === selectedId;
          return (
            <button
              key={hook.id}
              onClick={() => onSelect(hook.id)}
              className={`group relative flex items-start gap-4 rounded-xl border p-5 text-left transition-all ${
                isSelected
                  ? 'border-spark/50 bg-spark/[0.03] shadow-[0_0_20px_rgba(255,229,0,0.08)]'
                  : 'border-edge bg-coal hover:border-edge/80'
              }`}
            >
              {/* Selector */}
              <div
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-all ${
                  isSelected
                    ? 'border-spark bg-spark shadow-[0_0_10px_rgba(255,229,0,0.4)]'
                    : 'border-edge group-hover:border-neutral-600'
                }`}
              >
                {isSelected && <Check className="h-3 w-3 text-black" strokeWidth={4} />}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-neutral-600">
                    Option {i + 1}
                  </span>
                  <span className="rounded-md bg-spark/10 border border-spark/20 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-spark">
                    {hook.style}
                  </span>
                </div>
                <p className="mt-2 font-serif text-lg italic text-white leading-snug">
                  {hook.headline}
                </p>
                <p className="mt-2 text-sm text-neutral-500 leading-relaxed">
                  {hook.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
      )}
    </div>
  );
}
