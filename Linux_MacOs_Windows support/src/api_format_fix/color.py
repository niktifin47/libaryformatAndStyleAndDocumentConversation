"""Immutable OKLCH colors and deterministic sRGB export."""

import math
from dataclasses import dataclass
from numbers import Real

from .models import ColorScheme


def _finite_number(value: object) -> bool:
    try:
        return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
    except (TypeError, OverflowError):
        return False


@dataclass(frozen=True)
class OklchColor:
    lightness: float
    chroma: float
    hue: float

    def __post_init__(self) -> None:
        for value in (self.lightness, self.chroma, self.hue):
            if not _finite_number(value):
                raise ValueError("OKLCH components must be finite numbers.")
        if not 0 <= self.lightness <= 1 or self.chroma < 0:
            raise ValueError("OKLCH lightness must be in [0, 1] and chroma must be nonnegative.")

    def harmonize(self, reference_hue: float, strength: float) -> "OklchColor":
        if not _finite_number(reference_hue) or not _finite_number(strength):
            raise ValueError("Reference hue and strength must be finite numbers.")
        if not 0 <= strength <= 1:
            raise ValueError("Harmonization strength must be in [0, 1].")
        if self.chroma == 0 or strength == 0:
            return self
        hue = self.hue % 360
        delta = (reference_hue % 360 - hue + 180) % 360 - 180
        if delta == -180:
            delta = 180
        if delta == 0:
            return self
        return OklchColor(self.lightness, self.chroma, (hue + delta * strength) % 360)

    def to_hex(self) -> str:
        angle = math.radians(self.hue % 360)
        cosine, sine = math.cos(angle), math.sin(angle)

        def linear(chroma: float) -> tuple[float, float, float]:
            a, b = chroma * cosine, chroma * sine
            l = (self.lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
            m = (self.lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
            s = (self.lightness - 0.0894841775 * a - 1.291485548 * b) ** 3
            return (
                4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
            )

        def in_gamut(rgb: tuple[float, float, float]) -> bool:
            return all(-1e-7 <= channel <= 1 + 1e-7 for channel in rgb)

        # All sRGB colors have OKLCH chroma below 4; the bound avoids overflow.
        chroma = min(self.chroma, 4.0)
        rgb = linear(chroma)
        if not in_gamut(rgb):
            low, high = 0.0, chroma
            for _ in range(32):
                mid = (low + high) / 2
                if in_gamut(linear(mid)):
                    low = mid
                else:
                    high = mid
            rgb = linear(low)
        channels = []
        for channel in rgb:
            channel = min(1.0, max(0.0, channel))
            encoded = 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055
            channels.append(math.floor(encoded * 255 + 0.5))
        return "#" + "".join(f"{channel:02x}" for channel in channels)


@dataclass(frozen=True)
class OklchPalette:
    name: str
    text: OklchColor
    heading: OklchColor
    accent: OklchColor
    background: OklchColor = OklchColor(1, 0, 0)

    def __post_init__(self) -> None:
        if not all(isinstance(value, OklchColor) for value in (
            self.text, self.heading, self.accent, self.background
        )):
            raise ValueError("Palette colors must be OklchColor values.")

    def to_color_scheme(self) -> ColorScheme:
        return ColorScheme(
            self.name, self.text.to_hex(), self.heading.to_hex(),
            self.accent.to_hex(), self.background.to_hex(),
        )

    def harmonize(self, reference_hue: float, strength: float) -> "OklchPalette":
        return OklchPalette(
            self.name,
            self.text.harmonize(reference_hue, strength),
            self.heading.harmonize(reference_hue, strength),
            self.accent.harmonize(reference_hue, strength),
            self.background.harmonize(reference_hue, strength),
        )
