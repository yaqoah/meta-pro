import { Fragment, type ReactNode } from 'react';

/**
 * Minimal inline-markdown renderer for short LLM-generated strings.
 *
 * Handles `` `code` ``, `**bold**`, `*italic*` and newlines.
 * Renders React elements only (never `dangerouslySetInnerHTML`), so
 * untrusted LLM output cannot inject markup. Unclosed or malformed markers
 * (e.g. a lone `**`) fall through and render verbatim.
 *
 * Note: underscore-italic (`_text_`) is intentionally NOT supported — LLM
 * output in this domain is full of identifiers (`snake_case`, `__init__`)
 * and `_..._` would mangle them; `*...*` already covers italics.
 */

const INLINE_PATTERN = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\n)/g;

function renderSegment(segment: string, key: number): ReactNode {
  if (segment === '\n') return <br key={key} />;

  const bold = segment.match(/^\*\*(.*)\*\*$/s);
  if (bold) {
    return (
      <strong key={key} className="font-semibold">
        {renderInline(bold[1] ?? '')}
      </strong>
    );
  }

  const italic = segment.match(/^\*([^*\n]+)\*$/);
  if (italic) {
    return <em key={key}>{italic[1]}</em>;
  }

  const code = segment.match(/^`([^`\n]+)`$/);
  if (code) {
    return (
      <code
        key={key}
        className="rounded bg-edge/70 px-1 py-0.5 font-mono text-xs text-spark"
      >
        {code[1]}
      </code>
    );
  }

  return <Fragment key={key}>{segment}</Fragment>;
}

/** Parse one string into styled inline nodes. */
function renderInline(text: string): ReactNode[] {
  return text
    .split(INLINE_PATTERN)
    .filter(Boolean)
    .map((part, i) => renderSegment(part, i));
}

type Props = {
  text: string;
  className?: string;
};

/** Render a short string, honouring inline markdown (bold/italic/code). */
export default function MarkdownText({ text, className }: Props) {
  return <span className={className}>{renderInline(text)}</span>;
}
