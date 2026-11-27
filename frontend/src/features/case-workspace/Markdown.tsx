/**
 * Minimal Markdown renderer for the generated reports: `##`/`###` headings,
 * `-` lists, `**bold**`, paragraphs, and `EVD-xxxxxx` citations as chips. The
 * report format is produced by our own writer, so a full parser is not needed
 * (and none is in the stack). Two shapes the writer emits get a readable
 * layout instead of raw lines:
 * - a list where every item is a proposed action, `type (owner, due in N days): text`,
 *   renders as a table;
 * - consecutive `**Label:** text` lines (the STR sections) render as labelled rows.
 */
import type { ReactNode } from "react";
import { humanize } from "../../lib/format";
import { EvdChip } from "./EvdChip";

// Citations are written as `[EVD-000123]`; the brackets are dropped, the chip shows the id.
const INLINE = /(\*\*[^*]+\*\*|\[?EVD-\d{6}\]?)/g;
const CITATION = /^\[?(EVD-\d{6})\]?$/;
const ACTION_ITEM = /^([a-z][a-z_]+) \(([^,()]+), due in (\d+) days?\): (.+)$/;
const LABELLED = /^\*\*([^*]{1,40}):\*\*\s*(.*)$/;

type Block = { kind: "h2" | "h3" | "p"; text: string } | { kind: "list"; items: string[] } | { kind: "labelled"; rows: [string, string][] };

function inline(text: string, keyBase: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyBase}-${i}`;
    const cited = CITATION.exec(part);
    if (cited) return <EvdChip key={key} id={cited[1]} />;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={key} className="font-semibold text-primary">{part.slice(2, -2)}</strong>;
    return part;
  });
}

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    const labelled = LABELLED.exec(line);
    if (line.startsWith("- ")) {
      if (last?.kind === "list") last.items.push(line.slice(2));
      else blocks.push({ kind: "list", items: [line.slice(2)] });
    } else if (labelled) {
      const row: [string, string] = [labelled[1], labelled[2]];
      if (last?.kind === "labelled") last.rows.push(row);
      else blocks.push({ kind: "labelled", rows: [row] });
    } else if (!line.trim()) {
      continue;
    } else if (line.startsWith("### ")) {
      blocks.push({ kind: "h3", text: line.slice(4) });
    } else if (line.startsWith("## ")) {
      blocks.push({ kind: "h2", text: line.slice(3) });
    } else {
      blocks.push({ kind: "p", text: line });
    }
  }
  return blocks;
}

function ActionTable({ items, k }: { items: RegExpExecArray[]; k: string }) {
  return (
    <table className="my-2 w-full table-fixed border-collapse text-sm">
      <thead>
        <tr className="border-b border-line text-left text-xs text-muted">
          <th className="w-[28%] py-1.5 pr-2 font-normal">Action</th>
          <th className="w-[16%] py-1.5 pr-2 font-normal">Owner</th>
          <th className="w-[10%] py-1.5 pr-2 font-normal">Due</th>
          <th className="py-1.5 font-normal">Details</th>
        </tr>
      </thead>
      <tbody>
        {items.map((m, i) => (
          <tr key={`${k}-${i}`} className="border-b border-line/50 align-top">
            <td className="py-1.5 pr-2 font-medium text-primary">{humanize(m[1])}</td>
            <td className="py-1.5 pr-2 text-secondary">{humanize(m[2])}</td>
            <td className="num py-1.5 pr-2 text-secondary">{m[3] === "0" ? "now" : `${m[3]} d`}</td>
            <td className="py-1.5 text-secondary">{inline(m[4], `${k}-${i}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderBlock(block: Block, i: number): ReactNode {
  const k = `b${i}`;
  switch (block.kind) {
    case "h2":
      return <h2 key={k}>{inline(block.text, k)}</h2>;
    case "h3":
      return <h3 key={k}>{inline(block.text, k)}</h3>;
    case "p":
      return <p key={k}>{inline(block.text, k)}</p>;
    case "labelled":
      return (
        <dl key={k} className="my-2 grid grid-cols-[minmax(90px,140px)_minmax(0,1fr)] gap-x-4 gap-y-2">
          {block.rows.map(([label, text], j) => (
            <div key={`${k}-${j}`} className="contents">
              <dt className="font-semibold text-primary">{label}</dt>
              <dd className="leading-relaxed">{inline(text, `${k}-${j}`)}</dd>
            </div>
          ))}
        </dl>
      );
    case "list": {
      const actions = block.items.map((item) => ACTION_ITEM.exec(item));
      if (actions.every((m): m is RegExpExecArray => m !== null)) return <ActionTable key={k} items={actions} k={k} />;
      return <ul key={k}>{block.items.map((item, j) => <li key={`${k}-${j}`}>{inline(item, `${k}-${j}`)}</li>)}</ul>;
    }
  }
}

export function Markdown({ text }: { text: string }) {
  return <div className="md text-sm text-secondary">{parse(text).map(renderBlock)}</div>;
}
