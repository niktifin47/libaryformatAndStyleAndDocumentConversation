package com.niktifin47.apiformatfix

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.io.ByteArrayInputStream
import java.util.zip.ZipInputStream

@RunWith(RobolectricTestRunner::class)
class OklchColorTest {
    @Test
    fun sharedReferenceVectorsAreDeterministic() {
        val resource = requireNotNull(javaClass.getResourceAsStream("/oklch.json"))
        val vectors = JSONObject(resource.bufferedReader().use { it.readText() }).getJSONArray("vectors")
        for (index in 0 until vectors.length()) {
            val vector = vectors.getJSONObject(index)
            val color = OklchColor(vector.getDouble("l"), vector.getDouble("c"), vector.getDouble("h"))
            assertEquals(vector.getString("name"), vector.getString("hex"), color.toHex())
            assertEquals(vector.getString("hex"), color.toHex())
        }
        assertEquals("#ee1300", OklchColor(0.6, 1e308, 30.0).toHex())
    }

    @Test
    fun invalidComponentsFailExplicitly() {
        val invalid = listOf(
            Triple(-0.1, 0.0, 0.0), Triple(1.1, 0.0, 0.0), Triple(0.5, -0.1, 0.0),
            Triple(Double.NaN, 0.0, 0.0), Triple(0.5, Double.POSITIVE_INFINITY, 0.0),
            Triple(0.5, 0.0, Double.NEGATIVE_INFINITY),
        )
        invalid.forEach { (l, c, h) -> assertThrows(IllegalArgumentException::class.java) { OklchColor(l, c, h) } }
    }

    @Test
    fun harmonizationUsesSharedShortestArcVectors() {
        val resource = requireNotNull(javaClass.getResourceAsStream("/oklch.json"))
        val vectors = JSONObject(resource.bufferedReader().use { it.readText() }).getJSONArray("harmonization")
        for (index in 0 until vectors.length()) {
            val vector = vectors.getJSONObject(index)
            val color = OklchColor(0.6, vector.getDouble("c"), vector.getDouble("h"))
            val result = color.harmonize(vector.getDouble("target"), vector.getDouble("strength"))
            assertEquals(vector.getString("name"), vector.getDouble("expected"), result.hue, 1e-10)
            assertEquals(color.lightness, result.lightness, 0.0)
            assertEquals(color.chroma, result.chroma, 0.0)
            assertEquals(vector.getDouble("h"), color.hue, 0.0)
        }
        val neutral = OklchColor(1.0, 0.0, 720.0)
        for ((reference, strength) in listOf(
            Double.NaN to 0.5, 10.0 to Double.POSITIVE_INFINITY, 10.0 to -0.1, 10.0 to 1.1,
        )) {
            assertThrows(IllegalArgumentException::class.java) { neutral.harmonize(reference, strength) }
        }
        val color = OklchColor(0.6, 0.2, 350.0)
        val palette = OklchPalette("custom", color, color, color, neutral)
        val result = palette.harmonize(10.0, 0.5)
        assertEquals(listOf(0.0, 0.0, 0.0), listOf(result.text.hue, result.heading.hue, result.accent.hue))
        assertEquals(neutral, result.background)
        assertEquals(350.0, palette.text.hue, 0.0)
    }

    @Test
    fun modifyingAndExportingDoesNotChangeSourcePalette() {
        val color = OklchColor(0.7, 0.1, -180.0)
        val palette = OklchPalette("custom", color, color, color)
        val modified = palette.copy(heading = OklchColor(0.5, 0.0, 0.0))
        assertEquals("#636363", modified.heading.toHex())
        val template = FormatTemplate("custom", "Arial", 11f, 16f, "custom")
        val html = ApiFormatFix.formatText("# Test", "md", "html", template, palette.toColorScheme())
        assertTrue(html.contains("#4bb3a1"))
        assertEquals(-180.0, palette.heading.hue, 0.0)
    }

    @Test
    fun binaryOutputsRenderStrongTextWithAccent() {
        val context = RuntimeEnvironment.getApplication()
        val template = FormatTemplate("custom", "Arial", 11f, 16f, "custom")
        val colors = FormatColorScheme("custom", "#111111", "#222222", "#336699")
        val source = "# Title **Hot**\n\nBefore **safe <tag>&** after **red** unmatched **open\n\n- item **wow**"
        val docx = ApiFormatFix.formatContent(context, source, "md", "docx", template, colors)
        var xml = ""
        ZipInputStream(ByteArrayInputStream(docx)).use {
            while (true) {
                val entry = it.nextEntry ?: break
                if (entry.name == "word/document.xml") xml = it.readBytes().toString(Charsets.UTF_8)
            }
        }
        assertEquals(4, Regex("""<w:b/><w:color w:val="336699"/>""").findAll(xml).count())
        assertTrue(xml.contains("safe &lt;tag&gt;&amp;"))
        assertTrue(xml.contains("unmatched **open"))
        val bytes = ApiFormatFix.formatContent(context, source, "md", "pdf", template, colors)
        PDDocument.load(ByteArrayInputStream(bytes)).use { pdf ->
            val content = pdf.getPage(0).contents.readBytes().toString(Charsets.ISO_8859_1)
            val text = PDFTextStripper().getText(pdf)
            assertTrue(content.contains("0.2 0.4 0.6 sc"))
            assertTrue(text.contains("Before safe <tag>& after red unmatched **open"))
            assertTrue(text.contains("Title Hot"))
        }
    }

    @Test
    fun accentedTextWrapsAcrossPdfPagesWithoutLosingWords() {
        val context = RuntimeEnvironment.getApplication()
        val template = FormatTemplate("custom", "Arial", 11f, 16f, "custom")
        val colors = FormatColorScheme("custom", "#111111", "#222222", "#336699")
        val source = "Before **" + "bold word ".repeat(600) + "** after"
        val bytes = ApiFormatFix.formatContent(context, source, "md", "pdf", template, colors)
        PDDocument.load(ByteArrayInputStream(bytes)).use { pdf ->
            assertTrue(pdf.numberOfPages > 1)
            val text = PDFTextStripper().getText(pdf).replace(Regex("\\s+"), " ")
            assertEquals(600, Regex("bold word").findAll(text).count())
            assertTrue(text.contains("Before bold word"))
            assertTrue(text.contains("bold word after"))
            for (page in pdf.pages) {
                assertTrue(page.contents.readBytes().toString(Charsets.ISO_8859_1).contains("0.2 0.4 0.6 sc"))
            }
        }
    }

    @Test
    fun backgroundIsAppliedToDocxAndEveryPdfPage() {
        val context = RuntimeEnvironment.getApplication()
        val template = FormatTemplate("custom", "Arial", 11f, 16f, "custom")
        val source = "# Title\n\n" + (0 until 250).joinToString("\n\n") { "Paragraph $it" }
        for (background in listOf("#123456", "#ffffff")) {
            val colors = FormatColorScheme("custom", "#111111", "#222222", "#333333", background)
            val docx = ApiFormatFix.formatContent(context, source, "md", "docx", template, colors)
            val zip = ZipInputStream(ByteArrayInputStream(docx))
            var documentXml = ""
            var stylesXml = ""
            zip.use {
                while (true) {
                    val entry = it.nextEntry ?: break
                    if (entry.name == "word/document.xml") documentXml = it.readBytes().toString(Charsets.UTF_8)
                    if (entry.name == "word/styles.xml") stylesXml = it.readBytes().toString(Charsets.UTF_8)
                }
            }
            if (background == "#ffffff") assertTrue(!documentXml.contains("<w:background"))
            else assertTrue(documentXml.contains("""<w:background w:color="123456"/>"""))
            assertTrue(stylesXml.contains("""w:color w:val="111111""""))
            assertTrue(stylesXml.contains("""w:color w:val="222222""""))

            val bytes = ApiFormatFix.formatContent(context, source, "md", "pdf", template, colors)
            PDDocument.load(ByteArrayInputStream(bytes)).use { pdf ->
                assertTrue(pdf.numberOfPages > 1)
                val firstPage = pdf.getPage(0).contents.readBytes().toString(Charsets.ISO_8859_1)
                assertTrue(firstPage.contains("0.06667 0.06667 0.06667 sc"))
                assertTrue(firstPage.contains("0.13333 0.13333 0.13333 sc"))
                for (page in pdf.pages) {
                    val contents = page.contents.readBytes().toString(Charsets.ISO_8859_1)
                    if (background == "#ffffff") assertTrue(!contents.contains("0 0 612 792 re"))
                    else {
                        assertTrue(contents.contains("0 0 612 792 re"))
                        assertTrue(contents.contains("0.07059 0.20392 0.33725 sc"))
                    }
                }
            }
        }
    }
}
