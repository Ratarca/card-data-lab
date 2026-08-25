---
name: sincronize
description: 'Synchronize README.md and EXECUTION_PLAN.md so they stay consistent. Use when: docs drift after architecture/stack/roadmap changes; user asks to sync or reconcile README with execution plan.'
argument-hint: 'Optional: specific topic to check (e.g. event catalog)'
---

# Sincronize — README ↔ Execution Plan

Synchronize `README.md` and `EXECUTION_PLAN.md` so they never contradict each other.

## When to run

After any change to architecture, stack, stages, gates, roadmap, or repo structure in either file.

## Instructions

1. **Read both files fully**: `README.md` and `EXECUTION_PLAN.md`.

2. **Check the sync contract** — each document has a role:
   - `README.md` = *what & why*: system design (C4), architecture decisions, data model, event catalog.
   - `EXECUTION_PLAN.md` = *how & when*: stages, gates, iteration tracker, parallel tracks, taskipy commands.

3. **Verify these points of consistency** and fix any drift:

   | Topic | Source of truth | Must match in |
   |---|---|---|
   | Architecture style (e.g. modular monolith) | README → System Design | EXECUTION_PLAN Stage 2 wording |
   | Stack & tooling (uv, taskipy, dbt-duckdb...) | README → Stack | EXECUTION_PLAN Stage 0 + tracker "Tester" column |
   | Event catalog (names of all 10 `event_type`s) | README → Event catalog | EXECUTION_PLAN Stage 1 |
   | Facts & dimensions list (`fct_*`, `dim_*`) | README → OLAP layer | EXECUTION_PLAN Stage 5 |
   | KPIs (5 dashboards) & ML targets | README → Data Products | EXECUTION_PLAN Stage 6A/6B |
   | Repository structure | README → Repository structure | EXECUTION_PLAN Stage 0 scaffold list |
   | Roadmap summary | EXECUTION_PLAN stages/gates | README → Roadmap section |

4. **Fix drift rules**:
   - If a *decision* changed (architecture, modeling), update both files; README holds the rationale, EXECUTION_PLAN reflects it in affected stages/gates/tracker rows.
   - If only *progress* changed, update only the Iteration Tracker statuses in `EXECUTION_PLAN.md` — never touch README for progress.
   - Keep cross-links valid: README links to `EXECUTION_PLAN.md`, EXECUTION_PLAN links back to README sections.

5. **Report** at the end: list what was out of sync, what you changed in each file, and confirm both are consistent (or flag open questions).

## Output format

```text
Sync report
- Checked: <list of topics from step 3>
- Drift found: <topic → description> (or "none")
- Changes: README.md: <...> / EXECUTION_PLAN.md: <...>
- Status: ✅ synchronized | ⚠️ needs human decision on <topic>
```
