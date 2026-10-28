"""The page's line budget (tailor.line_budget, measured by rendering) and the exact bullets per role (bullet_plan)."""

import pytest

from strelitzia.scoring.content_library import ContentLibrary, Project, RoleSection
from strelitzia.scoring.pdf import render_pdf
from strelitzia.scoring.resume_model import Bullet, RoleEntry, TailoredResume
from strelitzia.scoring.tailor import FILL_MAX, Budget, bullet_plan, line_budget
from strelitzia.scoring.template import DEFAULT_TEMPLATE_PATH, parse_base_resume, render_resume
from workbench_helpers import BASE_RESUME, FIXED, PROFILE, library

pytestmark = pytest.mark.real_layout

_WORDS = ("Owned the nightly orders pipeline feeding the finance warehouse for 3 teams, moving 40 million rows "
          "per day across 12 source systems and cutting runtime from 6 hours to 45 minutes with retries, alerts "
          "and a staged rollout that analysts relied on every morning").split()


def _bullet(chars: int) -> str:
    out = ""
    while len(out) < chars:
        out = f"{out} {_WORDS[len(out.split()) % len(_WORDS)]}".strip()
    return out[:chars].rstrip()


def _lib(n: int) -> ContentLibrary:
    return ContentLibrary(roles=[
        RoleSection(title=f"Engineer {i}, Co{i}", dates="2020", projects=[
            Project(name=f"P{i}", role_header="## ROLE", dates="2020", context="c", scope_scale="s",
                    tools_actions="t", outcome_metrics="o", angles=[])])
        for i in range(n)]).ensure_keys()


def _budget(bullets: int, bullet_lines: float = 2.0) -> Budget:
    total = 60.0
    return Budget(lines_free=bullets * bullet_lines + (1 - FILL_MAX) * total + 0.5, chars_per_line=120,
                  lines_total=total, bullet_lines=bullet_lines)


def test_band_is_two_printed_lines():
    assert Budget(lines_free=10, chars_per_line=120).band == (192, 234)


def test_plan_follows_the_recency_tiers():
    lib = _lib(4)
    keys = [r.key for r in lib.roles]
    assert list(bullet_plan(lib, None, _budget(11)).values()) == [5, 3, 2, 1]
    assert list(bullet_plan(lib, None, _budget(15)).values()) == [6, 4, 3, 2]
    assert sum(bullet_plan(lib, None, _budget(13)).values()) == 13
    assert list(bullet_plan(lib, None, _budget(17)).values()) == [7, 5, 3, 2]  # past the maximums, recent first
    assert list(bullet_plan(lib, None, _budget(8)).values()) == [3, 2, 2, 1]  # the biggest role gives first
    assert list(bullet_plan(lib, None, _budget(3)).values()) == [1, 1, 1, 0]  # then the oldest role goes
    assert set(bullet_plan(lib, None, _budget(11))) == set(keys)


def test_plan_uses_only_the_base_resume_roles():
    lib = _lib(3)
    base = TailoredResume(roles=[RoleEntry(role_key=lib.roles[0].key, title="t", company="c", dates="d",
                                           tagline=None),
                                 RoleEntry(role_key=lib.roles[2].key, title="t", company="c", dates="d",
                                           tagline=None)])
    assert list(bullet_plan(lib, base, _budget(8)).values()) == [5, 0, 3]


def test_base_fixture_plan_fills_the_page(tmp_path):
    lib = library()
    base = parse_base_resume(BASE_RESUME, lib)
    budget = line_budget(PROFILE, FIXED, base.roles, base.skills)
    assert 100 <= budget.chars_per_line <= 140
    plan = bullet_plan(lib, base, budget)
    assert plan["data-engineer-acme"] >= plan["data-analyst-intern-globex"] > 0
    lo, hi = budget.band
    for role in base.roles:
        role.bullets = [Bullet(_bullet((lo + hi) // 2)) for _ in range(plan[role.role_key])]
    info = render_pdf(render_resume(base, PROFILE, template_path=DEFAULT_TEMPLATE_PATH, fixed=FIXED),
                      str(tmp_path / "plan.pdf"))
    fill = info["content_height_pt"] / info["usable_height_pt"]
    assert info["pages"] == 1 and 0.95 <= fill <= 1.0, fill
