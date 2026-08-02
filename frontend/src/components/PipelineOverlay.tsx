import { useEffect, useMemo, useState } from 'react';
import { Check, Loader2, Circle, X } from 'lucide-react';

type PipelineStepStatus = 'completed' | 'active' | 'queued';

type PipelineStep = {
  n: string;
  label: string;
  status: PipelineStepStatus;
};

type Props = {
  isGenerating: boolean;
  currentStep: '01' | '02' | '03';
  statusMessage: string | null;
  onCancel?: () => void;
};

const STEP_DEFS: { n: '01' | '02' | '03'; label: string }[] = [
  { n: '01', label: 'Ingesting & Extracting Core Insights' },
  { n: '02', label: 'Synthesizing Platform Hooks & Algorithm Mechanics' },
  { n: '03', label: 'Building Mermaid Diagrams & Claude Meta-Prompts' },
];

const STEP_PROGRESS: Record<'01' | '02' | '03', number> = {
  '01': 30,
  '02': 65,
  '03': 92,
};

export default function PipelineOverlay({
  isGenerating,
  currentStep,
  statusMessage,
  onCancel,
}: Props) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const visible = mounted && isGenerating;

  const steps: PipelineStep[] = useMemo(
    () =>
      STEP_DEFS.map((step) => ({
        ...step,
        status:
          step.n < currentStep ? 'completed' : step.n === currentStep ? 'active' : 'queued',
      })),
    [currentStep],
  );

  const progress = STEP_PROGRESS[currentStep];

  return (
    <div
      className={`absolute inset-0 z-40 rounded-2xl bg-ink/95 backdrop-blur-sm transition-opacity duration-300 ${
        visible ? 'opacity-100' : 'pointer-events-none opacity-0'
      }`}
    >
      {/* Top progress bar */}
      <div className="absolute inset-x-0 top-0 h-0.5 bg-edge/40 overflow-hidden rounded-t-2xl">
        <div
          className="h-full bg-spark shadow-[0_0_8px_rgba(255,229,0,0.6)] transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Cancel */}
      {onCancel && (
        <button
          onClick={onCancel}
          className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-lg border border-edge bg-coal px-3 py-1.5 text-xs font-mono text-neutral-400 hover:border-red-500/40 hover:text-red-400 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
          Cancel
        </button>
      )}

      <div className="flex h-full flex-col items-center justify-center px-6 py-10">
        <div className="mb-6 text-center">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-spark">
            Agent Pipeline Running
          </p>
          <h3 className="mt-2 font-serif text-3xl text-white tracking-tight">
            Distilling your strategy playbook
          </h3>
          <div className="mt-3 inline-flex items-center gap-2 font-mono text-xs text-neutral-400">
            <span className="pulse-dot" />
            <span className="text-spark/90">{statusMessage ?? 'Connecting to the pipeline…'}</span>
          </div>
        </div>

        {/* Vertical step timeline */}
        <div className="w-full max-w-md space-y-1">
          {steps.map((step, i) => (
            <div
              key={step.n}
              className={`flex items-start gap-4 rounded-xl px-4 py-3.5 transition-all duration-300 ${
                step.status === 'active'
                  ? 'bg-spark/[0.04] border border-spark/20'
                  : 'border border-transparent'
              }`}
              style={{
                transitionDelay: `${i * 80}ms`,
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(8px)',
              }}
            >
              {/* Status icon */}
              <div className="mt-0.5 shrink-0">
                {step.status === 'completed' && (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-spark/15 border border-spark/40">
                    <Check className="h-4 w-4 text-spark" strokeWidth={3} />
                  </div>
                )}
                {step.status === 'active' && (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-spark/10 border border-spark/30">
                    <span className="pulse-dot" />
                  </div>
                )}
                {step.status === 'queued' && (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-coal border border-edge">
                    <Circle className="h-3.5 w-3.5 text-neutral-600" />
                  </div>
                )}
              </div>

              {/* Step content */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-neutral-600">{step.n}</span>
                  {step.status === 'active' && (
                    <Loader2 className="h-3 w-3 animate-spin text-spark" />
                  )}
                </div>
                <p
                  className={`mt-0.5 text-sm leading-snug transition-colors ${
                    step.status === 'completed'
                      ? 'text-neutral-500'
                      : step.status === 'active'
                        ? 'text-white'
                        : 'text-neutral-600'
                  }`}
                >
                  {step.label}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Progress percentage */}
        <div className="mt-8 flex items-center gap-3">
          <span className="font-mono text-2xl text-white tabular-nums">
            {Math.round(progress)}
          </span>
          <span className="font-mono text-sm text-neutral-600">%</span>
        </div>
      </div>
    </div>
  );
}
