import json
import re
from datetime import date

from openai import OpenAI

from .models import JobItem

_LEGAL_SUFFIXES = {
    "gmbh",
    "ag",
    "kg",
    "se",
    "ug",
    "ohg",
    "gbr",
    "mbh",
    "co",
    "co.",
    "&",
    "e.v.",
    "e.k.",
}


def _company_core(company: str) -> str:
    """Extract core name by stripping trailing legal-form suffixes."""
    words = company.split()
    while len(words) > 1 and words[-1].lower().strip(".,") in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


class GenerationError(Exception):
    pass


PROMPT_TEMPLATE = """Du personalisierst eine deutsche Bewerbungsvorlage für eine konkrete Stelle.

## Stellenanzeige
Titel: {title}
Firma: {company}
Ort: {location}
Ansprechpartner: {contact_name}
Heutiges Datum: {today}

{description}

## Bewerberprofil
{profile}

## Slots der Vorlage (Name → bisheriger Beispieltext)
{slots}

## Auftrag
Schreibe für jeden Slot einen neuen Text im Stil und in ungefähr der Länge des Beispieltexts,
zugeschnitten auf diese Stelle und diese Firma.

Regeln:
- Formuliere nur aus Stellenanzeige, Bewerberprofil und den Beispieltexten.
- Erfinde keine Fakten über die Firma, die nirgends stehen (z.B. keine Straße/PLZ, wenn nicht bekannt).
- Erfinde ebenso wenig Angaben über den Bewerber. Abschlüsse, Titel, Zertifikate,
  Arbeitgeber, Jahreszahlen und Qualifikationen ausschließlich aus dem
  Bewerberprofil. Steht dort kein Studium, erwähne keines.
- Fehlt dir eine Angabe, lass sie weg. Schreibe niemals Platzhalter wie
  "Straße Hausnr", "PLZ Ort" oder "Musterstadt".
- Nenne nur Technologien, Werkzeuge und Kenntnisse, die im Bewerberprofil
  stehen. Fordert die Anzeige etwas, das dort fehlt, schreibe es dem Bewerber
  nicht zu — verlangt sie etwa PHP und das Profil nennt es nicht, dann kommt
  PHP im Text nicht vor.
- Die Beispieltexte geben nur Stil, Aufbau und Länge vor. Übernimm daraus keine
  konkreten Angaben und ergänze nichts, was dort nicht vorkommt — endet ein
  Beispieltext ohne Grußformel und Unterschrift, gehört auch in den neuen Text
  keine; die Vorlage setzt beides selbst.
- Ist kein Ansprechpartner bekannt, verwende die Anrede "Sehr geehrte Damen und Herren".
- Verwende für Datums-Slots exakt das oben genannte heutige Datum.
- Der Firmenname "{company}" muss in mindestens einem Slot-Text vorkommen.
- Antworte NUR mit einem JSON-Objekt: {{"slotname": "neuer Text", ...}}
  mit exakt denselben Slot-Namen wie oben, ohne weitere Erklärungen.
"""


def make_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


def build_prompt(job: JobItem, slots: dict[str, str], profile: dict) -> str:
    return PROMPT_TEMPLATE.format(
        title=job.title,
        company=job.company,
        location=job.location,
        contact_name=job.contact_name or "nicht bekannt",
        today=date.today().strftime("%d.%m.%Y"),
        description=job.description_md or "(keine Beschreibung vorhanden)",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        slots=json.dumps(slots, ensure_ascii=False, indent=2),
    )


def parse_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Manche Modelle schreiben Fließtext um das Objekt herum. Der äußerste
        # Block von { bis } ist dann der einzige Kandidat.
        anfang, ende = cleaned.find("{"), cleaned.rfind("}")
        if anfang == -1 or ende <= anfang:
            raise
        return json.loads(cleaned[anfang : ende + 1])


# Kennt das Modell eine Angabe nicht, baut es gern die Form nach statt sie
# wegzulassen. Diese Wendungen sind in einer fertigen Bewerbung immer falsch.
PLATZHALTER = (
    "straße hausnr",
    "strasse hausnr",
    "plz ort",
    "musterstraße",
    "musterstadt",
    "max mustermann",
    "vorname nachname",
    "firmenname",
    "lorem ipsum",
)

GRUSSFORMELN = (
    "mit freundlichen grüßen",
    "mit freundlichem gruß",
    "mit besten grüßen",
    "beste grüße",
    "herzliche grüße",
    "viele grüße",
)


# Zusaetzlich zu den Wendungen oben: angefangene Angaben wie "+49 ..." oder
# "<hier eintragen>", wie sie in Beispieldateien stehen.
PLATZHALTER_MUSTER = re.compile(
    "|".join([*(re.escape(p) for p in PLATZHALTER), r"\.\.\.", r"<[^>]+>", r"\bxxx\b"]),
    re.IGNORECASE,
)


def _platzhalter_in(text: str) -> list[str]:
    unten = text.lower()
    return [p for p in PLATZHALTER if p in unten]


def _grussformel_in(text: str) -> str | None:
    unten = text.lower()
    return next((g for g in GRUSSFORMELN if g in unten), None)


def ohne_ueberzaehlige_grussformel(wert: str, beispiel: str) -> str:
    """Kappt eine Grußformel am Textende, wenn die Vorlage selbst eine setzt.

    Reparieren statt abbrechen: das Modell haengt die Formel hartnaeckig an,
    und zwei gescheiterte Versuche hiessen gar keine Bewerbung — dabei ist der
    Abschluss eindeutig abtrennbar.
    """
    if _grussformel_in(beispiel):
        return wert
    zeilen = wert.split("\n")
    for i, zeile in enumerate(zeilen):
        if not _grussformel_in(zeile):
            continue
        # Nur kappen, wenn ab hier nichts Inhaltliches mehr kommt: hinter der
        # Formel steht hoechstens noch der Name.
        rest = [z for z in zeilen[i + 1 :] if z.strip()]
        if len(rest) <= 1 and len(zeile.split()) <= 6:
            return "\n".join(zeilen[:i]).rstrip()
    return wert


def pruefe_text(name: str, wert: str, beispiel: str) -> list[str]:
    """Prüft einen einzelnen Slot-Text gegen seinen Beispieltext.

    Beide Fälle stammen aus einer real erzeugten Bewerbung: eine erfundene
    Anschrift und eine Grußformel, die die Vorlage selbst schon setzt.
    """
    probleme = []
    gefunden = _platzhalter_in(wert)
    if gefunden:
        probleme.append(
            f"Slot '{name}' enthält Platzhalter statt echter Angaben: {gefunden}. "
            "Lass die Angabe lieber ganz weg."
        )
    gruss = _grussformel_in(wert)
    if gruss and not _grussformel_in(beispiel):
        probleme.append(
            f"Slot '{name}' endet mit einer Grußformel ('{gruss}'), "
            "der Beispieltext hat keine — die Vorlage setzt sie selbst."
        )
    return probleme


def validate_values(values: dict, slots: dict[str, str], company: str) -> list[str]:
    problems: list[str] = []
    if set(values) != set(slots):
        problems.append(
            f"Slot-Namen stimmen nicht überein: erwartet {sorted(slots)}, bekommen {sorted(values)}"
        )
    empty = [k for k, v in values.items() if not isinstance(v, str) or not v.strip()]
    if empty:
        problems.append(f"Leere Slots: {empty}")
    for name, wert in values.items():
        if isinstance(wert, str):
            problems.extend(pruefe_text(name, wert, slots.get(name, "")))
    joined = " ".join(str(v) for v in values.values()).lower()
    core = _company_core(company).lower()
    if core not in joined:
        problems.append(
            f"Firmenname '{_company_core(company)}' kommt in keinem Slot vor"
        )
    return problems


def slot_schema(namen) -> dict:
    """Antwortschema für die gewünschten Slots.

    Nur „irgendein JSON“ zu verlangen genügt nicht: die Grammatik lässt das
    Modell das Objekt dann früh schließen, und es fehlen Slots. Das Schema
    schreibt jeden Namen als Pflichtfeld vor.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "slots",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {name: {"type": "string"} for name in namen},
                "required": list(namen),
                "additionalProperties": False,
            },
        },
    }


def _auszug(text: str, zeichen: int = 200) -> str:
    """Kürzt eine Modellantwort auf ein Maß, das in eine Meldung passt."""
    knapp = " ".join(text.split())
    return knapp if len(knapp) <= zeichen else knapp[:zeichen] + " …"


def generate_slot_texts(
    client, model: str, job: JobItem, slots: dict[str, str], profile: dict
) -> dict[str, str]:
    prompt = build_prompt(job, slots, profile)
    last_problems: list[str] = []
    letzte_antwort = ""
    for _attempt in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            # Ohne erzwungenes Schema schließen lokale Modelle deutsche
            # Anführungszeichen gern mit einem ASCII-" und brechen damit den
            # umgebenden JSON-String auf.
            response_format=slot_schema(slots),
        )
        text = response.choices[0].message.content or ""
        letzte_antwort = text
        try:
            values = parse_response(text)
        except (json.JSONDecodeError, IndexError):
            last_problems = ["Antwort war kein gültiges JSON"]
        else:
            values = {
                name: ohne_ueberzaehlige_grussformel(wert, slots.get(name, ""))
                if isinstance(wert, str)
                else wert
                for name, wert in values.items()
            }
            last_problems = validate_values(values, slots, job.company)
            if not last_problems:
                return values
        prompt = build_prompt(job, slots, profile) + (
            f"\n\nDein letzter Versuch hatte diese Fehler: {last_problems}. Korrigiere sie."
        )
    raise GenerationError(
        f"LLM-Ausgabe nach 2 Versuchen ungültig: {last_problems}. "
        f"Antwort war: {_auszug(letzte_antwort)}"
    )


SINGLE_SLOT_PROMPT = """Du überarbeitest EINEN Textblock einer deutschen Bewerbung.

## Stellenanzeige
Titel: {title}
Firma: {company}
Ort: {location}
Ansprechpartner: {contact_name}
Heutiges Datum: {today}

{description}

## Bewerberprofil
{profile}

## Die übrigen Textblöcke der Bewerbung (nur als Kontext, nicht ändern)
{andere}

## Zu überarbeitender Block
Name: {slot}
Bisheriger Text: {beispiel}

## Auftrag
Schreibe diesen einen Block neu — im selben Stil und in ungefähr derselben Länge,
zugeschnitten auf diese Stelle und diese Firma.

Regeln:
- Formuliere nur aus Stellenanzeige, Bewerberprofil und den vorhandenen Texten.
- Erfinde keine Fakten über die Firma, die nirgends stehen.
- Erfinde ebenso wenig Angaben über den Bewerber: Abschlüsse, Titel, Zertifikate
  und Arbeitgeber ausschließlich aus dem Bewerberprofil.
- Nenne nur Technologien und Kenntnisse, die im Bewerberprofil stehen, auch wenn
  die Anzeige andere verlangt.
- Fehlt dir eine Angabe, lass sie weg — keine Platzhalter wie "Straße Hausnr".
- Ergänze nichts, was der bisherige Text nicht hatte; endet er ohne Grußformel
  und Unterschrift, gilt das auch für den neuen Text.
- Wiederhole nicht wörtlich, was in den übrigen Blöcken schon steht.
- Antworte NUR mit einem JSON-Objekt: {{"{slot}": "neuer Text"}}
  ohne weitere Erklärungen.
"""


def build_single_slot_prompt(
    job: JobItem, slot: str, beispiel: str, profile: dict, andere: dict[str, str]
) -> str:
    return SINGLE_SLOT_PROMPT.format(
        title=job.title,
        company=job.company,
        location=job.location,
        contact_name=job.contact_name or "nicht bekannt",
        today=date.today().strftime("%d.%m.%Y"),
        description=job.description_md or "(keine Beschreibung vorhanden)",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        andere=json.dumps(andere, ensure_ascii=False, indent=2),
        slot=slot,
        beispiel=beispiel,
    )


def generate_single_slot(
    client,
    model: str,
    job: JobItem,
    slot: str,
    beispiel: str,
    profile: dict,
    andere: dict[str, str],
) -> str:
    """Erzeugt genau einen Slot-Text.

    Bewusst schwächere Validierung als validate_values: ein einzelner Block
    muss den Firmennamen nicht enthalten (z. B. ein Datums- oder Anrede-Block).
    """
    prompt = build_single_slot_prompt(job, slot, beispiel, profile, andere)
    problem = ""
    letzte_antwort = ""
    for _attempt in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format=slot_schema([slot]),
        )
        text = response.choices[0].message.content or ""
        letzte_antwort = text
        try:
            values = parse_response(text)
        except (json.JSONDecodeError, IndexError):
            problem = "Antwort war kein gültiges JSON"
        else:
            value = values.get(slot)
            if isinstance(value, str) and value.strip():
                value = ohne_ueberzaehlige_grussformel(value, beispiel)
                maengel = pruefe_text(slot, value, beispiel)
                if not maengel:
                    return value
                problem = "; ".join(maengel)
            else:
                problem = f"Slot '{slot}' fehlte oder war leer"
        prompt = build_single_slot_prompt(job, slot, beispiel, profile, andere) + (
            f"\n\nDein letzter Versuch hatte diesen Fehler: {problem}. Korrigiere ihn."
        )
    raise GenerationError(
        f"LLM-Ausgabe nach 2 Versuchen ungültig: {problem}. "
        f"Antwort war: {_auszug(letzte_antwort)}"
    )
