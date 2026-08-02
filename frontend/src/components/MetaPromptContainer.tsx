import { Copy, Check, Terminal } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { useToast } from '@/hooks/useToast';

type Props = {
  prompt: string;
};

export default function MetaPromptContainer({ prompt }: Props) {
  const { showToast } = useToast();
  const { copied, copy } = useCopyToClipboard(() =>
    showToast('Copied to Clipboard!'),
  );

  return (
    <div>
      <div className="flex items-center gap-2">
        <Terminal className="h-4 w-4 text-spark" />
        <h3 className="font-serif text-xl text-white tracking-tight">
          Claude 3.5 Sonnet Prompt Package
        </h3>
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        A structured meta-prompt ready to paste into Claude for full draft generation.
      </p>

      <div className="mt-4 rounded-xl border border-edge bg-ink overflow-hidden">
        {/* Action bar */}
        <div className="flex items-center justify-between border-b border-edge px-4 py-2.5">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-neutral-700" />
            <span className="h-2.5 w-2.5 rounded-full bg-neutral-700" />
            <span className="h-2.5 w-2.5 rounded-full bg-neutral-700" />
            <span className="ml-2 font-mono text-xs text-neutral-600">meta-prompt.md</span>
          </div>
          <button
            onClick={() => copy(prompt)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-mono font-semibold transition-all ${
              copied
                ? 'bg-spark/20 text-spark border border-spark/40'
                : 'bg-spark text-black border border-spark shadow-[0_0_15px_rgba(255,229,0,0.25)] hover:shadow-[0_0_20px_rgba(255,229,0,0.35)]'
            }`}
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? 'Copied to Clipboard!' : 'Copy Prompt to Clipboard'}
          </button>
        </div>
        {/* Code box */}
        <pre className="max-h-72 overflow-y-auto p-4 font-mono text-xs text-neutral-300 leading-relaxed whitespace-pre-wrap scrollbar-thin scrollbar-thumb-[#1C1C22] scrollbar-track-transparent">
{prompt.trim()
  ? prompt
  : 'No meta-prompt generated yet — complete the pipeline to receive your prompt package.'}
        </pre>
      </div>
    </div>
  );
}
