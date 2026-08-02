import { useState } from 'react';
import { ChevronDown, Check } from 'lucide-react';

type Props = {
  items: string[];
};

export default function ChecklistAccordion({ items }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <div className="rounded-xl border border-edge bg-coal overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-edge/30 transition-colors"
      >
        <span className="text-sm font-semibold text-white">
          Platform Mechanics &amp; Checklist
        </span>
        <ChevronDown
          className={`h-4 w-4 text-neutral-500 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>
      <div
        className={`grid transition-all duration-200 ${
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden">
          {items.length === 0 ? (
            <p className="border-t border-edge px-5 py-4 text-sm text-neutral-500">
              No checklist items generated yet.
            </p>
          ) : (
            <ul className="border-t border-edge px-5 py-4 space-y-2.5">
              {items.map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-spark" strokeWidth={2.5} />
                  <span className="text-sm text-neutral-400 leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
