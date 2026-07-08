import json

from openai import OpenAI

from .models import JobItem


class GenerationError(Exception):
    pass


PROMPT_TEMPLATE = """Du personalisierst eine deutsche Bewerbungsvorlage für eine konkrete Stelle.

## Stellenanzeige
Titel: {title}
Firma: {company}
Ort: {location}

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
- Erfinde keine Fakten über die Firma, die nirgends stehen.
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
        description=job.description_md or "(keine Beschreibung vorhanden)",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        slots=json.dumps(slots, ensure_ascii=False, indent=2),
    )


def parse_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


def validate_values(values: dict, slots: dict[str, str], company: str) -> list[str]:
    problems: list[str] = []
    if set(values) != set(slots):
        problems.append(
            f"Slot-Namen stimmen nicht überein: erwartet {sorted(slots)}, bekommen {sorted(values)}"
        )
    empty = [k for k, v in values.items() if not isinstance(v, str) or not v.strip()]
    if empty:
        problems.append(f"Leere Slots: {empty}")
    joined = " ".join(str(v) for v in values.values()).lower()
    if company.lower() not in joined:
        problems.append(f"Firmenname '{company}' kommt in keinem Slot vor")
    return problems


def generate_slot_texts(
    client, model: str, job: JobItem, slots: dict[str, str], profile: dict
) -> dict[str, str]:
    prompt = build_prompt(job, slots, profile)
    last_problems: list[str] = []
    for _attempt in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        text = response.choices[0].message.content or ""
        try:
            values = parse_response(text)
        except (json.JSONDecodeError, IndexError):
            last_problems = ["Antwort war kein gültiges JSON"]
        else:
            last_problems = validate_values(values, slots, job.company)
            if not last_problems:
                return values
        prompt = build_prompt(job, slots, profile) + (
            f"\n\nDein letzter Versuch hatte diese Fehler: {last_problems}. Korrigiere sie."
        )
    raise GenerationError(f"LLM-Ausgabe nach 2 Versuchen ungültig: {last_problems}")
