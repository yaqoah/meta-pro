/**
 * Adapters between the backend API wire shapes (`@/services/api`) and the
 * frontend presentation shapes (`@/data/platforms`).
 *
 * The backend uses `PlatformType` enum values (`x_thread`) and snake_case
 * strategy fields (`algorithm_checklist`, `visual_diagram_mermaid`, ...)
 * with `reasoning` on hooks; the UI components consume `PlatformId`
 * (`xthread`), camelCase fields and a `description` on hooks.
 */
import { PlatformType, type PlatformStrategyOutput } from '@/services/api';
import { platforms, type Platform, type PlatformId } from '@/data/platforms';

const TYPE_TO_ID: Record<PlatformType, PlatformId> = {
  [PlatformType.LINKEDIN]: 'linkedin',
  [PlatformType.X_THREAD]: 'xthread',
  [PlatformType.MEDIUM]: 'medium',
};

const ID_TO_TYPE: Record<PlatformId, PlatformType> = {
  linkedin: PlatformType.LINKEDIN,
  xthread: PlatformType.X_THREAD,
  medium: PlatformType.MEDIUM,
};

export function platformTypeToId(type: PlatformType): PlatformId {
  return TYPE_TO_ID[type];
}

export function platformIdToType(id: PlatformId): PlatformType {
  return ID_TO_TYPE[id];
}

/** "contrarian" -> "Contrarian", "stat-led" -> "Stat Led". */
function prettifyStyle(style: string): string {
  return style
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

/** Convert one backend strategy output into the frontend `Platform` shape. */
export function strategyToPlatform(output: PlatformStrategyOutput): Platform {
  const id = platformTypeToId(output.platform);
  const config = platforms[id];
  return {
    id,
    label: config.label,
    hooks: (output.hooks ?? []).map((hook) => ({
      id: hook.id,
      style: prettifyStyle(hook.style),
      headline: hook.headline,
      description: hook.reasoning,
    })),
    checklist: output.algorithm_checklist ?? [],
    mermaidCode: output.visual_diagram_mermaid ?? '',
    metaPrompt: output.claude_meta_prompt ?? '',
  };
}

/** Convert the hook's per-platform strategy map into frontend platform data. */
export function strategyDataToPlatforms(
  data: Partial<Record<PlatformType, PlatformStrategyOutput>>,
): Partial<Record<PlatformId, Platform>> {
  const result: Partial<Record<PlatformId, Platform>> = {};
  for (const [type, output] of Object.entries(data) as [
    PlatformType,
    PlatformStrategyOutput,
  ][]) {
    if (output) result[platformTypeToId(type)] = strategyToPlatform(output);
  }
  return result;
}
