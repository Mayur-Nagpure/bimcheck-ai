from typing import Any, Dict, List, Optional

SUPPORTED_TYPES = {"Wall", "Door", "Window", "Floor", "Column", "Beam", "Room"}
DIMENSION_REQUIRED = {
    "Wall": ("length", "height", "thickness"),
    "Door": ("width", "height"),
    "Window": ("width", "height"),
    "Floor": ("length", "width", "thickness"),
    "Column": ("width", "depth", "height"),
    "Beam": ("length", "width", "height"),
    "Room": ("length", "width", "height"),
}


def _issue(element_id: str, severity: str, rule: str, message: str) -> Dict[str, str]:
    return {
        "element_id": element_id or "UNKNOWN",
        "severity": severity,
        "rule": rule,
        "message": message,
    }


def check_model(model: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(model, dict):
        raise ValueError("The JSON root must be an object.")
    elements = model.get("elements")
    if not isinstance(elements, list):
        raise ValueError("The JSON file must contain an 'elements' list.")

    issues: List[Dict[str, str]] = []
    seen_ids = set()
    element_ids = {
        str(e.get("id")) for e in elements
        if isinstance(e, dict) and e.get("id") not in (None, "")
    }

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            issues.append(_issue(f"ROW-{index + 1}", "Error", "INVALID_ELEMENT",
                                 "Element must be a JSON object."))
            continue

        eid = str(element.get("id", "")).strip()
        etype = str(element.get("type", "")).strip().title()
        label = eid or f"ROW-{index + 1}"

        if not eid:
            issues.append(_issue(label, "Error", "MISSING_ID",
                                 "Element has no ID. Add a unique identifier."))
        elif eid in seen_ids:
            issues.append(_issue(label, "Error", "DUPLICATE_ID",
                                 f"ID '{eid}' appears more than once."))
        else:
            seen_ids.add(eid)

        if not etype:
            issues.append(_issue(label, "Error", "MISSING_TYPE",
                                 "Element type is missing."))
        elif etype not in SUPPORTED_TYPES:
            issues.append(_issue(label, "Warning", "UNKNOWN_TYPE",
                                 f"Type '{etype}' is not in the prototype's supported types."))

        for dimension in DIMENSION_REQUIRED.get(etype, ()):
            value = element.get(dimension)
            if value is None or value == "":
                issues.append(_issue(label, "Error", "MISSING_DIMENSION",
                                     f"Required dimension '{dimension}' is missing."))
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                issues.append(_issue(label, "Error", "NON_NUMERIC_DIMENSION",
                                     f"Dimension '{dimension}' must be numeric."))
                continue
            if number <= 0:
                issues.append(_issue(label, "Error", "NON_POSITIVE_DIMENSION",
                                     f"Dimension '{dimension}' must be greater than zero."))
            elif number > 100:
                issues.append(_issue(label, "Warning", "UNUSUAL_DIMENSION",
                                     f"Dimension '{dimension}' is {number:g} m; verify the unit and value."))

        if etype in {"Door", "Window"}:
            host_id = str(element.get("host_wall_id", "")).strip()
            if not host_id:
                issues.append(_issue(label, "Warning", "MISSING_HOST",
                                     f"{etype} has no host_wall_id; verify which wall contains it."))
            elif host_id not in element_ids:
                issues.append(_issue(label, "Error", "INVALID_HOST",
                                     f"Host wall ID '{host_id}' does not exist in this model."))

    return {"issues": issues, "elements_checked": len(elements)}


def build_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    issues = results["issues"]
    errors = sum(1 for issue in issues if issue["severity"] == "Error")
    warnings = sum(1 for issue in issues if issue["severity"] == "Warning")
    count = len(issues)
    if count == 0:
        message = "All checked elements passed the current prototype rules."
    else:
        message = (
            f"Checked {results['elements_checked']} elements and found {count} issue(s): "
            f"{errors} error(s) and {warnings} warning(s). Review the issue table, "
            "correct the source model data, and run the checks again."
        )
    return {
        "elements_checked": results["elements_checked"],
        "issue_count": count,
        "errors": errors,
        "warnings": warnings,
        "message": message,
    }


def explain_issues_with_ai(issues: List[Dict[str, str]], api_key: Optional[str] = None) -> str:
    """Use an OpenAI model when a key is supplied; otherwise return local explanations."""
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a careful BIM quality assistant. Explain the supplied "
                            "data-validation issues in plain English. Give practical next steps. "
                            "Do not claim that these checks establish building-code compliance. "
                            "Do not invent data."
                        ),
                    },
                    {"role": "user", "content": str(issues)},
                ],
            )
            return response.output_text
        except Exception as exc:
            return (
                "AI API call failed, so here is a local explanation instead. "
                f"Technical detail: {exc}\n\n" + _local_explanation(issues)
            )
    return _local_explanation(issues)


def _local_explanation(issues: List[Dict[str, str]]) -> str:
    if not issues:
        return "No issues were detected. This only means the data passed the current prototype rules."
    lines = ["### Suggested review steps"]
    for item in issues[:20]:
        lines.append(
            f"- **{item['element_id']} — {item['rule']} ({item['severity']}):** "
            f"{item['message']} Suggested action: inspect the source element and correct or confirm the value."
        )
    if len(issues) > 20:
        lines.append(f"- {len(issues) - 20} additional issues were omitted from this explanation; review the full table.")
    lines.append("\nThese are data-quality suggestions, not engineering approval or code-compliance verification.")
    return "\n".join(lines)
