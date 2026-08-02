import { useCallback, useRef, useState } from 'react';
import {
  generatePlaybookStream,
  isAbortError,
  PlatformType,
  type GeneratePlaybookPayload,
  type PlatformStrategyOutput,
} from '@/services/api';

/** Strategy outputs indexed by platform (LINKEDIN / X_THREAD / MEDIUM). */
export type StrategyData = Partial<Record<PlatformType, PlatformStrategyOutput>>;

/** User-selected hook id per platform. */
export type SelectedHooks = Partial<Record<PlatformType, string>>;

/**
 * useMetaPro — live state for the Meta Pro generation pipeline.
 *
 * Owns everything the pipeline overlay and result panels need: active
 * generation flag, the 3-phase progress step, per-platform strategy outputs,
 * the active platform tab, per-platform hook selection and errors.
 *
 * `triggerGeneration` connects to the backend SSE stream, updates `currentStep`
 * monotonically as status events arrive, and merges `strategyData` per platform
 * as result events are emitted on graph completion.
 */
export function useMetaPro() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStep, setCurrentStep] = useState<'01' | '02' | '03'>('01');
  const [strategyData, setStrategyData] = useState<StrategyData>({});
  const [activePlatform, setActivePlatformState] = useState<PlatformType>(
    PlatformType.LINKEDIN,
  );
  const [selectedHookId, setSelectedHookId] = useState<SelectedHooks>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // Bumped to invalidate a stale in-flight run (abort + retry safety).
  const generationIdRef = useRef(0);

  /** Reset state, open the overlay, and stream a fresh generation. */
  const triggerGeneration = useCallback(async (payload: GeneratePlaybookPayload) => {
    abortRef.current?.abort();
    const generationId = ++generationIdRef.current;

    setError(null);
    setStrategyData({});
    setSelectedHookId({});
    setCurrentStep('01');
    setStatusMessage('Connecting to the agent pipeline…');
    setIsGenerating(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await generatePlaybookStream(
        payload,
        {
          onStatus: (event) => {
            if (event.status !== 'active') return;
            setCurrentStep((prev) => (event.step > prev ? event.step : prev));
            setStatusMessage(event.message);
          },
          onResult: (event) => {
            const output = event.data;
            setStrategyData((prev) => ({ ...prev, [output.platform]: output }));
            // Default-select the first hook for platforms with no choice yet.
            setSelectedHookId((prev) => {
              if (prev[output.platform] || output.hooks.length === 0) return prev;
              return { ...prev, [output.platform]: output.hooks[0].id };
            });
          },
          onError: (message) => {
            if (generationId === generationIdRef.current) setError(message);
          },
          onDone: (info) => {
            if (generationId !== generationIdRef.current) return;
            setStatusMessage(
              info.status === 'terminated' ? 'Pipeline terminated' : 'Playbook complete',
            );
            if (info.status === 'terminated') {
              setError('The pipeline terminated before producing a complete playbook.');
            } else if (info.errorLog.length > 0) {
              setError(`Pipeline finished with warnings: ${info.errorLog.join(' | ')}`);
            }
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (generationId === generationIdRef.current && !isAbortError(err)) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (generationId === generationIdRef.current) {
        abortRef.current = null;
        setIsGenerating(false);
      }
    }
  }, []);

  /** Abort the in-flight generation and close the overlay. */
  const cancelGeneration = useCallback(() => {
    generationIdRef.current += 1; // invalidate the in-flight run
    abortRef.current?.abort();
    abortRef.current = null;
    setStatusMessage(null);
    setIsGenerating(false);
  }, []);

  const setActivePlatform = useCallback((platform: PlatformType) => {
    setActivePlatformState(platform);
  }, []);

  /** Record the user's chosen hook for the currently active platform. */
  const selectHook = useCallback(
    (hookId: string) => {
      setSelectedHookId((prev) => ({ ...prev, [activePlatform]: hookId }));
    },
    [activePlatform],
  );

  /** Clear all generation state (results, errors, overlay). */
  const reset = useCallback(() => {
    generationIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setStrategyData({});
    setSelectedHookId({});
    setError(null);
    setCurrentStep('01');
    setStatusMessage(null);
    setIsGenerating(false);
  }, []);

  return {
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
  };
}
