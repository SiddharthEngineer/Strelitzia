"""Resume layout helpers shared by the Claude workbench: the page's line budget, bullets per role and the
one-page fit loop.

Resumes are written in a Claude Pro chat (strelitzia.scoring.workbench); the API tailor and its judge are gone.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from strelitzia.scoring.content_library import ContentLibrary
from strelitzia.scoring.resume_model import Bullet, RoleEntry, TailoredResume

# The page is full at 95-100%; the plan aims for 97% and never past 99%, so a bullet that wraps one line long
# still fits.
FILL_MIN, FILL_TARGET, FILL_MAX = 0.95, 0.97, 0.99
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


def bullet_plan(library: ContentLibrary, base: TailoredResume | None, budget: Budget) -> dict[str, int]:
    """Exact bullets per content-library role, so the page fills to FILL_TARGET-FILL_MAX.

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
    want = budget.bullets
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


def _role_slots(
    library: ContentLibrary, base: TailoredResume | None = None,
) -> dict[str, tuple[int, int]]:
    """Bullet range per content-library role, shaped like the base resume.

    The max is the role's bullet count in the base resume; the min is two fewer (at least one
    for the most recent role). A role the base resume doesn't show gets 0-2. Without a base
    resume: most recent role 2-5, others 0-3.
    """
    library.ensure_keys()
    counts = {r.role_key: len(r.bullets) for r in base.roles} if base else {}
    slots: dict[str, tuple[int, int]] = {}
    for i, role in enumerate(library.roles):
        if not counts:
            slots[role.key] = (2, 5) if i == 0 else (0, 3)
        elif role.key in counts:
            hi = max(counts[role.key], 1)
            slots[role.key] = (max(1 if i == 0 else 0, hi - 2), hi)
        else:
            slots[role.key] = (0, 2)
    return slots


def page_plan(library: ContentLibrary, base: TailoredResume | None, profile: dict,
              fixed: dict) -> tuple[dict[str, int], Budget]:
    """The exact bullets per role for this user's page, and the budget behind them.

    The budget is measured with the base resume's role headings (resume_fixed.yaml's win) and Skills and no
    Summary, so the packet and the checks of its draft always agree.
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
    return bullet_plan(library, base, budget), budget


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
