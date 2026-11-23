import { InvalidOptionError } from "./errors.ts";
import type { ColorScheme } from "./models.ts";

/** An immutable OKLCH color; hue is in degrees and normalized only during export. */
export class OklchColor {
  readonly lightness: number;
  readonly chroma: number;
  readonly hue: number;

  constructor(lightness: number, chroma: number, hue: number) {
    if (![lightness, chroma, hue].every((value) => typeof value === "number" && Number.isFinite(value))) {
      throw new InvalidOptionError("OKLCH components must be finite numbers.");
    }
    if (lightness < 0 || lightness > 1 || chroma < 0) {
      throw new InvalidOptionError("OKLCH lightness must be in [0, 1] and chroma must be nonnegative.");
    }
    this.lightness = lightness;
    this.chroma = chroma;
    this.hue = hue;
    Object.freeze(this);
  }

  harmonize(referenceHue: number, strength: number): OklchColor {
    if (typeof referenceHue !== "number" || !Number.isFinite(referenceHue) ||
        typeof strength !== "number" || !Number.isFinite(strength)) {
      throw new InvalidOptionError("Reference hue and strength must be finite numbers.");
    }
    if (strength < 0 || strength > 1) {
      throw new InvalidOptionError("Harmonization strength must be in [0, 1].");
    }
    if (this.chroma === 0 || strength === 0) return this;
    const hue = ((this.hue % 360) + 360) % 360;
    const target = ((referenceHue % 360) + 360) % 360;
    let delta = ((target - hue + 540) % 360) - 180;
    if (delta === -180) delta = 180;
    if (delta === 0) return this;
    return new OklchColor(this.lightness, this.chroma, ((hue + delta * strength) % 360 + 360) % 360);
  }

  toHex(): string {
    const angle = (((this.hue % 360) + 360) % 360) * Math.PI / 180;
    const cosine = Math.cos(angle);
    const sine = Math.sin(angle);
    const linear = (chroma: number): [number, number, number] => {
      const a = chroma * cosine;
      const b = chroma * sine;
      const l = (this.lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
      const m = (this.lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
      const s = (this.lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
      return [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
      ];
    };
    const inGamut = (rgb: readonly number[]): boolean =>
      rgb.every((channel) => channel >= -1e-7 && channel <= 1 + 1e-7);
    // All sRGB colors have OKLCH chroma below 4; the bound avoids overflow.
    const chroma = Math.min(this.chroma, 4);
    let rgb = linear(chroma);
    if (!inGamut(rgb)) {
      let low = 0;
      let high = chroma;
      for (let index = 0; index < 32; index++) {
        const mid = (low + high) / 2;
        if (inGamut(linear(mid))) low = mid;
        else high = mid;
      }
      rgb = linear(low);
    }
    return `#${rgb.map((value) => {
      const channel = Math.min(1, Math.max(0, value));
      const encoded = channel <= 0.0031308 ? 12.92 * channel : 1.055 * channel ** (1 / 2.4) - 0.055;
      return Math.floor(encoded * 255 + 0.5).toString(16).padStart(2, "0");
    }).join("")}`;
  }
}

/** Source OKLCH palette; converting it does not change its components. */
export class OklchPalette {
  readonly name: string;
  readonly text: OklchColor;
  readonly heading: OklchColor;
  readonly accent: OklchColor;
  readonly background: OklchColor;

  constructor(
    name: string,
    text: OklchColor,
    heading: OklchColor,
    accent: OklchColor,
    background: OklchColor = new OklchColor(1, 0, 0),
  ) {
    if (![text, heading, accent, background].every((color) => color instanceof OklchColor)) {
      throw new InvalidOptionError("Palette colors must be OklchColor values.");
    }
    this.name = name;
    this.text = text;
    this.heading = heading;
    this.accent = accent;
    this.background = background;
    Object.freeze(this);
  }

  withChanges(changes: Partial<Pick<OklchPalette, "name" | "text" | "heading" | "accent" | "background">>): OklchPalette {
    return new OklchPalette(
      changes.name === undefined ? this.name : changes.name,
      changes.text === undefined ? this.text : changes.text,
      changes.heading === undefined ? this.heading : changes.heading,
      changes.accent === undefined ? this.accent : changes.accent,
      changes.background === undefined ? this.background : changes.background,
    );
  }

  toColorScheme(): ColorScheme {
    return Object.freeze({
      name: this.name,
      text: this.text.toHex(),
      heading: this.heading.toHex(),
      accent: this.accent.toHex(),
      background: this.background.toHex(),
    });
  }

  harmonize(referenceHue: number, strength: number): OklchPalette {
    return new OklchPalette(
      this.name,
      this.text.harmonize(referenceHue, strength),
      this.heading.harmonize(referenceHue, strength),
      this.accent.harmonize(referenceHue, strength),
      this.background.harmonize(referenceHue, strength),
    );
  }
}
