import { useState, useCallback } from 'react';

export function useCopyToClipboard(onSuccess?: () => void) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        onSuccess?.();
        setTimeout(() => setCopied(false), 2000);
      } catch {
        setCopied(false);
      }
    },
    [onSuccess],
  );

  return { copied, copy };
}
