"""HTML-Schnipsel aus Stellenanzeigen → lesbarer Text mit Listenpunkten.

Karriereseiten liefern die Beschreibung als HTML. Gespeichert wird Text,
damit Liste, Detailansicht und LLM-Aufruf dasselbe sehen wie bei der
Arbeitsagentur.
"""

import re
from html.parser import HTMLParser

_BLOCK = {
    "p", "div", "section", "article", "ul", "ol", "table", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
}
_UEBERSPRINGEN = {"script", "style", "noscript", "template"}


class _Sammler(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.teile: list[str] = []
        self._versteckt = 0

    def handle_starttag(self, tag, attrs):
        if tag in _UEBERSPRINGEN:
            self._versteckt += 1
        elif tag == "br":
            self.teile.append("\n")
        elif tag == "li":
            self.teile.append("\n- ")
        elif tag in _BLOCK:
            self.teile.append("\n\n")

    def handle_endtag(self, tag):
        if tag in _UEBERSPRINGEN:
            self._versteckt = max(0, self._versteckt - 1)
        elif tag in _BLOCK:
            self.teile.append("\n\n")

    def handle_data(self, data):
        if not self._versteckt:
            self.teile.append(data)


def zu_text(html: str | None) -> str:
    """Wandelt HTML in Text; Absätze bleiben erhalten, Leerraum wird gestrafft."""
    if not html:
        return ""
    sammler = _Sammler()
    sammler.feed(html)
    sammler.close()
    text = "".join(sammler.teile).replace("\xa0", " ")
    zeilen = [re.sub(r"[ \t\r\f\v]+", " ", zeile).strip() for zeile in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()
