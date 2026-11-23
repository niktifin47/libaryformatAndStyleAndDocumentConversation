# API Format Fix

The `LFSDC` Python distribution extracts and restyles documents on Linux, macOS,
and Windows. Its import name is `api_format_fix` and its CLI is `api-format-fix`.
See the [repository documentation](https://github.com/niktifin47/document-format-toolkit)
for installation, usage, supported formats, and security considerations.

For palette authoring, import `OklchColor` and `OklchPalette`; pass a palette as
`color_scheme` to the formatting APIs. `dataclasses.replace()` returns a
modified copy, while `palette.to_color_scheme()` exports a separate sRGB
snapshot. `palette.harmonize(reference_hue, strength)` returns a new palette.
The repository documentation describes gamut mapping and the intentional
DOCX/PDF background and strong-text behavior changes.
