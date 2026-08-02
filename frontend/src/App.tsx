import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react';
import {
  UploadCloud,
  FileVideo,
  X,
  Zap,
  Plus,
  Type,
  Target,
  AlertTriangle,
} from 'lucide-react';
import { ToastProvider, useToast } from '@/hooks/useToast';
import { useMetaPro } from '@/hooks/useMetaPro';
import {
  PlatformType,
  StrategicAngle,
  type GeneratePlaybookPayload,
} from '@/services/api';
import {
  platformIdToType,
  platformTypeToId,
  strategyDataToPlatforms,
} from '@/services/adapter';
import RightColumn from '@/components/RightColumn';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Best-effort duration label for an audio/video file (e.g. "24:18"). */
function getMediaDuration(file: File): Promise<string> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement(
      file.type.startsWith('video/') ? 'video' : 'audio',
    );
    el.preload = 'metadata';
    let settled = false;

    const finish = (value: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      URL.revokeObjectURL(url);
      resolve(value);
    };

    // Guarantee settlement (and URL cleanup) even if metadata never loads.
    const timer = setTimeout(() => finish('--:--'), 5000);

    el.onloadedmetadata = () => {
      const duration = el.duration;
      if (Number.isFinite(duration) && duration > 0) {
        const m = Math.floor(duration / 60);
        const s = Math.floor(duration % 60);
        finish(`${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`);
      } else {
        finish('--:--');
      }
    };
    el.onerror = () => finish('--:--');
    el.src = url;
  });
}

const MAX_MEDIA_BYTES = 100 * 1024 * 1024; // matches the dropzone copy

/** Strategic-angle presets: chip -> StrategicAngle + pre-filled focus direction. */
const ANGLE_PRESETS: { angle: StrategicAngle; label: string; focus: string }[] = [
  {
    angle: StrategicAngle.RECRUITER,
    label: 'Recruiter',
    focus:
      'Target senior engineering recruiters and hiring managers. Frame the engineering depth as rare, hard-to-replicate talent signal — translate technical decisions into why this person is worth hiring.',
  },
  {
    angle: StrategicAngle.TECHNICAL,
    label: 'Technical',
    focus:
      'Target AI/ML engineers building production systems. Emphasize architecture decisions, failure modes, and the "why" behind every trade-off, with concrete implementation detail.',
  },
  {
    angle: StrategicAngle.FOUNDER,
    label: 'Founder',
    focus:
      'Target technical founders and indie hackers. Frame the transcript as a build-in-public narrative — the problem, the hard-won lessons, and the unfair advantage it creates.',
  },
  {
    angle: StrategicAngle.CONTRARIAN,
    label: 'Contrarian',
    focus:
      'Target experienced practitioners skeptical of hype. Challenge the prevailing consensus, call out what most teams get wrong, and back the contrarian take with evidence.',
  },
];

function Header({ onReset }: { onReset: () => void }) {
  return (
    <header className="sticky top-0 z-50 bg-ink/90 backdrop-blur-md border-b border-edge">
      <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl text-white font-serif tracking-tight">
              Meta Pro<span className="text-spark">.</span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden sm:inline-flex items-center gap-2 text-xs text-neutral-400 font-mono bg-coal px-3 py-1.5 rounded-full border border-edge">
              <span className="pulse-dot" />
              Agent Runtime Ready
            </div>
            <button
              onClick={onReset}
              className="group inline-flex items-center gap-1.5 rounded-full border border-edge bg-coal px-4 py-1.5 text-sm text-neutral-200 hover:border-spark/60 hover:text-white transition-colors"
            >
              <Plus className="h-4 w-4 text-spark" />
              <span className="font-medium">New Playbook</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

function SectionTitle({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-md bg-spark/10 border border-spark/30 px-2 font-mono text-xs font-semibold text-spark">
        {n}
      </span>
      <h2 className="font-serif text-2xl text-white tracking-tight">{children}</h2>
    </div>
  );
}

function UploadZone({
  file,
  onFile,
  onRemove,
}: {
  file: File | null;
  onFile: (f: File) => void;
  onRemove: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();
  const [dragging, setDragging] = useState(false);
  const [duration, setDuration] = useState('--:--');

  useEffect(() => {
    if (!file) {
      setDuration('--:--');
      return;
    }
    let cancelled = false;
    getMediaDuration(file).then((value) => {
      if (!cancelled) setDuration(value);
    });
    return () => {
      cancelled = true;
    };
  }, [file]);

  const acceptFile = (f: File) => {
    if (f.size > MAX_MEDIA_BYTES) {
      showToast('Recording exceeds the 100MB limit.');
      return;
    }
    onFile(f);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) acceptFile(f);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) acceptFile(f);
  };

  if (file) {
    return (
      <div className="group flex items-center gap-3 rounded-xl border border-edge bg-coal p-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-spark/10 border border-spark/20">
          <FileVideo className="h-5 w-5 text-spark" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{file.name}</p>
          <div className="mt-1 flex items-center gap-2 text-xs text-neutral-500 font-mono">
            <span>{formatBytes(file.size)}</span>
            <span className="text-edge">·</span>
            <span className="inline-flex items-center gap-1 rounded bg-edge/60 px-1.5 py-0.5 text-neutral-300">
              {duration}
            </span>
          </div>
        </div>
        <button
          onClick={onRemove}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-edge text-neutral-500 hover:border-red-500/40 hover:text-red-400 transition-colors"
          aria-label="Remove file"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
        dragging ? 'border-spark bg-spark/5' : 'border-[#26262E] hover:border-spark'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*,audio/*"
        className="hidden"
        onChange={handleChange}
      />
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-coal border border-edge">
        <UploadCloud className="h-6 w-6 text-spark" />
      </div>
      <p className="mt-4 text-sm font-medium text-neutral-200">
        Drag &amp; drop audio/video recording
      </p>
      <p className="mt-1 text-xs text-neutral-600 font-mono">
        Supports MP4, MP3, WAV (Max 100MB)
      </p>
    </div>
  );
}

function LeftColumn({
  activePlatform,
  isGenerating,
  error,
  onClearError,
  onGenerate,
}: {
  activePlatform: PlatformType;
  isGenerating: boolean;
  error: string | null;
  onClearError: () => void;
  onGenerate: (payload: GeneratePlaybookPayload) => void;
}) {
  const { showToast } = useToast();
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [transcript, setTranscript] = useState('');
  // Default to the Technical preset: chip selected + its focus text applied.
  const [focus, setFocus] = useState(
    () => ANGLE_PRESETS.find((p) => p.angle === StrategicAngle.TECHNICAL)?.focus ?? '',
  );
  const [strategicAngle, setStrategicAngle] = useState<StrategicAngle>(
    StrategicAngle.TECHNICAL,
  );

  const handleGenerate = useCallback(() => {
    if (isGenerating) return;
    if (!audioFile && !transcript.trim()) {
      showToast('Add a recording or paste a transcript first.');
      return;
    }
    onGenerate({
      transcriptText: transcript,
      focusDirection: focus,
      strategicAngle,
      activePlatform,
      mediaFile: audioFile,
    });
  }, [
    isGenerating,
    audioFile,
    transcript,
    focus,
    strategicAngle,
    activePlatform,
    onGenerate,
    showToast,
  ]);

  return (
    <div className="col-span-12 lg:col-span-5">
      <div className="rounded-2xl border border-edge bg-coal/40 p-6 sm:p-8">
        <SectionTitle n="01">Content Ingestion</SectionTitle>
        <p className="mt-2 font-serif text-lg italic text-neutral-500">
          Feed the agent raw signal — it returns structure.
        </p>

        <div className="mt-8">
          <label className="mb-3 flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-neutral-500">
            <FileVideo className="h-3.5 w-3.5" />
            Recording
          </label>
          <UploadZone file={audioFile} onFile={setAudioFile} onRemove={() => setAudioFile(null)} />
        </div>

        <div className="mt-7">
          <label className="mb-3 flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-neutral-500">
            <Type className="h-3.5 w-3.5" />
            Transcript / Notes
          </label>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={6}
            placeholder="Paste raw transcript, meeting notes, or talking points here..."
            className="w-full resize-none rounded-xl bg-coal border border-edge focus:border-spark focus:outline-none focus:ring-1 focus:ring-spark/30 text-neutral-200 placeholder-neutral-600 px-4 py-3 text-sm leading-relaxed transition-colors"
          />
        </div>

        <div className="mt-7">
          <label className="flex items-center gap-2 text-white font-serif text-base">
            <Target className="h-4 w-4 text-spark" />
            Strategic Angle &amp; Focus Direction
          </label>
          <p className="text-xs text-neutral-500 mb-3">
            Pick a preset lens — it pre-fills the focus direction below (still fully
            editable).
          </p>
          <div className="flex flex-wrap gap-2">
            {ANGLE_PRESETS.map((preset) => {
              const isActive = strategicAngle === preset.angle;
              return (
                <button
                  key={preset.angle}
                  onClick={() => {
                    setStrategicAngle(preset.angle);
                    setFocus(preset.focus);
                  }}
                  className={`rounded-full border px-3.5 py-1.5 text-xs font-mono font-semibold uppercase tracking-wider transition-all ${
                    isActive
                      ? 'border-spark bg-spark/10 text-spark shadow-[0_0_12px_rgba(255,229,0,0.15)]'
                      : 'border-edge bg-coal text-neutral-500 hover:border-spark/40 hover:text-neutral-300'
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          <textarea
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            rows={3}
            placeholder="e.g., Target senior engineering managers. Focus on why state machines beat basic prompt chaining and highlight engineered failure recovery."
            className="mt-3 w-full resize-none bg-[#0E0E12] border border-[#1C1C22] focus:border-[#FFE500] focus:outline-none text-neutral-200 placeholder-neutral-600 rounded-xl p-3 text-xs leading-relaxed transition-all"
          />
        </div>

        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className={`group mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-spark text-black font-semibold py-3.5 transition-all ${
            isGenerating
              ? 'cursor-not-allowed opacity-60'
              : 'hover:bg-[#e6cf00] shadow-[0_0_20px_rgba(255,229,0,0.15)] hover:shadow-[0_0_30px_rgba(255,229,0,0.25)]'
          }`}
        >
          <Zap className={`h-4 w-4 ${isGenerating ? 'animate-pulse' : 'fill-black'}`} />
          <span className="tracking-wide">
            {isGenerating ? 'GENERATING…' : 'GENERATE STRATEGY PLAYBOOK'}
          </span>
        </button>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="flex-1 leading-snug">{error}</p>
            <button
              onClick={onClearError}
              aria-label="Dismiss error"
              className="shrink-0 text-red-300/60 hover:text-red-300 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function App() {
  const {
    isGenerating,
    currentStep,
    statusMessage,
    strategyData,
    activePlatform,
    setActivePlatform,
    selectedHookId,
    selectHook,
    error,
    setError,
    triggerGeneration,
    cancelGeneration,
    reset,
  } = useMetaPro();

  const livePlatforms = useMemo(
    () => strategyDataToPlatforms(strategyData),
    [strategyData],
  );

  const handleGenerate = useCallback(
    (payload: GeneratePlaybookPayload) => {
      void triggerGeneration(payload);
    },
    [triggerGeneration],
  );

  return (
    <ToastProvider>
      <div className="min-h-screen bg-ink">
        <Header onReset={reset} />
        <main className="mx-auto max-w-[1400px] px-5 sm:px-8 py-10 sm:py-16">
          <div className="mb-12 sm:mb-16">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-spark">
              Meta Pro / 2026
            </p>
            <h1 className="mt-3 font-serif text-5xl sm:text-7xl leading-[1.05] text-white tracking-tight">
              Editorial intelligence,
              <br />
              <span className="italic text-neutral-500">autonomously distilled.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-neutral-400">
              Drop in a recording. Meta Pro's agent reads the signal, extracts
              the narrative spine, and returns a publish-ready strategy playbook
              across every channel that matters.
            </p>
          </div>

          <div className="grid grid-cols-12 gap-6 lg:gap-8">
            <LeftColumn
              activePlatform={activePlatform}
              isGenerating={isGenerating}
              error={error}
              onClearError={() => setError(null)}
              onGenerate={handleGenerate}
            />
            <RightColumn
              isGenerating={isGenerating}
              currentStep={currentStep}
              statusMessage={statusMessage}
              platforms={livePlatforms}
              activePlatform={platformTypeToId(activePlatform)}
              onPlatformChange={(id) => setActivePlatform(platformIdToType(id))}
              selectedHookId={selectedHookId[activePlatform] ?? null}
              onSelectHook={selectHook}
              onCancel={cancelGeneration}
            />
          </div>
        </main>

        <footer className="border-t border-edge">
          <div className="mx-auto max-w-[1400px] px-5 sm:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <span className="text-2xl text-white font-serif tracking-tight">
              Meta Pro<span className="text-spark">.</span>
            </span>
            <p className="font-mono text-xs text-neutral-600">
              © 2026 Meta Pro — Editorial-grade autonomous strategy.
            </p>
          </div>
        </footer>
      </div>
    </ToastProvider>
  );
}

export default App;
