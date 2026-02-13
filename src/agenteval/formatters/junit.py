"""JUnit XML output formatter for CI results."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from agenteval.ci import CIResult
from agenteval.models import EvalRun


def format_junit(ci_result: CIResult, run: EvalRun) -> str:
    """Format CI result and run as JUnit XML string."""
    total = len(run.results)
    failures = sum(1 for r in run.results if not r.passed)

    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(testsuites, "testsuite", {
        "name": run.suite,
        "tests": str(total),
        "failures": str(failures),
    })

    for r in run.results:
        testcase = ET.SubElement(testsuite, "testcase", {
            "name": r.case_name,
            "classname": run.suite,
            "time": f"{r.latency_ms / 1000:.3f}",
        })
        if not r.passed:
            reason = r.details.get("reason", r.details.get("error", "failed"))
            failure = ET.SubElement(testcase, "failure", {"message": str(reason)})
            failure.text = str(reason)

    ET.indent(testsuites)
    return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)
