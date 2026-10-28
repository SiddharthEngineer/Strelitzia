"""validate_bullet_shape: warnings for bullets about a tool or a small task (agents/research/resume-bullets.md)."""

from strelitzia.scoring.resume_model import Bullet, RoleEntry, TailoredResume
from strelitzia.scoring.validator import validate_bullet_shape

SKILLS = {"Languages": "Python, SQL", "Data": "MySQL, Pandas, PyArrow, Parquet, Airflow (sensors), Spark"}
BEFORE_1 = "Wrote the export in Python: reads MySQL in chunks with Pandas, writes each chunk to Parquet with PyArrow."
AFTER_1 = ("Built the nightly MySQL-to-Parquet export that feeds the analytics lake, so analysts no longer query "
           "production; moves ~40M rows per run in Python.")
AFTER_2 = ("Owned ingestion orchestration for 12 vendor feeds in Airflow, adding retries and late-data alerts that "
           "cut missed morning loads from weekly to rare.")


def _resume(*bullets: tuple[str, list[str]]) -> TailoredResume:
    role = RoleEntry("data-engineer-acme", "Data Engineer", "Acme", "2024", None,
                     [Bullet(text, ids) for text, ids in bullets])
    return TailoredResume(roles=[role], skills={})


def test_the_researchs_before_warns_and_after_does_not():
    warnings = validate_bullet_shape(_resume((BEFORE_1, ["export"])), SKILLS)
    assert any("bullet 1 names 5 tools" in w for w in warnings), warnings
    assert validate_bullet_shape(_resume((AFTER_1, ["export"]), (AFTER_2, ["ingest"])), SKILLS) == []


def test_a_bullet_that_is_mostly_tools_warns():
    warnings = validate_bullet_shape(_resume(("Used Pandas and Spark in Airflow for the nightly jobs", ["x"])),
                                     SKILLS)
    assert warnings == ["data-engineer-acme bullet 1 is mostly tool names; say what the work owned or changed"]


def test_task_splitting_across_bullets_of_one_project_warns():
    resume = _resume((AFTER_1, ["export"]), (AFTER_2.replace("Owned", "Ran"), ["export"]), (AFTER_2, ["export", "x"]))
    warnings = validate_bullet_shape(resume, SKILLS)
    assert warnings == ["data-engineer-acme has 2 bullets citing only [export]; fold them into one responsibility "
                        "and feature other projects"]


def test_no_base_skills_only_checks_the_rest():
    assert validate_bullet_shape(_resume((BEFORE_1, ["export"])), {}) == []


def test_short_bullets_without_tools_are_fine():
    assert validate_bullet_shape(_resume(("Led a team of 4 engineers on payments", ["x"])), SKILLS) == []


def test_tool_matching_respects_case_symbols_overlap_and_acronyms():
    skills = {"Languages": "Go, R, C, Spark SQL, Spark, SQL", "ML": "Machine Learning (ML), NLP"}
    plain = ("Ran the go-live of the NLP and ML search in Spark for the R&D teams' C++ service, so every region "
             "switched over in one weekend without downtime")  # 3 tools; go, R, C and C++ aren't tools here
    assert validate_bullet_shape(_resume((plain, ["x"])), skills) == []
    overlap = ("Rebuilt the revenue reporting layer in Spark SQL, giving finance one source of truth across 12 "
               "regional teams every morning")
    assert validate_bullet_shape(_resume((overlap, ["x"])), skills) == []
    many = ("Owned the support-ticket triage model for 40 agents using machine learning and NLP in Go and Spark SQL, "
            "cutting first response time")
    assert any("names 4 tools" in w and "Machine Learning (ML)" in w
               for w in validate_bullet_shape(_resume((many, ["x"])), skills))


# ── validate_letter (resume-quality-5-cover-letter Task 2; agents/research/cover-letter.md) ──

def _letter_check(paragraphs, **kw):
    from strelitzia.scoring.validator import validate_letter
    from workbench_helpers import DESCRIPTION, library

    kw.setdefault("company", "Initech")
    kw.setdefault("tools", ["Python", "SQL", "Airflow", "Spark", "dbt", "Superset"])
    return validate_letter(paragraphs, ["orders-pipeline", "quality-dashboard"], library(), posting_text=DESCRIPTION,
                           **kw)


def test_the_story_letter_passes_without_warnings():
    from workbench_helpers import good_result

    assert _letter_check(good_result()["cover_letter"]["paragraphs"]) == ([], [])


def test_a_three_paragraph_tools_list_letter_warns():
    tools_list = [
        "I am applying for the Senior Data Engineer role. At Acme I built pipelines in Python, SQL, Airflow and "
        "Spark that run every night for the finance warehouse and its analysts across several source systems.",
        "I migrated the orders pipeline from cron to Airflow and Spark with dbt models, cutting runtime from 6 hours "
        "to 45 minutes. I also built a Superset dashboard with SQL checks that caught 2 schema regressions before "
        "release, and it served 3 teams. The pipeline moves 40 million rows per day across 12 source systems, and "
        "failures dropped 80% after the move to the new scheduler and the new checks I wrote for it in Python. "
        + "I worked with analysts and engineers on the platform every week to keep the data correct and on time. " * 4,
        "Your Customer Data Platform is the center of the role, and I have built on one before. I would be glad to "
        "talk about the pipeline work and the dashboard in more detail whenever it suits your team.",
    ]
    errors, warnings = _letter_check(tools_list)
    assert errors == [], errors
    assert any("sentence 2 names 4 tools (Airflow, Python, Spark, SQL)" in w for w in warnings), warnings
    assert any("first sentence doesn't name Initech" in w for w in warnings), warnings


def test_stock_phrases_are_errors():
    from workbench_helpers import good_result

    paragraphs = good_result()["cover_letter"]["paragraphs"]
    paragraphs[0] = "I am writing to express my interest in Initech. " + paragraphs[0]
    paragraphs[3] += " My unique blend of skills would not only help the team but also leverage the platform."
    errors, _ = _letter_check(paragraphs)
    stock = next(e for e in errors if "stock phrases" in e)
    for phrase in ("I am writing to express", "leverage", "unique blend of", "not only ... but also"):
        assert phrase in stock, stock


def test_needs_input_markers_name_the_question():
    from workbench_helpers import good_result

    paragraphs = good_result()["cover_letter"]["paragraphs"]
    paragraphs[0] += " [NEEDS INPUT: why Initech and not another data team?]"
    errors, _ = _letter_check(paragraphs)
    assert any("still needs your input: why Initech and not another data team?" in e for e in errors), errors


def test_paragraph_and_word_bounds():
    from workbench_helpers import good_result

    paragraphs = good_result()["cover_letter"]["paragraphs"]
    errors, _ = _letter_check(paragraphs[:2])
    assert any("has 2 paragraphs; it needs 3-5" in e for e in errors)
    assert any("words; at least 220" in e for e in errors)
    errors, _ = _letter_check(paragraphs + [paragraphs[1]] * 2)
    assert any("has 6 paragraphs" in e for e in errors) and any("at most 380" in e for e in errors)
    assert _letter_check(paragraphs[:3] + [paragraphs[3] + " " + paragraphs[2]])[0] == []
