import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import llm
from bewerbungs_pipeline.models import JobItem

JOB = JobItem(
    title="Mechatroniker (m/w/d)",
    company="Beispiel AG",
    location="Frankfurt am Main",
    url="https://example.org/job/1",
    source="arbeitsagentur",
    description_md="Wir suchen einen Mechatroniker für Wartung und Instandhaltung.",
    scraped_at=datetime.now(UTC),
)
SLOTS = {"firma": "AC Motoren GmbH", "einstieg": "Mit großem Interesse …"}
PROFILE = {"name": "Alain Ritter", "email": "cosmwave@gmail.com"}


class FakeClient:
    """Gibt vorbereitete Antworten zurück und zählt Aufrufe.

    Bei einem dict wird dieselbe Antwort bei jedem Aufruf erneut geliefert
    (unbegrenzt). Bei einer Liste wird eine Antwort pro Aufruf der Reihe
    nach geliefert.
    """

    def __init__(self, responses):
        self.calls = 0
        self._dict_response = None
        self._responses = None
        if isinstance(responses, dict):
            self._dict_response = json.dumps(responses, ensure_ascii=False)
        else:
            self._responses = responses
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        if self._dict_response is not None:
            text = self._dict_response
        else:
            text = self._responses[self.calls]
        self.calls += 1
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def good_response() -> str:
    return json.dumps(
        {"firma": "Beispiel AG", "einstieg": "Ihre Anzeige bei der Beispiel AG hat mich überzeugt."}
    )


def test_parse_response_strips_code_fence():
    fenced = "```json\n{\"a\": \"b\"}\n```"
    assert llm.parse_response(fenced) == {"a": "b"}


def test_validate_ok():
    values = json.loads(good_response())
    assert llm.validate_values(values, SLOTS, "Beispiel AG") == []


def test_validate_catches_problems():
    assert llm.validate_values({"firma": "x"}, SLOTS, "Beispiel AG")  # Slot fehlt
    bad_empty = {"firma": "", "einstieg": "y"}
    assert llm.validate_values(bad_empty, SLOTS, "Beispiel AG")  # leerer Slot
    no_company = {"firma": "Anders GmbH", "einstieg": "Text ohne Firmenbezug."}
    assert llm.validate_values(no_company, SLOTS, "Beispiel AG")  # Firmenname fehlt


def test_generate_success_first_try():
    client = FakeClient([good_response()])
    values = llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert values["firma"] == "Beispiel AG"
    assert client.calls == 1


def test_generate_retries_once_then_succeeds():
    client = FakeClient(["kein json", good_response()])
    values = llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert values["einstieg"].startswith("Ihre Anzeige")
    assert client.calls == 2


def test_generate_fails_after_two_attempts():
    client = FakeClient(["kein json", "immer noch kein json"])
    with pytest.raises(llm.GenerationError):
        llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert client.calls == 2


def test_validate_accepts_company_without_legal_suffix():
    values = {"firma": "Bewerbung bei AC Motoren", "einstieg": "Text."}
    slots = {"firma": "alt", "einstieg": "alt"}
    assert llm.validate_values(values, slots, "AC Motoren GmbH & Co. KG") == []


def test_validate_still_fails_when_core_name_missing():
    values = {"firma": "Eine andere Firma", "einstieg": "Text."}
    slots = {"firma": "alt", "einstieg": "alt"}
    assert llm.validate_values(values, slots, "AC Motoren GmbH")


def test_build_single_slot_prompt_names_slot_and_others():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    prompt = llm.build_single_slot_prompt(
        job, "motivation", "Beispieltext", {"name": "Alain"}, {"firma": "Beispiel AG"}
    )
    assert "motivation" in prompt
    assert "Beispieltext" in prompt
    assert "Beispiel AG" in prompt


def test_generate_single_slot_returns_text():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    client = FakeClient({"motivation": "Frisch formulierter Text."})
    text = llm.generate_single_slot(
        client, "test-model", job, "motivation", "alt", {"name": "Alain"}, {}
    )
    assert text == "Frisch formulierter Text."


def test_generate_single_slot_rejects_empty_answer():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    client = FakeClient({"motivation": "   "})
    with pytest.raises(llm.GenerationError):
        llm.generate_single_slot(
            client, "test-model", job, "motivation", "alt", {"name": "Alain"}, {}
        )
    assert client.calls == 2


class AufzeichnenderClient:
    """Merkt sich die Aufrufparameter, damit der Test sie prüfen kann."""

    def __init__(self, payload: dict):
        self.aufrufe = []
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        antwort = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        def create(**kw):
            self.aufrufe.append(kw)
            return antwort

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _job() -> JobItem:
    return JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )


def test_generate_slot_texts_fordert_alle_slots_als_schema_an():
    """Ohne erzwungenes Schema liefern lokale Modelle kaputte Strings oder
    lassen Slots weg — beides gemessen an ornith:latest."""
    slots = {"firma": "Muster GmbH", "motivation": "Beispiel"}
    client = AufzeichnenderClient({"firma": "Beispiel AG", "motivation": "Text"})
    llm.generate_slot_texts(client, "test-model", _job(), slots, {"name": "Alain"})
    schema = client.aufrufe[0]["response_format"]["json_schema"]["schema"]
    assert sorted(schema["required"]) == ["firma", "motivation"]
    assert schema["additionalProperties"] is False


def test_generate_single_slot_fordert_nur_seinen_slot_an():
    client = AufzeichnenderClient({"motivation": "Neuer Text."})
    llm.generate_single_slot(
        client, "test-model", _job(), "motivation", "alt", {"name": "Alain"}, {}
    )
    schema = client.aufrufe[0]["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["motivation"]


def test_parse_response_findet_json_in_prosa():
    text = 'Hier ist das Ergebnis:\n{"firma": "Beispiel AG"}\nViel Erfolg!'
    assert llm.parse_response(text) == {"firma": "Beispiel AG"}


def test_generationerror_zeigt_die_rohantwort():
    """Ohne Auszug der Antwort lässt sich ein Fehlschlag nicht diagnostizieren."""
    slots = {"firma": "Muster GmbH"}
    client = AufzeichnenderClient({})
    client.chat.completions.create = lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"firma": "kaputt""}'))]
    )
    with pytest.raises(llm.GenerationError) as fehler:
        llm.generate_slot_texts(client, "test-model", _job(), slots, {})
    assert "kaputt" in str(fehler.value)


def test_validate_values_meldet_erfundene_adresse():
    """Kennt das Modell die Anschrift nicht, baut es die Struktur nach —
    „Straße Hausnr, PLZ Ort“ landete so schon in einer fertigen Bewerbung."""
    slots = {"adressat": "AC Motoren GmbH\nz. Hd. Nina Klussmann\nEinsteinstr. 17"}
    werte = {"adressat": "Beispiel AG, Straße Hausnr, PLZ Ort"}
    probleme = llm.validate_values(werte, slots, "Beispiel AG")
    assert any("Platzhalter" in p for p in probleme)


def test_validate_values_meldet_zusaetzliche_grussformel():
    """Die Vorlage setzt Gruss und Unterschrift selbst — steht beides auch im
    Textblock, erscheint es doppelt."""
    slots = {"anschreiben_text": "Liebe Nina,\n\nich bewerbe mich bei Ihnen."}
    werte = {
        "anschreiben_text": "Sehr geehrte Damen und Herren,\n\nich bewerbe mich.\n\n"
        "Mit freundlichen Grüßen,\nAlain Ritter"
    }
    probleme = llm.validate_values(werte, slots, "Beispiel AG")
    assert any("Grußformel" in p for p in probleme)


def test_validate_values_erlaubt_grussformel_wenn_vorlage_eine_hat():
    slots = {"gruss": "Mit besten Grüßen\nAlain Ritter"}
    werte = {"gruss": "Mit freundlichen Grüßen\nAlain Ritter"}
    probleme = llm.validate_values(werte, slots, "Alain")
    assert not any("Grußformel" in p for p in probleme)


def test_validate_values_laesst_normale_anrede_durch():
    slots = {"einstieg": "Mit großem Interesse habe ich Ihre Anzeige gelesen."}
    werte = {"einstieg": "Sehr geehrte Damen und Herren, Ihre Anzeige der Beispiel AG …"}
    assert llm.validate_values(werte, slots, "Beispiel AG") == []


def test_prompt_verbietet_erfundene_angaben_ueber_den_bewerber():
    prompt = llm.build_prompt(JOB, {"x": "y"}, {"name": "Alain"})
    assert "Bewerberprofil" in prompt
    assert "erfinde" in prompt.lower()
    # Der bisherige Prompt verbot nur Erfundenes ueber die Firma.
    assert "Abschlüsse" in prompt or "Qualifikationen" in prompt


def test_generate_single_slot_weist_platzhalter_zurueck():
    """Auch „Neu erzeugen“ darf keine erfundene Anschrift liefern."""
    client = AufzeichnenderClient({"adressat": "Beispiel AG, Straße Hausnr, PLZ Ort"})
    with pytest.raises(llm.GenerationError, match="Platzhalter"):
        llm.generate_single_slot(
            client, "test-model", _job(), "adressat",
            "AC Motoren GmbH\nEinsteinstr. 17", {"name": "Alain"}, {},
        )


def test_generate_single_slot_weist_zusaetzliche_grussformel_zurueck():
    client = AufzeichnenderClient(
        {"text": "Ich bewerbe mich.\n\nMit freundlichen Grüßen\nAlain"}
    )
    with pytest.raises(llm.GenerationError, match="Grußformel"):
        llm.generate_single_slot(
            client, "test-model", _job(), "text", "Ich bewerbe mich gern.",
            {"name": "Alain"}, {},
        )
