/**
 * Minimal Markdown renderer for the generated reports: `##`/`###` headings,
 * `-` lists, `**bold**`, paragraphs, and `EVD-xxxxxx` citations as chips. The
 * report format is produced by our own writer, so a full parser is not needed
 * (and none is in the stack).
 */
import type { ReactNode } from "react";
import { EvdChip } from "./EvdChip";

const INLINE = /(\*\*[^*]+\*\*|EVD-\d{6})/g;

function inline(text: string, keyBase: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (/^EVD-\d{6}$/.test(part)) return <EvdChip key={key} id={part} />;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={key} className="font-semibold text-primary">{part.slice(2, -2)}</strong>;
    return part;
  });
}

export function Markdown({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = (i: number) => {
    if (list.length) out.push(<ul key={`ul-${i}`}>{list}</ul>);
    list = [];
  };
  text.split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    if (line.startsWith("- ")) {
      list.push(<li key={i}>{inline(line.slice(2), `li${i}`)}</li>);
      return;
    }
    flush(i);
    if (!line.trim()) return;
    if (line.startsWith("### ")) out.push(<h3 key={i}>{inline(line.slice(4), `h${i}`)}</h3>);
    else if (line.startsWith("## ")) out.push(<h2 key={i}>{inline(line.slice(3), `h${i}`)}</h2>);
    else out.push(<p key={i}>{inline(line, `p${i}`)}</p>);
  });
  flush(-1);
  return <div className="md text-sm text-secondary">{out}</div>;
}
