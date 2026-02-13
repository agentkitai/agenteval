"""Interactive terminal review of generated eval cases."""

from __future__ import annotations

from typing import List

from agenteval.models import EvalCase


class InteractiveReviewer:
    """Review generated EvalCases interactively in the terminal."""

    def review(self, cases: List[EvalCase]) -> List[EvalCase]:
        """Show each case and prompt user to accept, skip, or edit.

        Returns only accepted (and optionally edited) cases.
        """
        accepted: List[EvalCase] = []

        for i, case in enumerate(cases, 1):
            print(f"\n── Case {i}/{len(cases)}: {case.name} ──")
            print(f"  Input:    {case.input[:80]}")
            print(f"  Expected: {case.expected}")
            print(f"  Grader:   {case.grader}")
            if case.tags:
                print(f"  Tags:     {', '.join(case.tags)}")

            choice = input("[y]es / [n]o / [e]dit? ").strip().lower()
            if choice in ("y", "yes", ""):
                accepted.append(case)
            elif choice in ("e", "edit"):
                edited = self._edit_case(case)
                if edited is not None:
                    accepted.append(edited)
            # 'n' or anything else → skip

        return accepted

    def _edit_case(self, case: EvalCase) -> EvalCase | None:
        """Open case in $EDITOR via tempfile. Returns edited case or original."""
        import os
        import tempfile

        import yaml

        editor = os.environ.get("EDITOR", "vi")
        data = {
            "name": case.name,
            "input": case.input,
            "expected": case.expected,
            "grader": case.grader,
            "tags": case.tags,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f, default_flow_style=False)
            tmp_path = f.name

        try:
            os.system(f"{editor} {tmp_path}")
            with open(tmp_path) as f:
                edited = yaml.safe_load(f)
            if edited:
                return EvalCase(
                    name=edited.get("name", case.name),
                    input=edited.get("input", case.input),
                    expected=edited.get("expected", case.expected),
                    grader=edited.get("grader", case.grader),
                    tags=edited.get("tags", case.tags),
                )
        except Exception:
            pass
        finally:
            os.unlink(tmp_path)

        return case
