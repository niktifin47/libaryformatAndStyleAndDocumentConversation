package com.niktifin47.apiformatfix

import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/** Source OKLCH components; hue is normalized only when exporting. */
data class OklchColor(val lightness: Double, val chroma: Double, val hue: Double) {
    init {
        require(lightness.isFinite() && chroma.isFinite() && hue.isFinite()) {
            "OKLCH components must be finite numbers."
        }
        require(lightness in 0.0..1.0 && chroma >= 0.0) {
            "OKLCH lightness must be in [0, 1] and chroma must be nonnegative."
        }
    }

    fun harmonize(referenceHue: Double, strength: Double): OklchColor {
        require(referenceHue.isFinite() && strength.isFinite()) {
            "Reference hue and strength must be finite numbers."
        }
        require(strength in 0.0..1.0) { "Harmonization strength must be in [0, 1]." }
        if (chroma == 0.0 || strength == 0.0) return this
        val source = ((hue % 360.0) + 360.0) % 360.0
        val target = ((referenceHue % 360.0) + 360.0) % 360.0
        var delta = ((target - source + 540.0) % 360.0) - 180.0
        if (delta == -180.0) delta = 180.0
        if (delta == 0.0) return this
        return copy(hue = ((source + delta * strength) % 360.0 + 360.0) % 360.0)
    }

    fun toHex(): String {
        val angle = Math.toRadians(((hue % 360.0) + 360.0) % 360.0)
        val cosine = cos(angle)
        val sine = sin(angle)
        fun linear(chroma: Double): List<Double> {
            val a = chroma * cosine
            val b = chroma * sine
            val l = (lightness + 0.3963377774 * a + 0.2158037573 * b).pow(3)
            val m = (lightness - 0.1055613458 * a - 0.0638541728 * b).pow(3)
            val s = (lightness - 0.0894841775 * a - 1.291485548 * b).pow(3)
            return listOf(
                4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
            )
        }
        fun inGamut(rgb: List<Double>) = rgb.all { it >= -1e-7 && it <= 1 + 1e-7 }
        // All sRGB colors have OKLCH chroma below 4; the bound avoids overflow.
        val limitedChroma = min(chroma, 4.0)
        var rgb = linear(limitedChroma)
        if (!inGamut(rgb)) {
            var low = 0.0
            var high = limitedChroma
            repeat(32) {
                val mid = (low + high) / 2
                if (inGamut(linear(mid))) low = mid else high = mid
            }
            rgb = linear(low)
        }
        return "#" + rgb.joinToString("") {
            val channel = it.coerceIn(0.0, 1.0)
            val encoded =
                if (channel <= 0.0031308) 12.92 * channel
                else 1.055 * channel.pow(1.0 / 2.4) - 0.055
            floor(encoded * 255 + 0.5).toInt().toString(16).padStart(2, '0')
        }
    }
}

/** Immutable palette that can be copied without modifying the original values. */
data class OklchPalette(
    val name: String,
    val text: OklchColor,
    val heading: OklchColor,
    val accent: OklchColor,
    val background: OklchColor = OklchColor(1.0, 0.0, 0.0),
) {
    fun toColorScheme() =
        FormatColorScheme(name, text.toHex(), heading.toHex(), accent.toHex(), background.toHex())

    fun harmonize(referenceHue: Double, strength: Double) = copy(
        text = text.harmonize(referenceHue, strength),
        heading = heading.harmonize(referenceHue, strength),
        accent = accent.harmonize(referenceHue, strength),
        background = background.harmonize(referenceHue, strength),
    )
}
