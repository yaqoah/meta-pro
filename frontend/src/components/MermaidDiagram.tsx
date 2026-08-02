import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { Copy, Check, Network } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { useToast } from '@/hooks/useToast';

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    background: '#050505',
    primaryColor: '#0E0E12',
    primaryTextColor: '#E5E5E5',
    primaryBorderColor: '#FFE500',
    lineColor: '#FFE500',
    secondaryColor: '#1C1C22',
    tertiaryColor: '#0E0E12',
    nodeBorder: '#FFE500',
    edgeLabelBackground: '#0E0E12',
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: '13px',
  },
  flowchart: {
    curve: 'basis',
    htmlLabels: true,
  },
});

type Props = {
  code: string;
};

export default function MermaidDiagram({ code }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const { showToast } = useToast();
  const { copied, copy } = useCopyToClipboard(() =>
    showToast('Copied to Clipboard!'),
  );

  useEffect(() => {
    let cancelled = false;
    const id = `mmd-${Math.random().toString(36).slice(2, 9)}`;
    mermaid
      .render(id, code)
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch(() => {
        if (!cancelled) setSvg('');
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  return (
    <div className="rounded-xl border border-edge bg-coal overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge px-5 py-3.5">
        <div className="flex items-center gap-2">
          <Network className="h-4 w-4 text-spark" />
          <span className="text-sm font-semibold text-white">
            Extracted System Architecture
            <span className="text-neutral-600 font-normal"> (Visual Asset)</span>
          </span>
        </div>
        <button
          onClick={() => copy(code)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-ink px-3 py-1.5 text-xs font-mono text-neutral-400 hover:border-spark/50 hover:text-spark transition-colors"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-spark" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied ? 'Copied to Clipboard!' : 'Copy Diagram Code'}
        </button>
      </div>
      <div
        ref={containerRef}
        className="flex items-center justify-center overflow-x-auto bg-ink p-6 scrollbar-thin scrollbar-thumb-[#1C1C22] scrollbar-track-transparent"
      >
        {svg ? (
          <div
            className="mermaid-svg [&>svg]:max-w-full [&>svg]:h-auto"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <p className="font-mono text-xs text-neutral-600">
            {code.trim()
              ? 'Rendering diagram...'
              : 'No diagram generated yet — complete the pipeline to receive a Mermaid flowchart.'}
          </p>
        )}
      </div>
    </div>
  );
}
