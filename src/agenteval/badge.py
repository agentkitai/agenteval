"""Badge SVG generation for AgentEval pass rates."""

from __future__ import annotations


def generate_badge(pass_rate: float, output_path: str) -> None:
    """Generate a shields.io-style flat SVG badge.

    Colors: green (≥90%), yellow (≥70%), red (<70%).
    """
    pass_rate = max(0.0, min(1.0, pass_rate))
    pct = f"{pass_rate:.0%}"
    if pass_rate >= 0.9:
        color = "#4c1"
    elif pass_rate >= 0.7:
        color = "#dfb317"
    else:
        color = "#e05d44"

    label = "agenteval"
    label_width = 70
    value_width = 50
    total_width = label_width + value_width

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a"><rect width="{total_width}" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_width / 2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_width / 2}" y="14">{label}</text>
    <text x="{label_width + value_width / 2}" y="15" fill="#010101" fill-opacity=".3">{pct}</text>
    <text x="{label_width + value_width / 2}" y="14">{pct}</text>
  </g>
</svg>'''

    with open(output_path, "w") as f:
        f.write(svg)
