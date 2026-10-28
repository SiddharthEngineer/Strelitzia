"""Resume layout helpers shared by the Claude workbench: the page's line budget, bullets per role and the
one-page fit loop.

Resumes are written in a Claude Pro chat (strelitzia.scoring.workbench); the API tailor and its judge are gone.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from strelitzia.scoring.content_library import ContentLibrary
from strelitzia.scoring.resume_model import Bullet, RoleEntry, TailoredResume

# The page is full at 95-100%. The plan never goes past 98%, so a bullet that wraps one line long (~1.7%) still
# fits; a plan that lands a little under 95% is closed by spacing (fill_page).
FILL_MIN, FILL_TARGET, FILL_MAX = 0.95, 0.97, 0.98
# Below FILL_REJECT the draft goes back to Claude; between it and FILL_MIN, spacing (the template's --gap, at most
# GAP_MAX_PX) closes the gap.
FILL_REJECT, GAP_MAX_PX = 0.90, 4.0
# Bullets are two printed lines (user decision, 2026-10-27): this band of characters per bullet line.
BAND = (1.6, 1.95)
# Bullets per role by recency (research §3): the most recent role 5-6, then 3-4, 2-3, and 1-2 for the rest.
TIERS = ((5, 6), (3, 4), (2, 3), (1, 2))
_PLACEHOLDER = "Placeholder bullet"


@dataclass(frozen=True)
class Budget:
    """The room a page leaves for experience bullets, measured by rendering."""
    lines_free: float  # room below the fixed parts (header, role headings, education, skills, Summary), in lines
    chars_per_line: int  # characters of typical bullet text per printed line
    lines_total: float = 0.0  # the usable page height, in lines
    bullet_lines: float = 2.0  # what one two-line bullet takes, its spacing included, in lines

    @property
    def band(self) -> tuple[int, int]:
        """(min, max) characters per bullet, so each prints as two lines."""
        return round(self.chars_per_line * BAND[0]), round(self.chars_per_line * BAND[1])

    @property
    def bullets(self) -> int:
        """How many two-line bullets fill the page without going past FILL_MAX."""
        room = self.lines_free - (1 - FILL_MAX) * self.lines_total
        return max(0, math.floor(room / self.bullet_lines + 1e-9)) if self.bullet_lines > 0 else 0


def line_budget(profile: dict, fixed: dict, roles: list[RoleEntry], skills: dict[str, str],
                summary: str = "") -> Budget:
    """Measure the room for bullets: render the fixed parts with the role headings and placeholder lines.

    Two renders in one browser session: every role with one one-line bullet, and the same with a second bullet
    in the first role. Their difference is what a bullet line and its spacing take; the line height and the
    characters per line come from the first experience bullet.
    """
    from strelitzia.scoring import pdf as pdf_mod
    from strelitzia.scoring.template import render_resume

    def resume(extra: int) -> TailoredResume:
        out = [RoleEntry(role_key=r.role_key, title=r.title, company=r.company, dates=r.dates, tagline=r.tagline,
                         bullets=[Bullet(_PLACEHOLDER) for _ in range(1 + (extra if i == 0 else 0))])
               for i, r in enumerate(roles)]
        return TailoredResume(roles=out, skills=dict(skills), headline=summary)

    one, two = pdf_mod.measure_layout([render_resume(resume(0), profile, fixed=fixed),
                                       render_resume(resume(1), profile, fixed=fixed)])
    line_pt = one.get("line_pt") or 9.5 * 1.35
    bullet_pt = (two["content_height_pt"] - one["content_height_pt"]) if roles else line_pt
    bullet_pt = max(bullet_pt, line_pt)
    fixed_pt = one["content_height_pt"] - len(roles) * bullet_pt
    usable = pdf_mod.USABLE_HEIGHT_PT
    return Budget(lines_free=(usable - fixed_pt) / line_pt, chars_per_line=one.get("chars_per_line") or 120,
                  lines_total=usable / line_pt, bullet_lines=(bullet_pt + line_pt) / line_pt)


def bullet_plan(library: ContentLibrary, base: TailoredResume | None, budget: Budget,
                fewer: int = 0) -> dict[str, int]:
    """Exact bullets per content-library role, so the page fills to FILL_TARGET-FILL_MAX (with `fewer` bullets
    less in all: a Summary takes about one bullet's room).

    The roles are the base resume's (all of the library's without one); every other role gets 0, as does a role
    that doesn't fit even at one bullet (oldest first). Counts start at each role's tier minimum; a short page
    takes bullets from the role with the most (the older on a tie), a long one adds them most recent first, up to
    the tier maximums and then past them.
    """
    library.ensure_keys()
    shown = {r.role_key for r in base.roles} if base and base.roles else None
    keys = [r.key for r in library.roles if shown is None or r.key in shown]
    plan = {r.key: 0 for r in library.roles}
    counts = [TIERS[min(i, len(TIERS) - 1)][0] for i in range(len(keys))]
    highs = [TIERS[min(i, len(TIERS) - 1)][1] for i in range(len(keys))]
    want = max(0, budget.bullets - fewer)
    while sum(counts) > want:
        over = [(c, i) for i, c in enumerate(counts) if c > 1]
        if over:
            counts[max(over)[1]] -= 1
        else:
            counts[max(i for i, c in enumerate(counts) if c)] = 0
    for cap in (highs, None):
        while keys and sum(counts) < want:
            grew = False
            for i in range(len(counts)):
                if sum(counts) < want and (cap is None or counts[i] < cap[i]):
                    counts[i] += 1
                    grew = True
            if not grew:
                break
    plan.update(zip(keys, counts, strict=True))
    return plan


def page_plan(library: ContentLibrary, base: TailoredResume | None, profile: dict, fixed: dict,
              summary: bool = False) -> tuple[dict[str, int], Budget]:
    """The exact bullets per role for this user's page, and the budget behind them.

    The budget is measured with the base resume's role headings (resume_fixed.yaml's win) and Skills and no
    Summary, so the packet and the checks of its draft always agree; `summary` plans one bullet fewer for a
    draft with one.
    """
    from strelitzia.scoring.template import fixed_roles_from_resume

    library.ensure_keys()
    shown = {r.role_key for r in base.roles} if base and base.roles else None
    heads = {**(fixed_roles_from_resume(base) if base else {}), **(fixed.get("roles") or {})}
    roles = []
    for section in library.roles:
        if shown is None or section.key in shown:
            info = heads.get(section.key) or {}
            roles.append(RoleEntry(role_key=section.key, title=info.get("title") or section.title.split(",")[0].strip(),
                                   company=info.get("company") or "", dates=info.get("dates") or section.dates,
                                   tagline=info.get("tagline") or None))
    budget = line_budget(profile, fixed, roles, base.skills if base else {})
    fewer = 1 if summary else 0
    plan = bullet_plan(library, base, budget, fewer)
    kept = [r for r in roles if plan[r.role_key]]
    if roles and not kept:  # not even one bullet fits: every role stays at 0
        return plan, budget
    if roles and len(kept) < len(roles):  # a dropped role's heading frees room: measure again without it
        budget = line_budget(profile, fixed, kept, base.skills if base else {})
        plan = bullet_plan(library, TailoredResume(roles=kept), budget, fewer)
    return plan, budget


def fit_to_one_page(
    resume: TailoredResume,
    profile: dict,
    fixed: dict,
    slots: dict[str, tuple[int, int]],
    pdf_path: Path,
    max_iterations: int = 4,
) -> tuple[dict, list[str]]:
    """Render to PDF; while it overflows one page, drop a bullet and re-render.

    Each round drops the last bullet of the role with the most bullets above its minimum
    (ties go to the later, older role). Never goes below a role's minimum.

    Returns:
        (render_pdf info of the final render, texts of the dropped bullets). info["overflow"]
        is still True if the resume couldn't be made to fit.
    """
    from strelitzia.scoring import pdf as pdf_mod
    from strelitzia.scoring.template import render_resume

    dropped: list[str] = []
    info = pdf_mod.render_pdf(render_resume(resume, profile, fixed=fixed), str(pdf_path))
    for _ in range(max_iterations):
        if not info["overflow"]:
            break
        surplus = [
            (len(r.bullets) - slots.get(r.role_key, (0, 0))[0], i)
            for i, r in enumerate(resume.roles)
        ]
        best, idx = max(surplus, default=(0, -1))
        if best <= 0:
            break
        dropped.append(resume.roles[idx].bullets.pop().text)
        info = pdf_mod.render_pdf(render_resume(resume, profile, fixed=fixed), str(pdf_path))
    return info, dropped


def fill_page(resume: TailoredResume, profile: dict, fixed: dict, pdf_path: Path, info: dict,
              max_iterations: int = 4) -> tuple[dict, float]:
    """Close a small gap at the bottom of the page: raise the template's --gap until the page is FILL_MIN full.

    Each round re-renders and aims at FILL_TARGET from the spacing's measured effect, never past GAP_MAX_PX.
    A template without --gap doesn't change, so the loop stops after one round.

    Returns:
        (render_pdf info of the final render, the gap in CSS pixels; 0 when the page was already full).
    """
    from strelitzia.scoring import pdf as pdf_mod
    from strelitzia.scoring.template import render_resume

    def render(gap: float) -> dict:
        return pdf_mod.render_pdf(render_resume(resume, profile, fixed=fixed, gap=gap), str(pdf_path))

    usable = info["usable_height_pt"]
    gap, step = 0.0, 1.0
    for _ in range(max_iterations):
        if info["content_height_pt"] >= FILL_MIN * usable or gap >= GAP_MAX_PX:
            break
        new_gap = min(GAP_MAX_PX, gap + step)
        new = render(new_gap)
        if new["overflow"]:
            info = render(gap)
            break
        slope = (new["content_height_pt"] - info["content_height_pt"]) / (new_gap - gap)
        gap, info = new_gap, new
        if slope <= 0:  # the template doesn't use --gap
            return info, 0.0
        step = max(0.25, (FILL_TARGET * usable - info["content_height_pt"]) / slope)
    return info, gap
