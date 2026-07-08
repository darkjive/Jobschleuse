import html
import re
from html.parser import HTMLParser

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# HTML-Void-Elemente: können kein Kind-Content haben, daher kein data-slot möglich.
_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _SlotParser(HTMLParser):
    """Findet die (start, end)-Offsets im Roh-HTML für jedes data-slot-Element."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self._source = source
        self._line_starts = self._compute_line_starts(source)
        # Stack von (tag, name-oder-None, tiefe-gleichnamiger-tags-innerhalb-des-slots)
        self._stack: list[dict] = []
        self.ranges: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _compute_line_starts(source: str) -> list[int]:
        starts = [0]
        for i, ch in enumerate(source):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    def _offset(self, line: int, col: int) -> int:
        return self._line_starts[line - 1] + col

    def _current_offset(self) -> int:
        line, col = self.getpos()
        return self._offset(line, col)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        slot_name = self._slot_name(attrs)
        if slot_name is not None and tag in _VOID_ELEMENTS:
            raise ValueError(f"Slot auf leerem Element nicht unterstützt: {slot_name}")

        if slot_name is not None and self._stack:
            raise ValueError(f"Verschachtelte Slots nicht unterstützt: {tag}")

        # Falls wir gerade in einem Slot stecken und ein gleichnamiger Tag
        # öffnet, Verschachtelungstiefe hochzählen, damit handle_endtag
        # den richtigen End-Tag matcht.
        if self._stack and self._stack[-1]["tag"] == tag:
            self._stack[-1]["depth"] += 1

        if slot_name is not None:
            if slot_name in self.ranges:
                raise ValueError(f"Slot doppelt vergeben: {slot_name}")
            start = self._current_offset() + len(self.get_starttag_text())
            self._stack.append({
                "tag": tag,
                "slot": slot_name,
                "depth": 0,
                "start": start,
            })

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        slot_name = self._slot_name(attrs)
        if slot_name is not None:
            raise ValueError(f"Slot auf leerem Element nicht unterstützt: {slot_name}")

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        top = self._stack[-1]
        if top["tag"] != tag:
            return
        if top["depth"] > 0:
            top["depth"] -= 1
            return
        self._stack.pop()
        end = self._current_offset()
        self.ranges[top["slot"]] = (top["start"], end)

    @staticmethod
    def _slot_name(attrs: list[tuple[str, str | None]]) -> str | None:
        for attr_name, attr_value in attrs:
            if attr_name == "data-slot":
                return attr_value or ""
        return None


def _parse(source: str) -> dict[str, tuple[int, int]]:
    parser = _SlotParser(source)
    parser.feed(source)
    parser.close()
    if parser._stack:
        pending_slot = parser._stack[-1]
        raise ValueError(f"Slot nicht geschlossen: {pending_slot['slot']}")
    return parser.ranges


def _clean_text(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_slots(html_source: str) -> dict[str, str]:
    ranges = _parse(html_source)
    return {
        name: _clean_text(html_source[start:end])
        for name, (start, end) in ranges.items()
    }


def fill_slots(html_source: str, values: dict[str, str]) -> str:
    ranges = _parse(html_source)
    unknown = set(values) - set(ranges)
    if unknown:
        raise ValueError(f"Slots nicht in Vorlage: {sorted(unknown)}")

    result = html_source
    replacements = sorted(
        ((start, end, name) for name, (start, end) in ranges.items() if name in values),
        key=lambda item: item[0],
        reverse=True,
    )
    for start, end, name in replacements:
        escaped = html.escape(values[name], quote=False)
        result = result[:start] + escaped + result[end:]
    return result
