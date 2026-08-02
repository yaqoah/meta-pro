import { Sparkles } from 'lucide-react';
import { type Platform, type PlatformId } from '@/data/platforms';
import PlatformTabs from './PlatformTabs';
import HookEngine from './HookEngine';
import ChecklistAccordion from './ChecklistAccordion';
import MermaidDiagram from './MermaidDiagram';
import MetaPromptContainer from './MetaPromptContainer';
import PipelineOverlay from './PipelineOverlay';

type Props = {
  isGenerating: boolean;
  currentStep: '01' | '02' | '03';
  statusMessage: string | null;
  platforms: Partial<Record<PlatformId, Platform>>;
  activePlatform: PlatformId;
  onPlatformChange: (id: PlatformId) => void;
  selectedHookId: string | null;
  onSelectHook: (id: string) => void;
  onCancel?: () => void;
};

function EmptyWorkspace() {
  return (
    <div className="rounded-2xl border border-dashed border-edge bg-coal/20 p-10 sm:p-14 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-coal border border-edge">
        <Sparkles className="h-5 w-5 text-spark" />
      </div>
      <p className="mt-5 font-serif text-2xl text-white tracking-tight">
        Awaiting pipeline output
      </p>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-neutral-500">
        Drop in a recording or paste a transcript, pick a strategic angle, and
        generate — the agent will return hooks, algorithm mechanics, an
        architecture diagram, and a Claude meta-prompt for every platform.
      </p>
    </div>
  );
}

export default function RightColumn({
  isGenerating,
  currentStep,
  statusMessage,
  platforms,
  activePlatform,
  onPlatformChange,
  selectedHookId,
  onSelectHook,
  onCancel,
}: Props) {
  const platform = platforms[activePlatform];

  return (
    <div className="col-span-12 lg:col-span-7">
      <div className="relative">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-md bg-spark/10 border border-spark/30 px-2 font-mono text-xs font-semibold text-spark">
            02
          </span>
          <h2 className="font-serif text-2xl text-white tracking-tight">
            Strategy Playbook &amp; Meta-Prompt Workspace
          </h2>
        </div>
        <p className="mt-2 font-serif text-lg italic text-neutral-500">
          The agent has distilled your recording into a ready-to-deploy content strategy.
        </p>

        <div
          className={`mt-6 space-y-6 transition-all duration-300 ${
            isGenerating ? 'pointer-events-none opacity-30 blur-[2px]' : 'opacity-100 blur-0'
          }`}
        >
          <PlatformTabs active={activePlatform} onChange={onPlatformChange} />

          {platform ? (
            <>
              <div className="rounded-2xl border border-edge bg-coal/40 p-6 sm:p-7">
                <HookEngine
                  hooks={platform.hooks}
                  selectedId={selectedHookId ?? ''}
                  onSelect={onSelectHook}
                />
              </div>

              <ChecklistAccordion items={platform.checklist} />

              <MermaidDiagram code={platform.mermaidCode} />

              <div className="rounded-2xl border border-edge bg-coal/40 p-6 sm:p-7">
                <MetaPromptContainer prompt={platform.metaPrompt} />
              </div>
            </>
          ) : (
            <EmptyWorkspace />
          )}
        </div>

        <PipelineOverlay
          isGenerating={isGenerating}
          currentStep={currentStep}
          statusMessage={statusMessage}
          onCancel={onCancel}
        />
      </div>
    </div>
  );
}
