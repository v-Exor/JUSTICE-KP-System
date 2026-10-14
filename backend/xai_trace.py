from typing import Any


def build_xai_trace(rule_result: dict[str, Any], keyword_result: dict[str, Any]) -> list[str]:
    trace_lines: list[str] = []
    detected = keyword_result.get("detected_keywords", [])

    for rule in rule_result.get("rule_results", []):
        state = "Fired" if rule.get("fired") else "Not Fired"
        authority = rule.get("authority")
        source = f" [{authority}]" if authority else ""
        line = f"{rule.get('rule_id')} {state}: {rule.get('message')}{source}"
        if rule.get("rule_id") == "TRIG-01" and rule.get("fired") and detected:
            line = f"{line} Detected keyword(s): {', '.join(detected)}."
        trace_lines.append(line)

    trace_lines.append(
        f"Final Decision: {rule_result.get('recommended_next_action')}"
    )
    return trace_lines
