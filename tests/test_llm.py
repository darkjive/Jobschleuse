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
