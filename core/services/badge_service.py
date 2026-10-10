"""Dynamic SVG Badge generator for WARDEN audit scorecards and quality gates."""

from typing import ClassVar


class BadgeGeneratorService:
    """Generates shields.io-compatible vector SVG badges for README score cards."""

    COLOR_MAP: ClassVar[dict[str, str]] = {
        "A+": "#2ea44f",  # emerald bright green
        "A": "#3fb950",   # green
        "B": "#238636",   # dark green
        "C": "#d29922",   # yellow/amber
        "D": "#db6d28",   # orange
        "F": "#d73a49",   # crimson red
    }

    @classmethod
    def get_color_for_score(cls, score: float, grade: str | None = None) -> str:
        """Determines badge color based on score or grade."""
        if grade and grade.upper() in cls.COLOR_MAP:
            return cls.COLOR_MAP[grade.upper()]
        if score >= 95:
            return "#2ea44f"
        if score >= 85:
            return "#3fb950"
        if score >= 75:
            return "#238636"
        if score >= 65:
            return "#d29922"
        if score >= 50:
            return "#db6d28"
        return "#d73a49"

    @classmethod
    def generate_svg(
        cls,
        label: str = "WARDEN",
        score: float | None = None,
        grade: str | None = None,
        message: str | None = None,
        color: str | None = None,
    ) -> str:
        """Renders an SVG string formatted identically to modern shields.io badges."""
        # Determine value text
        if message:
            value_text = message
        elif score is not None and grade:
            value_text = f"{int(score)}/100 · {grade}"
        elif score is not None:
            value_text = f"{int(score)}/100"
        elif grade:
            value_text = grade
        else:
            value_text = "Verified"

        # Determine color
        if not color:
            color = cls.get_color_for_score(float(score) if score is not None else 85.0, grade=grade)

        # Approximate character widths for high-precision badge layout
        label_width = max(len(label) * 7 + 14, 50)
        value_width = max(len(value_text) * 7 + 14, 50)
        total_width = label_width + value_width

        label_x = label_width / 2
        value_x = label_width + (value_width / 2)

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {value_text}">
  <title>{label}: {value_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#24292e"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{int(label_x * 10)}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{int((label_width - 12) * 10)}">{label}</text>
    <text x="{int(label_x * 10)}" y="140" transform="scale(.1)" fill="#fff" textLength="{int((label_width - 12) * 10)}">{label}</text>
    <text aria-hidden="true" x="{int(value_x * 10)}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{int((value_width - 12) * 10)}">{value_text}</text>
    <text x="{int(value_x * 10)}" y="140" transform="scale(.1)" fill="#fff" textLength="{int((value_width - 12) * 10)}">{value_text}</text>
  </g>
</svg>"""
