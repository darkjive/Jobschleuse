from bs4 import BeautifulSoup


def extract_slots(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    slots: dict[str, str] = {}
    for element in soup.select("[data-slot]"):
        name = element["data-slot"]
        if name in slots:
            raise ValueError(f"Slot doppelt vergeben: {name}")
        slots[name] = element.get_text(" ", strip=True)
    return slots


def fill_slots(html: str, values: dict[str, str]) -> str:
    soup = BeautifulSoup(html, "lxml")
    filled: set[str] = set()
    for element in soup.select("[data-slot]"):
        name = element["data-slot"]
        if name in values:
            element.clear()
            element.append(values[name])
            filled.add(name)
    unknown = set(values) - filled
    if unknown:
        raise ValueError(f"Slots nicht in Vorlage: {sorted(unknown)}")
    return str(soup)
