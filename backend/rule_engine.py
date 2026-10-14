from dataclasses import dataclass
from typing import Any


KP_FINE_THRESHOLD_PHP = 5000


@dataclass
class RuleTrace:
    rule_id: str
    fired: bool
    message: str
    authority: str
    category: str


def _missing_fields(case_info: Any) -> list[str]:
    required = [
        "case_id",
        "barangay_name",
        "city_municipality",
        "case_year",
        "case_type",
        "dispute_category",
        "complainant_residency",
        "respondent_residency",
    ]
    missing: list[str] = []
    for field in required:
        value = getattr(case_info, field, None)
        if value is None or value == "":
            missing.append(field)
    return missing


def _flag(case_info: Any, field: str) -> bool:
    return bool(getattr(case_info, field, False))


def _text(case_info: Any, field: str) -> str:
    return str(getattr(case_info, field, "") or "").strip()


def trace(rule_id: str, fired: bool, message: str, authority: str, category: str) -> RuleTrace:
    return RuleTrace(
        rule_id=rule_id,
        fired=fired,
        message=message,
        authority=authority,
        category=category,
    )


def evaluate_jurisdiction(case_info: Any, keyword_result: dict[str, Any]) -> dict[str, Any]:
    traces: list[RuleTrace] = []
    missing = _missing_fields(case_info)

    complainant_residency = getattr(case_info, "complainant_residency", None)
    respondent_residency = getattr(case_info, "respondent_residency", None)
    max_penalty = getattr(case_info, "maximum_penalty_years", None)
    fine_amount = getattr(case_info, "fine_amount_php", None)
    government_party = _flag(case_info, "government_party_involved")
    already_filed = _flag(case_info, "already_filed_in_court")
    form_sensitive = _flag(case_info, "has_vawc_or_child_abuse_indicators")
    vawc_trigger = bool(keyword_result.get("vawc_trigger") or form_sensitive)
    juridical_entity_party = _flag(case_info, "has_juridical_entity_party")
    public_officer_official_function = _flag(case_info, "public_officer_involved") and _flag(
        case_info,
        "public_officer_official_function",
    )
    no_private_offended_party = _flag(case_info, "no_private_offended_party")
    penalty_lookup_required = _flag(case_info, "penalty_lookup_required")
    real_property_different_lgu = _flag(case_info, "real_property_in_different_city_municipality")
    parties_different_lgu = _flag(case_info, "parties_in_different_city_municipality")
    adjoining_with_agreement = _flag(case_info, "parties_in_adjoining_barangays") and _flag(
        case_info,
        "mutual_agreement_to_kp",
    )
    property_with_agreement = _flag(case_info, "mutual_agreement_to_kp")
    direct_court_exception = any(
        _flag(case_info, field)
        for field in [
            "accused_under_detention",
            "liberty_or_habeas_issue",
            "provisional_remedy_needed",
            "statute_limitations_urgent",
        ]
    )
    minor_or_incompetent = _flag(case_info, "minor_or_incompetent_party")
    invalid_next_of_kin = minor_or_incompetent and _flag(case_info, "next_of_kin_is_lawyer")
    indigenous_dispute = _flag(case_info, "indigenous_community_dispute")
    indigenous_same_community = _flag(case_info, "same_indigenous_community")
    indigenous_agreed = _flag(case_info, "indigenous_process_agreed")

    same_barangay = complainant_residency == "same_barangay" and respondent_residency == "same_barangay"
    adjacent_barangays = (
        complainant_residency in {"same_barangay", "adjacent_barangay"}
        and respondent_residency in {"same_barangay", "adjacent_barangay"}
        and not same_barangay
    )
    different_municipality_marker = (
        complainant_residency == "different_municipality"
        or respondent_residency == "different_municipality"
    )
    different_municipality = (
        different_municipality_marker or parties_different_lgu
    ) and not adjoining_with_agreement
    residency_valid = same_barangay or adjacent_barangays or adjoining_with_agreement

    traces.append(
        trace(
            "KP-COVER-01",
            residency_valid and not missing,
            "Parties are eligible for ordinary barangay settlement coverage after residency screening."
            if residency_valid and not missing
            else "Ordinary barangay settlement coverage is not yet established from the intake facts.",
            "R.A. 7160, Book III, Title I, Chapter VII, Sec. 408",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-02",
            juridical_entity_party,
            "A corporation, partnership, cooperative, association, or other juridical entity appears as a party."
            if juridical_entity_party
            else "No juridical entity party was marked.",
            "DOJ IRR Rule VI, Sec. 1; KP Handbook Ch. 2",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-03",
            government_party,
            "Government, subdivision, or instrumentality is marked as a party."
            if government_party
            else "No government party involvement was marked.",
            "R.A. 7160, Sec. 408(a)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-04",
            public_officer_official_function,
            "A public officer or employee is involved and the dispute relates to official functions."
            if public_officer_official_function
            else "No public-officer official-function exception was marked.",
            "R.A. 7160, Sec. 408(b)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-05",
            (max_penalty is not None and max_penalty > 1)
            or (fine_amount is not None and fine_amount > KP_FINE_THRESHOLD_PHP),
            f"Penalty/fine ceiling exceeded: maximum penalty={max_penalty}, fine=PHP {fine_amount}."
            if (max_penalty is not None and max_penalty > 1)
            or (fine_amount is not None and fine_amount > KP_FINE_THRESHOLD_PHP)
            else f"Penalty/fine ceiling was not exceeded or is not applicable; KP fine threshold is PHP {KP_FINE_THRESHOLD_PHP:,}.",
            "R.A. 7160, Sec. 408(c)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-06",
            no_private_offended_party,
            "The offense has no private offended party."
            if no_private_offended_party
            else "A no-private-offended-party exception was not marked.",
            "R.A. 7160, Sec. 408(d)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-07",
            real_property_different_lgu and not property_with_agreement,
            "Real property is located in different cities/municipalities and no KP submission agreement was marked."
            if real_property_different_lgu and not property_with_agreement
            else "No blocking real-property different-city/municipality exception was marked.",
            "R.A. 7160, Sec. 408(e)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-08",
            parties_different_lgu and not adjoining_with_agreement,
            "Parties reside in different cities/municipalities without both adjoining-barangay and mutual-agreement facts."
            if parties_different_lgu and not adjoining_with_agreement
            else "No blocking different-city/municipality residence exception was marked.",
            "R.A. 7160, Sec. 408(f)",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-COVER-10",
            _text(case_info, "proceeding_origin") == "court_referred",
            "Case is marked as court-referred for possible barangay settlement before trial."
            if _text(case_info, "proceeding_origin") == "court_referred"
            else "Case is not marked as court-referred.",
            "R.A. 7160, Sec. 408, final paragraph",
            "coverage",
        )
    )
    traces.append(
        trace(
            "KP-VENUE-01",
            same_barangay,
            "Same barangay residency detected." if same_barangay else "Parties are not both marked same_barangay.",
            "R.A. 7160, Sec. 409(a)",
            "venue",
        )
    )
    traces.append(
        trace(
            "KP-VENUE-02",
            adjacent_barangays,
            "Different barangays within the same city/municipality may proceed in the respondent barangay."
            if adjacent_barangays
            else "Different-barangay same-city/municipality venue was not detected from residency markers.",
            "R.A. 7160, Sec. 409(b)",
            "venue",
        )
    )
    traces.append(
        trace(
            "KP-VENUE-03",
            _flag(case_info, "real_property_involved"),
            f"Real-property venue applies; property barangay='{_text(case_info, 'real_property_barangay')}'."
            if _flag(case_info, "real_property_involved")
            else "No real-property venue fact was marked.",
            "R.A. 7160, Sec. 409(c)",
            "venue",
        )
    )
    traces.append(
        trace(
            "KP-VENUE-04",
            _flag(case_info, "workplace_or_school_dispute"),
            f"Workplace/school venue applies; location barangay='{_text(case_info, 'workplace_or_school_barangay')}'."
            if _flag(case_info, "workplace_or_school_dispute")
            else "No workplace/school venue fact was marked.",
            "R.A. 7160, Sec. 409(d)",
            "venue",
        )
    )
    traces.append(
        trace(
            "TRIG-01",
            vawc_trigger,
            "VAWC, child-abuse, violence, or sensitive-safety indicator detected."
            if vawc_trigger
            else "No VAWC/child-abuse sensitive indicator was detected.",
            "R.A. 9262 safety cross-reference; R.A. 7160 Secs. 410-413 guardrail",
            "safety",
        )
    )
    traces.append(
        trace(
            "TRIG-02",
            minor_or_incompetent,
            "A minor or incompetent party is involved; next-of-kin assistance and child-protection review may be required."
            if minor_or_incompetent
            else "No minor/incompetent party was marked.",
            "R.A. 7160, Sec. 415; R.A. 7610 safety cross-reference",
            "safety",
        )
    )
    traces.append(
        trace(
            "TRIG-03",
            direct_court_exception,
            "A direct-to-court exception is marked: detention, liberty/habeas issue, provisional remedy, or limitations urgency."
            if direct_court_exception
            else "No direct-to-court exception was marked.",
            "R.A. 7160, Sec. 412(b)",
            "safety",
        )
    )
    traces.append(
        trace(
            "TRIG-06",
            penalty_lookup_required,
            "Penalty/fine lookup is required before the system can confidently accept KP coverage."
            if penalty_lookup_required
            else "No unresolved penalty/fine lookup was marked.",
            "R.A. 7160, Sec. 408(c)",
            "manual_review",
        )
    )
    traces.append(
        trace(
            "TRIG-07",
            different_municipality or real_property_different_lgu,
            "Different-city/municipality or real-property venue facts require jurisdiction/venue review."
            if different_municipality or real_property_different_lgu
            else "No different-city/municipality venue trigger was marked.",
            "R.A. 7160, Secs. 408(e)-(f), 409",
            "manual_review",
        )
    )
    traces.append(
        trace(
            "TRIG-08",
            already_filed,
            "Case is already filed in court or otherwise outside ordinary intake."
            if already_filed
            else "Case is not marked as already filed in court.",
            "KP Handbook manual-review trigger; R.A. 7160 Sec. 412(b)",
            "manual_review",
        )
    )
    traces.append(
        trace(
            "TRIG-11",
            invalid_next_of_kin,
            "Minor/incompetent party assistant is marked as a lawyer, which conflicts with the KP appearance rule."
            if invalid_next_of_kin
            else "No invalid next-of-kin lawyer assistance issue was marked.",
            "R.A. 7160, Sec. 415",
            "manual_review",
        )
    )
    traces.append(
        trace(
            "KP-ICC-01",
            indigenous_dispute,
            "Indigenous/community dispute-resolution facts are marked."
            if indigenous_dispute
            else "No indigenous community dispute-resolution fact was marked.",
            "R.A. 7160, Secs. 399(f), 412(c); DOJ IRR Rule IX",
            "indigenous_process",
        )
    )
    traces.append(
        trace(
            "KP-ICC-02",
            indigenous_dispute and indigenous_same_community,
            "Parties are marked as members of the same indigenous cultural community."
            if indigenous_dispute and indigenous_same_community
            else "Same-indigenous-community routing was not established.",
            "R.A. 7160, Sec. 412(c); DOJ IRR Rule IX",
            "indigenous_process",
        )
    )
    traces.append(
        trace(
            "KP-ICC-03",
            indigenous_dispute and not indigenous_same_community and indigenous_agreed,
            "Mixed-community indigenous process is marked with mutual agreement."
            if indigenous_dispute and not indigenous_same_community and indigenous_agreed
            else "Mixed-community indigenous-process agreement was not established.",
            "DOJ IRR Rule IX; KP Handbook Ch. 5",
            "indigenous_process",
        )
    )

    exclusion_ground = "none"
    decision = "ambiguous_manual_review"
    confidence = "low"
    recommended_next_action = "Review missing or ambiguous facts before deciding KP jurisdiction."

    if vawc_trigger:
        decision = "refer_to_pnp_wcpc_or_authority"
        exclusion_ground = "vawc"
        confidence = "high"
        recommended_next_action = "Refer to PNP Women and Children Protection Desk. Do not proceed with barangay mediation."
    elif direct_court_exception:
        decision = "outside_kp"
        exclusion_ground = "direct_court_exception"
        confidence = "high"
        recommended_next_action = "Allow direct filing or urgent legal referral because a Section 412(b) exception applies."
    elif juridical_entity_party:
        decision = "outside_kp"
        exclusion_ground = "juridical_entity_party"
        confidence = "high"
        recommended_next_action = "Refer to the proper court or agency because KP proceedings are for individual parties."
    elif public_officer_official_function:
        decision = "outside_kp"
        exclusion_ground = "public_officer_official_function"
        confidence = "high"
        recommended_next_action = "Refer to the proper office because the dispute concerns official public functions."
    elif no_private_offended_party:
        decision = "outside_kp"
        exclusion_ground = "no_private_offended_party"
        confidence = "high"
        recommended_next_action = "Refer outside KP because the offense has no private offended party."
    elif real_property_different_lgu and not property_with_agreement:
        decision = "outside_kp"
        exclusion_ground = "real_property_different_city_municipality"
        confidence = "high"
        recommended_next_action = "Refer or obtain proper agreement because the real property is located in different cities or municipalities."
    elif different_municipality:
        decision = "outside_kp"
        exclusion_ground = "different_municipality"
        confidence = "high"
        recommended_next_action = "Refer the parties to the proper court or authority because KP residency is not satisfied."
    elif max_penalty is not None and max_penalty > 1:
        decision = "outside_kp"
        exclusion_ground = "penalty_over_1_year"
        confidence = "high"
        recommended_next_action = "Refer the matter outside KP because the offense exceeds the penalty threshold."
    elif fine_amount is not None and fine_amount > KP_FINE_THRESHOLD_PHP:
        decision = "outside_kp"
        exclusion_ground = "fine_over_5000"
        confidence = "high"
        recommended_next_action = "Refer the matter outside KP because the fine exceeds the legal KP threshold."
    elif government_party:
        decision = "outside_kp"
        exclusion_ground = "government_party"
        confidence = "high"
        recommended_next_action = "Refer to the proper office because a government party is involved."
    elif already_filed:
        decision = "outside_kp"
        exclusion_ground = "already_filed_in_court"
        confidence = "high"
        recommended_next_action = "Do not proceed with KP mediation because the case is already filed in court."
    elif penalty_lookup_required:
        decision = "ambiguous_manual_review"
        exclusion_ground = "penalty_lookup_required"
        confidence = "low"
        recommended_next_action = "Perform a legal penalty/fine lookup before deciding KP coverage."
    elif invalid_next_of_kin:
        decision = "ambiguous_manual_review"
        exclusion_ground = "invalid_minor_assistance"
        confidence = "low"
        recommended_next_action = "Review the minor/incompetent-party assistance because lawyers may not appear as representatives in KP proceedings."
    elif indigenous_dispute and (indigenous_same_community or indigenous_agreed):
        decision = "ambiguous_manual_review"
        exclusion_ground = "indigenous_customary_process"
        confidence = "medium"
        recommended_next_action = "Route to the applicable indigenous customary dispute-resolution process or record mutual agreement before ordinary KP handling."
    elif missing:
        decision = "ambiguous_manual_review"
        exclusion_ground = "incomplete_facts"
        confidence = "low"
        recommended_next_action = "Complete the missing case information and have barangay officials review the case."
    elif residency_valid:
        decision = "within_kp"
        exclusion_ground = "none"
        confidence = "high" if same_barangay else "medium"
        recommended_next_action = "Proceed with Katarungang Pambarangay mediation and document the case analysis."

    traces.append(
        trace(
            "KP-DECISION-01",
            decision == "within_kp",
            "No exclusion grounds found and residency is valid."
            if decision == "within_kp"
            else "Within-KP conclusion was not reached.",
            "R.A. 7160, Sec. 408",
            "decision",
        )
    )
    traces.append(
        trace(
            "KP-DECISION-02",
            decision == "ambiguous_manual_review",
            "Facts are incomplete or ambiguous; manual review is required."
            if decision == "ambiguous_manual_review"
            else "Facts are sufficient for a deterministic decision.",
            "KP Handbook manual-review trigger table",
            "decision",
        )
    )

    return {
        "jurisdiction_decision": decision,
        "exclusion_ground": exclusion_ground,
        "confidence_level": confidence,
        "missing_fields": missing,
        "recommended_next_action": recommended_next_action,
        "rule_results": [trace.__dict__ for trace in traces],
    }
