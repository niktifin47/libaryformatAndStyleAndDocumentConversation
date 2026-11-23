import { importOptional } from "../optional.ts";
import type { Document } from "../models.ts";
import { headingSizePt } from "../style.ts";
import type { ResolvedStyle } from "../style.ts";
import { strongSpans } from "./inline.ts";
import type { InlineSpan } from "./inline.ts";

const PAGE_MARGIN = 72;
// Code points above Latin-1 that Windows-1252 (the encoding of PDF's built-in fonts) can represent.
const WIN_ANSI_EXTRAS = new Set([
  0x20ac, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160, 0x2039, 0x0152,
  0x017d, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x02dc, 0x2122, 0x0161, 0x203a,
  0x0153, 0x017e, 0x0178,
]);

// PDF's built-in fonts cannot draw other characters, so they are replaced instead of drawn as garbage.
function toBuiltInFontSpans(text: string): InlineSpan[] {
  const output: InlineSpan[] = [];
  let pendingSpace = false;
  let wroteText = false;
  for (const span of strongSpans(text.trim())) {
    let part = "";
    for (const character of span.text) {
      if (" \t\n\v\f\r".includes(character)) {
        pendingSpace = true;
        continue;
      }
      if (pendingSpace && wroteText) part += " ";
      pendingSpace = false;
      const codePoint = character.codePointAt(0) as number;
      const drawable =
        (codePoint >= 0x20 && codePoint <= 0x7e) ||
        (codePoint >= 0xa0 && codePoint <= 0xff) ||
        WIN_ANSI_EXTRAS.has(codePoint);
      part += drawable ? character : "?";
      wroteText = true;
    }
    if (part) output.push({ text: part, strong: span.strong });
  }
  return output;
}

/** Draw the document text with PDF's built-in Helvetica or Times fonts. */
export async function renderPdf(document: Document, style: ResolvedStyle): Promise<Uint8Array> {
  const { default: PDFDocument } = await importOptional(
    () => import("pdfkit"),
    "Writing PDF",
    "pdfkit",
  );
  const { template, colors } = style;
  const serif = template.fontFamily.toLowerCase().includes("times");
  const bodyFont = serif ? "Times-Roman" : "Helvetica";
  const boldFont = serif ? "Times-Bold" : "Helvetica-Bold";

  const pdf = new PDFDocument({ size: "LETTER", margin: PAGE_MARGIN, autoFirstPage: false });
  const chunks: Buffer[] = [];
  const finished = new Promise<Uint8Array>((resolve, reject) => {
    pdf.on("data", (chunk: Buffer) => chunks.push(chunk));
    pdf.on("end", () => resolve(Buffer.concat(chunks)));
    pdf.on("error", reject);
  });
  pdf.on("pageAdded", () => {
    if (colors.background.toLowerCase() !== "#ffffff") {
      pdf.save();
      pdf.rect(0, 0, pdf.page.width, pdf.page.height).fill(colors.background);
      pdf.restore();
    }
  });
  pdf.addPage();

  const write = (
    text: string,
    font: string,
    size: number,
    color: string,
    spaceBefore: number,
    spaceAfter: number,
  ): void => {
    const spans = toBuiltInFontSpans(text);
    if (spans.length === 0) return;
    pdf.font(font).fontSize(size);
    if (spaceBefore && pdf.y > pdf.page.margins.top) pdf.y += spaceBefore;
    const lineGap = Math.max(0, size * 1.4 - pdf.currentLineHeight(true));
    spans.forEach((span, index) => {
      pdf.font(span.strong ? boldFont : font).fillColor(span.strong ? colors.accent : color)
        .text(span.text, { align: "left", lineGap, continued: index < spans.length - 1 });
    });
    pdf.y += spaceAfter;
  };

  try {
    let orderedNumber = 0;
    for (const block of document.blocks) {
      if (block.kind.startsWith("heading")) {
        orderedNumber = 0;
        const level = Math.min(Number(block.kind.slice("heading".length)), 6);
        write(block.text, boldFont, headingSizePt(template, level), colors.heading, 10, 6);
      } else if (block.kind === "list_item" || block.kind === "ordered_item") {
        let marker = "\u2022";
        if (block.kind === "ordered_item") marker = `${++orderedNumber}.`;
        else orderedNumber = 0;
        write(`${marker} ${block.text}`, bodyFont, template.fontSizePt, colors.text, 0, 3);
      } else {
        orderedNumber = 0;
        write(block.text, bodyFont, template.fontSizePt, colors.text, 0, 6);
      }
    }
  } catch (error) {
    finished.catch(() => undefined);
    pdf.end();
    throw error;
  }
  pdf.end();
  return finished;
}
