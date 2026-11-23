import hashlib
import json
import time
from dataclasses import FrozenInstanceError, replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from api_format_fix import COLOR_SCHEMES, ColorScheme, OklchColor, OklchPalette, format_content

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "test-fixtures" / "oklch.json").read_text(
        encoding="utf-8"
    )
)
VECTORS = FIXTURE["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_reference_vectors(vector):
    color = OklchColor(vector["l"], vector["c"], vector["h"])
    assert color.to_hex() == vector["hex"]
    assert color.to_hex() == vector["hex"]


@pytest.mark.parametrize(
    "values",
    [(-0.1, 0, 0), (1.1, 0, 0), (0.5, -0.1, 0), (float("nan"), 0, 0),
     (0.5, float("inf"), 0), (0.5, 0, float("-inf")), (True, 0, 0), ("0.5", 0, 0),
     (10**400, 0, 0)],
)
def test_invalid_components_fail_explicitly(values):
    with pytest.raises(ValueError, match="OKLCH"):
        OklchColor(*values)


def test_palette_is_immutable_and_rendering_uses_a_separate_snapshot():
    color = OklchColor(0.7, 0.1, -180)
    palette = OklchPalette("custom", color, color, color)
    modified = replace(palette, heading=OklchColor(0.5, 0, 0))
    with pytest.raises(FrozenInstanceError):
        palette.heading = color
    with pytest.raises(ValueError, match="OklchColor"):
        replace(palette, text="#ffffff")
    assert palette.heading == color
    assert modified.heading.to_hex() == "#636363"
    assert "#4bb3a1" in format_content("# Test", ".md", ".html", color_scheme=palette)
    assert palette.heading.hue == -180


def test_extreme_finite_chroma_is_reduced_without_overflow():
    assert OklchColor(0.6, 1e308, 30).to_hex() == "#ee1300"


@pytest.mark.parametrize("vector", FIXTURE["harmonization"], ids=lambda vector: vector["name"])
def test_harmonization_reference_vectors(vector):
    color = OklchColor(0.6, vector["c"], vector["h"])
    result = color.harmonize(vector["target"], vector["strength"])
    assert result.hue == pytest.approx(vector["expected"])
    assert (result.lightness, result.chroma) == (color.lightness, color.chroma)
    assert color.hue == vector["h"]


@pytest.mark.parametrize(
    ("reference", "strength"),
    [(float("nan"), 0.5), (10, float("inf")), (True, 0.5), (10, -0.1), (10, 1.1)],
)
def test_harmonization_rejects_invalid_values(reference, strength):
    with pytest.raises(ValueError):
        OklchColor(0.5, 0.0, 0).harmonize(reference, strength)


def test_palette_harmonization_applies_to_all_chromatic_roles():
    color = OklchColor(0.6, 0.2, 350)
    neutral = OklchColor(1, 0, 720)
    palette = OklchPalette("custom", color, color, color, neutral)
    result = palette.harmonize(10, 0.5)
    assert (result.text.hue, result.heading.hue, result.accent.hue) == (0, 0, 0)
    assert result.background is neutral
    assert palette.text.hue == 350


def test_all_legacy_palette_values_are_unchanged():
    values = [
        [v.name, v.text, v.heading, v.accent, v.background]
        for _, v in sorted(COLOR_SCHEMES.items())
    ]
    serialized = json.dumps(values, separators=(",", ":")).encode()
    assert hashlib.sha256(serialized).hexdigest() == FIXTURE["legacy_schemes_sha256"]


def test_docx_and_pdf_render_strong_spans_with_accent_and_preserve_unmatched_text():
    from docx import Document as WordDocument
    from pypdf import PdfReader

    scheme = ColorScheme("custom", "#111111", "#222222", "#336699")
    source = "# Title **Hot**\n\nBefore **safe <tag>&** after **red** unmatched **open\n\n- item **wow**"
    docx = format_content(source, ".md", ".docx", color_scheme=scheme)
    document = WordDocument(BytesIO(docx))
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "Title Hot", "Before safe <tag>& after red unmatched **open", "item wow"
    ]
    strong = [run for paragraph in document.paragraphs for run in paragraph.runs if run.bold]
    assert [run.text for run in strong] == ["Hot", "safe <tag>&", "red", "wow"]
    assert all(str(run.font.color.rgb) == "336699" for run in strong)
    pdf = PdfReader(BytesIO(format_content(source, ".md", ".pdf", color_scheme=scheme)))
    content = pdf.pages[0].get_contents().get_data()
    text = pdf.pages[0].extract_text()
    assert b".2 .4 .6 rg" in content
    assert "Before safe <tag>& after red unmatched **open" in text
    assert "Title Hot" in text


def test_strong_span_scanning_stays_linear_on_untrusted_text():
    from api_format_fix.renderer import _strong_spans

    source = "**x**" * 50_000 + " **unclosed"
    started = time.monotonic()
    spans = _strong_spans(source)
    assert time.monotonic() - started < 2
    assert len(spans) == 50_001
    assert spans[-1] == (" **unclosed", False)
    assert _strong_spans("**first\nsecond**") == [("**first\n", False), ("second**", False)]


@pytest.mark.parametrize("background", ["#123456", "#ffffff"])
def test_docx_and_all_pdf_pages_have_the_selected_background(background):
    from pypdf import PdfReader

    scheme = ColorScheme("custom", "#111111", "#222222", "#333333", background)
    source = "# Title\n\n" + "\n\n".join(f"Paragraph {index}" for index in range(250))
    docx = format_content(source, ".md", ".docx", color_scheme=scheme)
    with ZipFile(BytesIO(docx)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        styles = archive.read("word/styles.xml").decode("utf-8")
    assert 'w:color w:val="111111"' in styles
    assert 'w:color w:val="222222"' in styles
    if background == "#ffffff":
        assert "<w:background" not in xml
    else:
        assert '<w:background w:color="123456"' in xml

    pdf = format_content(source, ".md", ".pdf", color_scheme=scheme)
    pages = PdfReader(BytesIO(pdf)).pages
    assert len(pages) > 1
    first_page = pages[0].get_contents().get_data()
    assert b".066667 .066667 .066667 rg" in first_page
    assert b".133333 .133333 .133333 rg" in first_page
    for page in pages:
        contents = page.get_contents().get_data()
        if background == "#ffffff":
            assert b"0 0 612 792 re" not in contents
        else:
            assert b"0 0 612 792 re" in contents
            assert b".070588 .203922 .337255 rg" in contents
