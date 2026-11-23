import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import { strFromU8, unzipSync } from "fflate";
import { getDocument, OPS } from "pdfjs-dist/legacy/build/pdf.mjs";

import { COLOR_SCHEMES, OklchColor, OklchPalette, formatContent } from "../src/index.ts";
import { strongSpans } from "../src/writers/inline.ts";
import { docx } from "./helpers.ts";

const fixture = JSON.parse(readFileSync(new URL("../../test-fixtures/oklch.json", import.meta.url), "utf8"));
const vectors: { name: string; l: number; c: number; h: number; hex: string }[] =
  fixture.vectors;

test("shared OKLCH reference vectors convert deterministically", () => {
  for (const vector of vectors) {
    const color = new OklchColor(vector.l, vector.c, vector.h);
    assert.equal(color.toHex(), vector.hex, vector.name);
    assert.equal(color.toHex(), vector.hex, vector.name);
  }
  assert.equal(new OklchColor(0.6, 1e308, 30).toHex(), "#ee1300");
});

test("harmonization follows shared shortest-arc vectors without mutating colors", () => {
  for (const vector of fixture.harmonization as {
    name: string; c: number; h: number; target: number; strength: number; expected: number;
  }[]) {
    const color = new OklchColor(0.6, vector.c, vector.h);
    const result = color.harmonize(vector.target, vector.strength);
    assert.equal(result.hue, vector.expected, vector.name);
    assert.equal(result.lightness, color.lightness);
    assert.equal(result.chroma, color.chroma);
    assert.equal(color.hue, vector.h);
  }
  for (const [reference, strength] of [[NaN, 0.5], [10, Infinity], [10, -0.1], [10, 1.1]]) {
    assert.throws(() => new OklchColor(0.5, 0, 0).harmonize(reference!, strength!), /finite|strength/);
  }
  assert.throws(() => new OklchColor(0.5, 0, 0).harmonize(true as never, 0.5), /finite/);
  const color = new OklchColor(0.6, 0.2, 350);
  const neutral = new OklchColor(1, 0, 720);
  const palette = new OklchPalette("custom", color, color, color, neutral);
  const result = palette.harmonize(10, 0.5);
  assert.deepEqual([result.text.hue, result.heading.hue, result.accent.hue], [0, 0, 0]);
  assert.equal(result.background, neutral);
  assert.equal(palette.text.hue, 350);
});

test("invalid OKLCH components and palette colors fail explicitly", () => {
  for (const values of [
    [-0.1, 0, 0], [1.1, 0, 0], [0.5, -0.1, 0], [NaN, 0, 0],
    [0.5, Infinity, 0], [0.5, 0, -Infinity],
  ]) {
    assert.throws(() => new OklchColor(values[0]!, values[1]!, values[2]!), /OKLCH/);
  }
  assert.throws(() => new OklchColor("0.5" as never, 0, 0), /finite/);
  assert.throws(() => new OklchColor(true as never, 0, 0), /finite/);
  const color = new OklchColor(0.7, 0.1, 180);
  assert.throws(() => new OklchPalette("bad", color, "red" as never, color), /OklchColor/);
});

test("all legacy palette values remain identical to the Python baseline", () => {
  const values = Object.keys(COLOR_SCHEMES).sort().map((key) => {
    const color = COLOR_SCHEMES[key]!;
    return [color.name, color.text, color.heading, color.accent, color.background];
  });
  assert.equal(createHash("sha256").update(JSON.stringify(values)).digest("hex"), fixture.legacy_schemes_sha256);
});

test("DOCX and PDF render strong spans with the accent color", async () => {
  const colorScheme = {
    name: "custom", text: "#111111", heading: "#222222", accent: "#336699",
  };
  const source = "# Title **Hot**\n\nBefore **safe <tag>&** after **red** unmatched **open\n\n- item **wow**";
  const docx = await formatContent(source, ".md", ".docx", { colorScheme });
  const xml = strFromU8(unzipSync(docx)["word/document.xml"]!);
  assert.equal((xml.match(/<w:b\/><w:color w:val="336699"\/>/g) ?? []).length, 4);
  assert.match(xml, /safe &lt;tag&gt;&amp;/);
  assert.match(xml, /unmatched \*\*open/);
  const bytes = await formatContent(source, ".md", ".pdf", { colorScheme });
  const loading = getDocument({ data: new Uint8Array(bytes) });
  const pdf = await loading.promise;
  try {
    const page = await pdf.getPage(1);
    const ops = await page.getOperatorList();
    assert.ok(ops.fnArray.some((op, index) => op === OPS.setFillRGBColor && ops.argsArray[index]?.[0] === "#336699"));
    const text = (await page.getTextContent()).items.map((item) => "str" in item ? item.str : "").join("");
    assert.ok(text.includes("Before safe <tag>& after red unmatched **open"));
    assert.ok(text.includes("safe <tag>&"));
    assert.ok(text.includes("unmatched **open"));
  } finally {
    await loading.destroy();
  }
});

test("strong span scanning stays linear on untrusted text", () => {
  const text = "**x**".repeat(50_000) + " **unclosed";
  const started = performance.now();
  const spans = strongSpans(text);
  assert.ok(performance.now() - started < 2000);
  assert.equal(spans.length, 50_001);
  assert.deepEqual(spans.at(-1), { text: " **unclosed", strong: false });
  assert.deepEqual(strongSpans("**first\nsecond**"), [
    { text: "**first\n", strong: false }, { text: "second**", strong: false },
  ]);
});

test("PDF does not interpret strong delimiters across an imported line break", async () => {
  const source = docx("<w:p><w:r><w:t>**first</w:t><w:br/><w:t>second**</w:t></w:r></w:p>");
  const bytes = await formatContent(source, ".docx", ".pdf", {
    colorScheme: { name: "custom", text: "#111111", heading: "#222222", accent: "#336699" },
  });
  const loading = getDocument({ data: new Uint8Array(bytes) });
  try {
    const page = await (await loading.promise).getPage(1);
    const ops = await page.getOperatorList();
    assert.ok(!ops.fnArray.some((op, index) => op === OPS.setFillRGBColor && ops.argsArray[index]?.[0] === "#336699"));
    const text = (await page.getTextContent()).items.map((item) => "str" in item ? item.str : "").join("");
    assert.ok(text.includes("**first second**"));
  } finally {
    await loading.destroy();
  }
});

test("PDF preserves existing trimming of Unicode whitespace around imported text", async () => {
  const source = docx("<w:p><w:r><w:t>\u00a0hello\u00a0</w:t></w:r></w:p>");
  const bytes = await formatContent(source, ".docx", ".pdf");
  const loading = getDocument({ data: new Uint8Array(bytes) });
  try {
    const text = (await (await (await loading.promise).getPage(1)).getTextContent()).items
      .map((item) => "str" in item ? item.str : "").join("");
    assert.equal(text, "hello");
  } finally {
    await loading.destroy();
  }
});

test("PDF preserves strong spans and spaces across wrapped pages", async () => {
  const source = Array.from({ length: 200 }, () => "Before **bold word** after").join("\n\n");
  const bytes = await formatContent(source, ".md", ".pdf", {
    colorScheme: { name: "custom", text: "#111111", heading: "#222222", accent: "#336699" },
  });
  const loading = getDocument({ data: new Uint8Array(bytes) });
  try {
    const pdf = await loading.promise;
    assert.ok(pdf.numPages > 1);
    let text = "";
    for (let index = 1; index <= pdf.numPages; index++) {
      const page = await pdf.getPage(index);
      text += (await page.getTextContent()).items.map((item) => "str" in item ? item.str : "").join("");
      const ops = await page.getOperatorList();
      assert.ok(ops.fnArray.some((op, i) => op === OPS.setFillRGBColor && ops.argsArray[i]?.[0] === "#336699"));
    }
    assert.equal((text.match(/Before bold word after/g) ?? []).length, 200);
  } finally {
    await loading.destroy();
  }
});

test("modification and formatting preserve the source palette", async () => {
  const color = new OklchColor(0.7, 0.1, -180);
  const palette = new OklchPalette("custom", color, color, color);
  const modified = palette.withChanges({ heading: new OklchColor(0.5, 0, 0) });
  assert.equal(modified.heading.toHex(), "#636363");
  const updated = palette.withChanges({
    name: "updated", text: modified.heading, heading: color, accent: modified.heading,
    background: modified.heading,
  });
  assert.equal(updated.name, "updated");
  assert.equal(updated.background.toHex(), "#636363");
  assert.equal(palette.heading.hue, -180);
  assert.ok(Object.isFrozen(palette) && Object.isFrozen(color));
  assert.match(await formatContent("# Test", ".md", ".html", { colorScheme: palette }), /#4bb3a1/);
  assert.equal(palette.heading, color);
});

test("DOCX and every PDF page use the selected background", async () => {
  const source = "# Title\n\n" + Array.from({ length: 200 }, (_, index) => `Paragraph ${index}`).join("\n\n");
  for (const background of ["#123456", "#ffffff"]) {
    const colorScheme = {
      name: "custom", text: "#111111", heading: "#222222", accent: "#333333", background,
    };
    const docx = await formatContent(source, ".md", ".docx", { colorScheme });
    const parts = unzipSync(docx);
    const xml = strFromU8(parts["word/document.xml"]!);
    const styles = strFromU8(parts["word/styles.xml"]!);
    assert.match(styles, /w:color w:val="111111"/);
    assert.match(styles, /w:color w:val="222222"/);
    if (background === "#ffffff") assert.doesNotMatch(xml, /<w:background/);
    else assert.match(xml, /<w:background w:color="123456"\/>/);

    const bytes = await formatContent(source, ".md", ".pdf", { colorScheme });
    const loading = getDocument({ data: new Uint8Array(bytes) });
    const pdf = await loading.promise;
    try {
      assert.ok(pdf.numPages > 1);
      for (let index = 1; index <= pdf.numPages; index++) {
        const ops = await (await pdf.getPage(index)).getOperatorList();
        const colors = ops.fnArray
          .map((operator, position) => operator === OPS.setFillRGBColor ? ops.argsArray[position]?.[0] : null)
          .filter(Boolean);
        assert.equal(colors.includes("#123456"), background === "#123456");
        if (index === 1) {
          assert.ok(colors.includes("#111111"));
          assert.ok(colors.includes("#222222"));
        }
        if (background === "#123456") assert.ok(ops.fnArray.includes(OPS.constructPath));
      }
    } finally {
      await loading.destroy();
    }
  }
});
