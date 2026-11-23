export interface InlineSpan {
  readonly text: string;
  readonly strong: boolean;
}

/** Split nonempty, single-line strong spans without backtracking on untrusted text. */
export function strongSpans(text: string): InlineSpan[] {
  const spans: InlineSpan[] = [];
  let position = 0;
  while (position < text.length) {
    const start = text.indexOf("**", position);
    if (start < 0) {
      spans.push({ text: text.slice(position), strong: false });
      break;
    }
    const end = text.indexOf("**", start + 3);
    const newline = text.slice(start + 2, end < 0 ? undefined : end).indexOf("\n");
    if (newline >= 0) {
      const next = start + 3 + newline;
      spans.push({ text: text.slice(position, next), strong: false });
      position = next;
    } else if (end < 0) {
      spans.push({ text: text.slice(position), strong: false });
      break;
    } else {
      if (start > position) spans.push({ text: text.slice(position, start), strong: false });
      spans.push({ text: text.slice(start + 2, end), strong: true });
      position = end + 2;
    }
  }
  return spans;
}
