/**
 * Meta Pro API service layer.
 *
 * Thin client for the FastAPI backend (`backend/app/main.py`):
 *
 * - `POST /api/generate/stream` — multipart upload (media and/or raw text)
 *   that streams pipeline progress, per-platform strategy outputs and errors
 *   back over Server-Sent Events.
 *
 * The backend emits SSE frames of the form `event: <name>` + `data: <json>`
 * (`start`, `step`, `result`, `error`). This module reads the stream
 * line-by-line and normalizes those frames into typed callbacks consumed by
 * the UI hooks.
 */

// `import.meta.env` is injected by Vite; optional-chaining keeps this module
// safe to import outside the bundler (tests, SSR) where it is undefined.
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/+$/, '');

/** Mirrors backend `app.schemas.PlatformType`. */
export enum PlatformType {
  LINKEDIN = 'linkedin',
  X_THREAD = 'x_thread',
  MEDIUM = 'medium',
}

/** Mirrors backend `app.schemas.StrategicAngle`. */
export enum StrategicAngle {
  RECRUITER = 'recruiter',
  TECHNICAL = 'technical',
  FOUNDER = 'founder',
  CONTRARIAN = 'contrarian',
}

/** Mirrors backend `app.schemas.ChaosInjectionFlag`. */
export type ChaosInjectionFlag = 'API_FAILURE' | 'CORRUPT_SCHEMA' | 'INFINITE_LOOP';

/** Mirrors backend `app.schemas.HookOption` (strategy-agent output). */
export type HookOption = {
  id: string;
  style: string;
  headline: string;
  reasoning: string;
};

/** Mirrors backend `app.schemas.PlatformStrategyOutput`. */
export type PlatformStrategyOutput = {
  platform: PlatformType;
  hooks: HookOption[];
  algorithm_checklist: string[];
  visual_diagram_mermaid: string;
  claude_meta_prompt: string;
};

export type GeneratePlaybookPayload = {
  /** Raw transcript / notes text. May be empty when `mediaFile` is provided. */
  transcriptText: string;
  /** Optional focus direction / target-audience guidance. */
  focusDirection: string;
  strategicAngle: StrategicAngle;
  activePlatform: PlatformType;
  /** Optional chaos-engineering mode (exercises backend resilience paths). */
  chaosInjectionFlag?: ChaosInjectionFlag | null;
  /** Audio/video file to transcribe server-side. */
  mediaFile?: File | null;
  /** Optional checkpoint thread id — reuse it to resume a previous run. */
  threadId?: string;
};

/** Normalized pipeline-step event (derived from backend `start`/`step` frames). */
export type StatusEvent = {
  type: 'status';
  /** Pipeline phase: 01 ingest / 02 hooks / 03 visual + prompt. */
  step: '01' | '02' | '03';
  message: string;
  status: 'active' | 'done';
  /** Graph node that emitted the event, when available. */
  node?: string;
};

/** Normalized strategy-output event (one per platform, from the `result` frame). */
export type ResultEvent = {
  type: 'result';
  data: PlatformStrategyOutput;
};

export type DoneInfo = {
  status: 'done' | 'terminated';
  threadId?: string;
  stepCount?: number;
  errorLog: string[];
};

export type StreamHandlers = {
  onStatus?: (event: StatusEvent) => void;
  onResult?: (event: ResultEvent) => void;
  onError?: (message: string) => void;
  onDone?: (info: DoneInfo) => void;
};

/** Error thrown for non-2xx HTTP responses or transport failures. */
export class ApiError extends Error {
  readonly status?: number;
  readonly cause?: unknown;

  constructor(message: string, options?: { status?: number; cause?: unknown }) {
    super(message);
    this.name = 'ApiError';
    this.status = options?.status;
    if (options?.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

const NODE_MESSAGES: Record<string, string> = {
  supervisor: 'Coordinating agents & routing the pipeline',
  strategy_agent: 'Synthesizing platform-specific hooks & algorithm mechanics',
  visual_agent: 'Compiling Mermaid visual diagrams',
  prompt_builder: 'Compiling Claude meta-prompt packages',
};

const PLATFORM_VALUES = new Set<string>(Object.values(PlatformType));

function isKnownPlatform(value: unknown): value is PlatformType {
  return typeof value === 'string' && PLATFORM_VALUES.has(value);
}

/** Map a graph node to the 3-phase pipeline overlay step (01/02/03). */
function stepForNode(node: string | undefined): '01' | '02' | '03' | null {
  switch (node) {
    case 'strategy_agent':
      return '02';
    case 'visual_agent':
    case 'prompt_builder':
      return '03';
    case 'supervisor':
      return '01';
    default:
      return null;
  }
}

/**
 * Read a `text/event-stream` body frame-by-frame, invoking `onFrame` with
 * each parsed `event:`/`data:` pair. Handles CRLF, multi-line data, SSE
 * comments (keep-alives) and `id`/`retry` fields (ignored).
 */
async function readEventStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onFrame: (eventName: string, data: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let eventName = '';
  const dataLines: string[] = [];

  const flush = () => {
    if (dataLines.length === 0) return;
    const data = dataLines.join('\n');
    dataLines.length = 0;
    onFrame(eventName, data);
    eventName = '';
  };

  for (;;) {
    if (signal?.aborted) return;
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex: number;
    while ((newlineIndex = buffer.search(/\r?\n/)) !== -1) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + (buffer[newlineIndex] === '\r' ? 2 : 1));

      if (line === '') {
        // Blank line = end of the current event.
        flush();
        continue;
      }
      if (line.startsWith(':')) continue; // SSE comment / keep-alive

      const separator = line.indexOf(':');
      if (separator === -1) continue;
      const field = line.slice(0, separator);
      let value = line.slice(separator + 1);
      if (value.startsWith(' ')) value = value.slice(1);

      if (field === 'event') eventName = value;
      else if (field === 'data') dataLines.push(value);
      // `id` and `retry` fields are intentionally ignored.
    }
  }
  flush();
}

/** Normalize one parsed SSE frame into typed handler calls. */
function dispatchFrame(eventName: string, data: string, handlers: StreamHandlers): void {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return; // non-JSON frame (keep-alive, etc.) — nothing to dispatch
  }

  const type = typeof payload['type'] === 'string' ? payload['type'] : eventName;

  switch (type) {
    case 'start':
      handlers.onStatus?.({
        type: 'status',
        step: '01',
        status: 'active',
        message: 'Ingesting media & extracting core technical insights',
      });
      break;

    case 'step': {
      const node = typeof payload['node'] === 'string' ? payload['node'] : undefined;
      const step = stepForNode(node);
      if (!step) break;
      handlers.onStatus?.({
        type: 'status',
        step,
        node,
        status: payload['status'] === 'done' ? 'done' : 'active',
        message: (node && NODE_MESSAGES[node]) || 'Running agents…',
      });
      break;
    }

    case 'result': {
      const finalState = (payload['final_state'] ?? {}) as Record<string, unknown>;
      const results = (finalState['strategy_results'] ?? {}) as Record<string, unknown>;
      for (const raw of Object.values(results)) {
        // Skip malformed / unknown-platform entries so corrupted output
        // (e.g. chaos modes) never flows into the strategy store.
        const output = raw as Partial<PlatformStrategyOutput>;
        if (!output || !isKnownPlatform(output.platform)) continue;
        handlers.onResult?.({
          type: 'result',
          data: output as PlatformStrategyOutput,
        });
      }
      handlers.onDone?.({
        status: payload['status'] === 'terminated' ? 'terminated' : 'done',
        threadId: typeof payload['thread_id'] === 'string' ? payload['thread_id'] : undefined,
        stepCount: typeof payload['step_count'] === 'number' ? payload['step_count'] : undefined,
        errorLog: Array.isArray(payload['error_log']) ? (payload['error_log'] as string[]) : [],
      });
      break;
    }

    case 'error': {
      const detail = payload['detail'];
      const message =
        typeof detail === 'string'
          ? detail
          : typeof payload['message'] === 'string'
            ? payload['message']
            : 'The pipeline reported an unknown backend error.';
      handlers.onError?.(message);
      break;
    }
  }
}

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as Record<string, unknown> | null)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((entry) => {
          if (typeof entry === 'string') return entry;
          const msg = (entry as Record<string, unknown> | null)?.msg;
          return typeof msg === 'string' ? msg : JSON.stringify(entry);
        })
        .join('; ');
    }
    if (detail !== undefined && detail !== null) return JSON.stringify(detail);
  } catch {
    // Response body is not JSON — fall through to the generic message.
  }
  return `Request failed with status ${response.status} ${response.statusText}`.trim();
}

/**
 * POST `/api/generate/stream` with multipart FormData and consume the
 * Server-Sent Events response, invoking the provided handlers as frames
 * arrive. Resolves when the stream completes; rejects on HTTP errors,
 * transport failures, or (rethrows) `AbortError` when `signal` is aborted.
 */
export async function generatePlaybookStream(
  payload: GeneratePlaybookPayload,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append('transcript_text', payload.transcriptText ?? '');
  form.append('focus_direction', payload.focusDirection ?? '');
  form.append('strategic_angle', payload.strategicAngle);
  form.append('active_platform', payload.activePlatform);
  if (payload.chaosInjectionFlag) form.append('chaos_injection_flag', payload.chaosInjectionFlag);
  if (payload.threadId) form.append('thread_id', payload.threadId);
  if (payload.mediaFile) form.append('media', payload.mediaFile, payload.mediaFile.name);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/generate/stream`, {
      method: 'POST',
      body: form,
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(
      'Could not reach the Meta Pro backend. Make sure the API is running ' +
        '(uvicorn app.main:app) and VITE_API_BASE_URL is correct.',
      { cause: error },
    );
  }

  if (!response.ok) {
    throw new ApiError(await extractErrorDetail(response), { status: response.status });
  }
  if (!response.body) {
    throw new ApiError('The backend returned an empty response body.');
  }

  await readEventStream(
    response.body.getReader(),
    (eventName, data) => dispatchFrame(eventName, data, handlers),
    signal,
  );
}
