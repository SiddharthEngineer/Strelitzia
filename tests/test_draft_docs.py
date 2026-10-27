"""The draft Docs format (docs-drafts-1-format): render, parse back, Docs-export quirks and errors."""

import copy

import pytest

from strelitzia.scoring import draft_docs as dd
from strelitzia.scoring import workbench as wb
from workbench_helpers import good_result, library


def _resume_text(result=None, version="1a2b3c4d", instructions="5e6f7a8b"):
    return dd.resume_draft_text(result, library(), version, instructions)


# ── Resume ──

def test_resume_round_trips_the_valid_result():
    data = good_result()
    resume, versions, notes = dd.parse_resume_draft(_resume_text(data))
    assert resume == data["resume"]
    assert versions == {"rules": "1a2b3c4d", "instructions": "5e6f7a8b"} and notes == data["notes_for_user"]


def test_empty_version_lines_read_as_missing():
    _, versions, _ = dd.parse_resume_draft(_resume_text(good_result(), "", ""))
    assert versions == {"rules": None, "instructions": None}


def test_resume_text_reads_like_the_format():
    text = _resume_text(good_result(dropped_roles=["data-analyst-intern-globex"], roles=good_result()["resume"]["roles"][:1]))
    assert text.startswith("Rules version: 1a2b3c4d\nInstructions version: 5e6f7a8b\nSummary: Data engineer building Airflow and Spark pipelines\n")
    assert "## data-engineer-acme\n- Migrated the nightly orders pipeline" in text
    assert "45 minutes [orders-pipeline]\n" in text
    assert "## Dropped roles\n- data-analyst-intern-globex\n" in text
    assert "## Skills\n- Languages: Python, SQL\n- Tools: Airflow, Spark, dbt, Superset\n" in text
    assert text.rstrip().endswith("## Notes for me\nKubernetes and Terraform are not in your library, so I left them out.")


def test_docs_export_quirks_parse_the_same():
    text = _resume_text(good_result())
    exported = (text.replace("\n- ", "\n* ").replace("[", "\\[").replace("]", "\\]")
                .replace("orders-pipeline", "orders\\-pipeline").replace("## Skills", "### **Skills**"))
    exported = exported.replace("\n* ", "\n\n* ")  # blank lines between list items
    assert dd.parse_resume_draft(exported) == dd.parse_resume_draft(text)


def test_skeleton_has_every_role_and_placeholders_are_errors():
    text = _resume_text(None)
    for role in library().roles:
        assert f"## {role.key}\n- {dd.PLACEHOLDER_BULLET}" in text
    with pytest.raises(dd.DraftFormatError) as e:
        dd.parse_resume_draft(text)
    assert all("placeholder" in m for m in e.value.errors) and len(e.value.errors) == len(library().roles)
    assert e.value.errors[0].startswith("Line 6:")


def test_missing_summary_is_empty():
    text = _resume_text(good_result()).replace("Summary: Data engineer building Airflow and Spark pipelines\n", "")
    assert dd.parse_resume_draft(text)[0]["headline"] == ""


def test_an_old_headline_line_parses_as_the_summary():
    text = _resume_text(good_result())
    old = text.replace("Summary: ", "Headline: ")
    assert old != text and dd.parse_resume_draft(old) == dd.parse_resume_draft(text)
    assert dd.parse_resume_draft(old)[0]["headline"] == "Data engineer building Airflow and Spark pipelines"


def test_unknown_section_is_kept_as_a_role_key_for_the_schema_check():
    text = _resume_text(good_result()).replace("## data-engineer-acme", "## data-engineer-acmee")
    resume, _, _ = dd.parse_resume_draft(text)
    assert resume["roles"][0]["role_key"] == "data-engineer-acmee"
    errors = wb.schema_errors({"strelitzia": 1, "resume": resume, "cover_letter": None},
                              wb.result_schema(library()))
    assert any("data-engineer-acmee" in e and "data-engineer-acme" in e for e in errors)


@pytest.mark.parametrize("change, line, words", [
    (lambda t: t.replace(" [orders-pipeline]", ""), 6, "no [slug] tags"),
    (lambda t: t.replace(" [orders-pipeline]", " []"), 6, "no [slug] tags"),
    (lambda t: t.replace("- Languages: Python, SQL", "- Python and SQL"), 15, "Category: skill"),
    (lambda t: t.replace("Summary:", "Some intro\nSummary:"), 3, "above the first ## heading"),
    (lambda t: t.replace("- Migrated", "Migrated"), 6, "isn't a \"- \" list item"),
    (lambda t: t.replace("## data-analyst-intern-globex\n- Trained", "## data-analyst-intern-globex\n\n## Extra\n- Trained"),
     9, "has no bullets"),
])
def test_each_error_names_its_line(change, line, words):
    with pytest.raises(dd.DraftFormatError) as e:
        dd.parse_resume_draft(change(_resume_text(good_result())))
    assert len(e.value.errors) == 1, e.value.errors
    assert e.value.errors[0].startswith(f"Line {line}:") and words in e.value.errors[0]


def test_a_role_twice_is_an_error():
    text = _resume_text(good_result())
    text = text.replace("## data-analyst-intern-globex", "## data-engineer-acme")
    with pytest.raises(dd.DraftFormatError) as e:
        dd.parse_resume_draft(text)
    assert "appears twice" in e.value.errors[0]


# ── Cover letter ──

def test_cover_round_trips():
    cover = good_result()["cover_letter"]
    text = dd.cover_draft_text(cover, "1a2b3c4d")
    assert text.startswith("Rules version: 1a2b3c4d\n\n") and text.endswith("Evidence: orders-pipeline, quality-dashboard\n")
    assert dd.parse_cover_draft(text) == cover


def test_cover_paragraph_lines_are_joined():
    text = "First line\nsame paragraph.\n\nSecond.\n\nThird.\n\nEvidence: orders-pipeline"
    assert dd.parse_cover_draft(text) == {"paragraphs": ["First line same paragraph.", "Second.", "Third."],
                                          "evidence_slugs": ["orders-pipeline"]}


@pytest.mark.parametrize("text", ["", "  \n\n", "Rules version: 1a2b3c4d\n\n", dd.cover_draft_text(None, "v")])
def test_an_empty_letter_is_none(text):
    assert dd.parse_cover_draft(text) is None


def test_a_letter_without_evidence_is_an_error():
    with pytest.raises(dd.DraftFormatError) as e:
        dd.parse_cover_draft("One.\n\nTwo.\n\nThree.")
    assert "Evidence:" in e.value.errors[0]


# ── Both ──

def test_drafts_to_result_gives_the_paste_shape():
    data = good_result()
    data["rules_version"] = wb.RULES_VERSION
    data["instructions_version"] = wb.INSTRUCTIONS_VERSION
    result = dd.drafts_to_result(_resume_text(data, wb.RULES_VERSION, wb.INSTRUCTIONS_VERSION),
                                 dd.cover_draft_text(data["cover_letter"], "x"))
    assert result == data
    assert wb.schema_errors(result, wb.RESULT_SCHEMA) == []


def test_drafts_to_result_takes_the_version_from_the_cover_when_the_resume_has_none():
    data = good_result()
    resume = _resume_text(data).replace("Rules version: 1a2b3c4d\n", "")
    assert dd.drafts_to_result(resume, dd.cover_draft_text(data["cover_letter"], "c0ffee00"))["rules_version"] == "c0ffee00"
    no_version = dd.drafts_to_result(resume, "")
    assert "rules_version" not in no_version and no_version["cover_letter"] is None


def test_cover_version_lines_are_stripped():
    cover = good_result()["cover_letter"]
    text = "Rules version: c0ffee00\nInstructions version: 5e6f7a8b\n\n" + dd.cover_draft_text(cover, "")
    assert dd.parse_cover_draft(text) == cover and not dd.cover_draft_text(cover, "").startswith("Rules")


def test_drafts_to_result_reports_both_docs():
    data = copy.deepcopy(good_result())
    resume = _resume_text(data).replace(" [orders-pipeline]", "")
    with pytest.raises(dd.DraftFormatError) as e:
        dd.drafts_to_result(resume, "One.\n\nTwo.")
    assert e.value.errors[0].startswith("Resume draft, line 6:")
    assert e.value.errors[1].startswith("Cover letter draft: The last line")
