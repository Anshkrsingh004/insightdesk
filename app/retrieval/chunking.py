"""Chunking: split documents into citable units.

Articles are markdown with `##` sections -> one chunk per section (so citations carry a
meaningful `section`). Tickets are short -> a single chunk. Each chunk keeps the
document's Source Register metadata so precedence can reason over it.
"""
from __future__ import annotations

import re

HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def split_markdown(md: str) -> list[tuple[str, str]]:
    """Return [(section_title, text), ...]. Text before the first ## is 'Overview'."""
    parts: list[tuple[str, str]] = []
    matches = list(HEADING.finditer(md))
    if not matches:
        return [("Body", md.strip())]
    # preamble (title line + intro) before first ##
    pre = md[: matches[0].start()].strip()
    if pre:
        # drop the leading '# Title' line from the preamble label
        parts.append(("Overview", pre))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        section = m.group(1).strip()
        text = md[start:end].strip()
        if text:
            parts.append((section, text))
    return parts
