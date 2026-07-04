import { Check, Copy } from "lucide-react";
import { useState } from "react";

interface Props {
  command: string;
}

/** A monospace command line with a copy-to-clipboard button. */
export function CopyCommand({ command }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (insecure context) — the text is still selectable */
    }
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-forest-deep/95 px-3 py-2">
      <code className="flex-1 overflow-x-auto whitespace-pre font-mono text-xs text-mint">
        {command}
      </code>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? "Copied" : "Copy command"}
        title={copied ? "Copied" : "Copy"}
        className="shrink-0 rounded-md p-1 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
      >
        {copied ? (
          <Check size={15} className="text-mint" />
        ) : (
          <Copy size={15} />
        )}
      </button>
    </div>
  );
}
