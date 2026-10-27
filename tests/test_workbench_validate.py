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
