from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.pilot_business_case import _executive_conclusion, _live_metrics, _metric_states


client = TestClient(app)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _line(**overrides) -> dict:
    payload = {
        "kind": "monetary_cost",
        "financial_treatment": "cost",
        "category": "investment",
        "label": "Initial investment",
        "description": "Governed economic line used by the live business case test.",
        "phase": "execution",
        "unit": "",
        "planned_quantity": None,
        "actual_quantity": None,
        "conservative_amount": 110000,
        "base_amount": 100000,
        "favorable_amount": 90000,
        "committed_amount": 30000,
        "realized_amount": 20000,
        "forecast_amount": 105000,
        "start_month": 0,
        "end_month": None,
        "recurrence": "one_off",
        "source_label": "Approved supplier budget dated 2026-08-26",
        "evidence_node_id": None,
        "alternative_node_id": None,
        "responsible": "Mission owner",
        "assumption": "The approved scope remains materially unchanged.",
        "confidence": "high",
        "include_in_totals": True,
    }
    payload.update(overrides)
    return payload


def test_resource_only_values_never_become_zero_costs() -> None:
    case = {
        "id": "case-resource-only",
        "currency": "EUR",
        "horizon_months": 12,
    }
    resources = [
        _line(
            kind="human_resource",
            financial_treatment="none",
            include_in_totals=False,
            unit="horas",
            planned_quantity=80,
            actual_quantity=12,
            conservative_amount=None,
            base_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
        )
    ]

    metrics = _live_metrics(case, resources)
    states = _metric_states(case, resources)

    assert states["resources"] == "observed_or_estimated"
    assert states["human_hours"] == "observed_or_estimated"
    assert states["planned_human_hours"] == "observed_or_estimated"
    assert states["actual_human_hours"] == "observed_or_estimated"
    assert states["costs"] == "unknown_not_zero"
    assert states["benefits"] == "unknown_not_zero"
    assert states["financial"] == "unknown_not_zero"
    assert "custo monetário continua por determinar" in _executive_conclusion(
        case,
        metrics,
        states,
    )
    assert "0 €" not in _executive_conclusion(case, metrics, states)

    funding_without_value = [
        _line(
            kind="financial_resource",
            financial_treatment="none",
            include_in_totals=False,
            conservative_amount=None,
            base_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
        )
    ]
    assert _metric_states(case, funding_without_value)["funding"] == "unknown_not_zero"

    base_only_cost = _line(
        conservative_amount=None,
        base_amount=125,
        favorable_amount=None,
        committed_amount=None,
        realized_amount=None,
        forecast_amount=None,
    )
    base_only_states = _metric_states(case, [base_only_cost])
    assert base_only_states["budget_base"] == "observed_or_estimated"
    assert base_only_states["forecast_cost"] == "observed_or_estimated"
    assert base_only_states["committed_cost"] == "unknown_not_zero"
    assert base_only_states["realized_cost"] == "unknown_not_zero"
    assert base_only_states["forecast_financial"] == "unknown_not_zero"

    explicit_zero_benefit = _line(
        kind="monetary_benefit",
        financial_treatment="benefit",
        category="avoided_cost",
        conservative_amount=None,
        base_amount=0,
        favorable_amount=None,
        committed_amount=None,
        realized_amount=None,
        forecast_amount=None,
    )
    zero_is_known = _metric_states(case, [base_only_cost, explicit_zero_benefit])
    assert zero_is_known["expected_benefit"] == "observed_or_estimated"
    assert zero_is_known["forecast_financial"] == "observed_or_estimated"

    partial_commitment = _metric_states(
        case,
        [
            _line(committed_amount=50),
            _line(label="Second cost", committed_amount=None),
        ],
    )
    assert partial_commitment["committed_cost"] == "partial_observed_or_estimated"
    partially_realized_costs = [
        _line(realized_amount=50),
        _line(label="Cost without an actual", realized_amount=None),
    ]
    partial_realized_states = _metric_states(case, partially_realized_costs)
    assert partial_realized_states["realized_cost"] == "partial_observed_or_estimated"
    assert "Com dados parciais" in _executive_conclusion(
        case,
        _live_metrics(case, partially_realized_costs),
        partial_realized_states,
    )

    committed_funding = _line(
        kind="financial_resource",
        financial_treatment="none",
        include_in_totals=False,
        conservative_amount=None,
        base_amount=None,
        favorable_amount=None,
        committed_amount=75,
        realized_amount=None,
        forecast_amount=None,
    )
    assert _metric_states(case, [committed_funding])["funding"] == "observed_or_estimated"
    assert _live_metrics(case, [committed_funding])["funding_available"] == 75.0

    realized_without_evidence = _line(
        kind="monetary_benefit",
        financial_treatment="benefit",
        realized_amount=40,
        evidence_node_id=None,
    )
    assert (
        _metric_states(case, [realized_without_evidence])["verified_realized_benefit"]
        == "unknown_not_zero"
    )
    realized_without_evidence["evidence_node_id"] = "evidence-1"
    assert (
        _metric_states(case, [realized_without_evidence])["evidence_linked_realized_benefit"]
        == "observed_or_estimated"
    )
    assert (
        _metric_states(case, [realized_without_evidence])["reviewed_evidence_realized_benefit"]
        == "unknown_not_zero"
    )
    realized_without_evidence["evidence_status"] = "accepted"
    assert (
        _metric_states(case, [realized_without_evidence])["reviewed_evidence_realized_benefit"]
        == "observed_or_estimated"
    )
    assert (
        _metric_states(case, [realized_without_evidence])["verified_realized_benefit"]
        == "unknown_not_zero"
    )


def test_live_business_case_tracks_scenarios_resources_review_and_history(monkeypatch) -> None:
    monkeypatch.setenv("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
    suffix = uuid4().hex[:10]
    registered = client.post(
        "/api/pilot/register",
        json={
            "full_name": "Business Case Reviewer",
            "organization_name": f"Business Case Workspace {suffix}",
            "email": f"business-case-{suffix}@example.com",
            "password": "business-case-test-123",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = _headers(registered.json()["access_token"])
    profile = client.get("/api/pilot/profile", headers=headers)
    organization_id = profile.json()["organization"]["id"]

    mission = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Validate the living economic case",
            "objective": "Track cost, value, time and persistent resources before and after a decision.",
            "central_question": "Does the mission create defensible value after its full lifecycle cost?",
            "context": "Deterministic economic governance contract.",
            "mission_kind": "mission",
            "domain": "investment_decision",
            "priority": "strategic",
            "horizon": "24 months",
            "stakeholders": [],
        },
    )
    assert mission.status_code == 201, mission.text
    mission_payload = mission.json()
    base = f"/api/pilot/business-cases/missions/{mission_payload['code']}"
    graph_base = f"/api/pilot/evidence-graph/missions/{mission_payload['code']}"

    benefit_evidence = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "evidence",
            "label": "Approved operational benefit baseline",
            "body": "Reviewed baseline used to verify realized avoided losses.",
            "status": "proposed",
        },
    )
    assert benefit_evidence.status_code == 201, benefit_evidence.text
    reviewed_benefit_evidence = client.patch(
        f"{graph_base}/nodes/{benefit_evidence.json()['id']}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert reviewed_benefit_evidence.status_code == 200, reviewed_benefit_evidence.text

    empty = client.get(base, headers=headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["case"]["id"] is None
    assert empty.json()["calculation_policy"] == "deterministic_server_side_no_ai"
    assert empty.json()["metrics_state"] == "unknown_not_zero"
    assert empty.json()["metrics"]["forecast_roi_pct"] is None
    assert empty.json()["governed_prefill"]["human_confirmation_required"] is True

    configured = client.put(
        base,
        headers=headers,
        json={
            "expected_revision": 0,
            "case_kind": "hybrid",
            "currency": "EUR",
            "horizon_months": 24,
            "discount_rate_pct": 8,
            "decision_context": "Decide whether the intervention should be financed and executed.",
            "baseline": "Current operation creates recurring losses and consumes untracked staff time.",
            "counterfactual": "Without action the losses, exposure and manual effort remain.",
            "planned_start_date": "2026-09-01",
            "planned_end_date": "2027-08-31",
            "forecast_end_date": "2027-09-30",
            "actual_start_date": "2026-09-03",
            "actual_end_date": None,
            "outcome_name": "Operational incidents avoided",
            "outcome_unit": "incidents",
            "planned_outcome_quantity": 50,
            "actual_outcome_quantity": 8,
            "notes": "Benefits are attributed only when their source is declared.",
        },
    )
    assert configured.status_code == 200, configured.text
    case = configured.json()["case"]
    assert case["revision"] == 1
    assert configured.json()["integrity_verified"] is True
    assert configured.json()["metrics_state"] == "unknown_not_zero"

    conflict = client.put(
        base,
        headers=headers,
        json={
            "expected_revision": 0,
            "case_kind": "hybrid",
            "currency": "EUR",
            "horizon_months": 24,
            "discount_rate_pct": 8,
        },
    )
    assert conflict.status_code == 409, conflict.text

    cost_payload = _line(expected_revision=1)
    cost = client.post(f"{base}/items", headers=headers, json=cost_payload)
    assert cost.status_code == 201, cost.text
    assert cost.json()["case"]["revision"] == 2
    assert cost.json()["metrics"]["forecast_roi_pct"] == -100.0
    no_benefit = next(
        warning
        for warning in cost.json()["warnings"]
        if warning["code"] == "no_monetary_benefit"
    )
    assert "não é calculável" not in no_benefit["message"]
    assert "apenas os custos monetários" in no_benefit["message"]

    benefit = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=2,
            kind="monetary_benefit",
            financial_treatment="benefit",
            category="avoided_cost",
            label="Avoided losses and productivity gain",
            conservative_amount=3000,
            base_amount=5000,
            favorable_amount=7000,
            committed_amount=15000,
            realized_amount=10000,
            forecast_amount=5000,
            start_month=1,
            end_month=23,
            recurrence="monthly",
            source_label="Operational baseline and approved benefit hypothesis",
            evidence_node_id=benefit_evidence.json()["id"],
            responsible="Operations director",
        ),
    )
    assert benefit.status_code == 201, benefit.text

    people = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=3,
            kind="human_resource",
            financial_treatment="none",
            category="internal_team",
            label="Internal implementation team",
            conservative_amount=None,
            base_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
            planned_quantity=420,
            actual_quantity=120,
            unit="horas",
            source_label="Approved resource plan and timesheet summary",
            include_in_totals=False,
        ),
    )
    assert people.status_code == 201, people.text
    people_id = people.json()["item_change"]["item_id"]

    funding = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=4,
            kind="financial_resource",
            financial_treatment="none",
            category="approved_funding",
            label="Approved financing envelope",
            conservative_amount=70000,
            base_amount=80000,
            favorable_amount=90000,
            committed_amount=80000,
            realized_amount=40000,
            forecast_amount=80000,
            source_label="Financing approval reference BC-2026-01",
            include_in_totals=False,
        ),
    )
    assert funding.status_code == 201, funding.text
    funding_id = funding.json()["item_change"]["item_id"]

    post_cost = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=5,
            category="maintenance",
            label="Annual post-mission maintenance",
            conservative_amount=1500,
            base_amount=1200,
            favorable_amount=900,
            committed_amount=0,
            realized_amount=0,
            forecast_amount=1200,
            phase="post_mission",
            start_month=12,
            end_month=23,
            recurrence="annual",
            source_label="Maintenance quotation MAINT-2026",
        ),
    )
    assert post_cost.status_code == 201, post_cost.text
    payload = post_cost.json()
    metrics = payload["metrics"]
    assert metrics["budget_base"] == 101200.0
    assert metrics["forecast_cost_at_completion"] == 106200.0
    assert metrics["expected_gross_benefit"] == 115000.0
    assert metrics["forecast_net_benefit"] == 8800.0
    assert metrics["forecast_payback_months"] == 22
    assert metrics["planned_human_hours"] == 420.0
    assert metrics["actual_human_hours"] == 120.0
    assert metrics["annual_post_mission_burden"] == 1200.0
    assert metrics["funding_available"] == 80000.0
    assert metrics["funding_gap"] == 26200.0
    assert metrics["schedule_variance_days"] == 30
    assert "ROI de 8,3%" in payload["executive_conclusion"]
    assert "encargo anual de 1 200 €" in payload["executive_conclusion"]
    assert metrics["evidence_linked_realized_benefit"] == 10000.0
    assert metrics["reviewed_evidence_realized_benefit"] == 10000.0
    assert metrics["verified_realized_benefit"] == 0.0
    assert metrics["unverified_realized_benefit"] == 10000.0
    assert "A missão registou 120,0 horas de trabalho" in payload["executive_conclusion"]
    assert "benefício realizado com evidência revista é 10 000 €" in payload["executive_conclusion"]
    assert "encargo anual de 1 200 €" in payload["executive_conclusion"]
    assert payload["readiness"]["ready_for_review"] is True
    assert payload["quality"]["source_coverage_pct"] == 100.0
    assert payload["metrics"]["scenarios"]["conservative"]["net_benefit"] < payload["metrics"]["scenarios"]["base"]["net_benefit"]
    assert payload["metrics"]["scenarios"]["favorable"]["net_benefit"] > payload["metrics"]["scenarios"]["base"]["net_benefit"]

    alternatives = []
    for title, body in (
        ("Automate the critical workflow", "Implement automation with controlled human review."),
        ("Redesign the manual workflow", "Reduce handoffs while retaining manual execution."),
    ):
        created = client.post(
            f"{graph_base}/nodes",
            headers=headers,
            json={
                "node_type": "alternative",
                "label": title,
                "body": body,
                "status": "proposed",
            },
        )
        assert created.status_code == 201, created.text
        alternatives.append(created.json())

    unmodelled = client.get(base, headers=headers)
    assert unmodelled.status_code == 200, unmodelled.text
    unmodelled_profiles = unmodelled.json()["alternative_comparison"]["profiles"]
    assert all(profile["metrics_state"] == "unknown_not_zero" for profile in unmodelled_profiles)

    revision = payload["case"]["revision"]
    scoped_lines = (
        _line(
            expected_revision=revision,
            alternative_node_id=alternatives[0]["id"],
            label="Automation implementation",
            base_amount=40000,
            conservative_amount=46000,
            favorable_amount=36000,
            forecast_amount=40000,
        ),
        _line(
            expected_revision=revision + 1,
            alternative_node_id=alternatives[0]["id"],
            kind="monetary_benefit",
            financial_treatment="benefit",
            label="Automation avoided cost",
            base_amount=2500,
            conservative_amount=1800,
            favorable_amount=3200,
            forecast_amount=2500,
            start_month=1,
            end_month=23,
            recurrence="monthly",
        ),
        _line(
            expected_revision=revision + 2,
            alternative_node_id=alternatives[0]["id"],
            kind="human_resource",
            financial_treatment="none",
            label="Automation delivery team",
            base_amount=None,
            conservative_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
            planned_quantity=80,
            actual_quantity=0,
            unit="horas",
            include_in_totals=False,
        ),
        _line(
            expected_revision=revision + 3,
            alternative_node_id=alternatives[1]["id"],
            label="Manual workflow redesign",
            base_amount=30000,
            conservative_amount=34000,
            favorable_amount=27000,
            forecast_amount=30000,
        ),
        _line(
            expected_revision=revision + 4,
            alternative_node_id=alternatives[1]["id"],
            kind="monetary_benefit",
            financial_treatment="benefit",
            label="Manual redesign avoided cost",
            base_amount=1500,
            conservative_amount=1000,
            favorable_amount=1900,
            forecast_amount=1500,
            start_month=1,
            end_month=23,
            recurrence="monthly",
        ),
        _line(
            expected_revision=revision + 5,
            alternative_node_id=alternatives[1]["id"],
            kind="equipment_resource",
            financial_treatment="none",
            label="Existing operational equipment",
            base_amount=None,
            conservative_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
            planned_quantity=2,
            actual_quantity=0,
            unit="unidades",
            include_in_totals=False,
        ),
    )
    alternative_payload = payload
    for line in scoped_lines:
        response = client.post(f"{base}/items", headers=headers, json=line)
        assert response.status_code == 201, response.text
        alternative_payload = response.json()

    assert alternative_payload["metrics"]["budget_base"] == metrics["budget_base"]
    assert alternative_payload["metrics"]["forecast_cost_at_completion"] == metrics["forecast_cost_at_completion"]
    comparison = alternative_payload["alternative_comparison"]
    assert comparison["profile_count"] == 2
    assert comparison["complete_profile_count"] == 2
    profiles = {row["alternative_node_id"]: row for row in comparison["profiles"]}
    assert profiles[alternatives[0]["id"]]["total_cost"] == 40000.0
    assert profiles[alternatives[0]["id"]]["probable_gross_benefit"] == 57500.0
    assert profiles[alternatives[0]["id"]]["resources"]["planned_human_hours"] == 80.0
    assert profiles[alternatives[1]["id"]]["total_cost"] == 30000.0
    assert profiles[alternatives[1]["id"]]["probable_gross_benefit"] == 34500.0
    assert profiles[alternatives[1]["id"]]["resources"]["equipment_lines"] == 1

    matrix = client.get(
        f"/api/pilot/alternative-matrices/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert matrix.status_code == 200, matrix.text
    assert matrix.json()["economic_comparison"]["complete_profile_count"] == 2
    assert matrix.json()["economic_alignment"]["status"] == "not_saved"
    payload = alternative_payload

    alternative = client.post(
        f"/api/pilot/alternative-matrices/missions/{mission_payload['code']}/alternatives",
        headers=headers,
        json={
            "title": "Phased implementation",
            "body": "Alternative with its own lifecycle cost, probable benefit and required team.",
        },
    )
    assert alternative.status_code == 200, alternative.text
    alternative_id = alternative.json()["alternative_change"]["alternative_id"]

    alternative_cost = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=payload["case"]["revision"],
            alternative_node_id=alternative_id,
            kind="material_resource",
            amount_basis="per_unit",
            planned_quantity=10,
            unit="unidades",
            label="Alternative implementation cost",
            conservative_amount=6000,
            base_amount=5000,
            favorable_amount=4500,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=5000,
        ),
    )
    assert alternative_cost.status_code == 201, alternative_cost.text
    alternative_benefit = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=alternative_cost.json()["case"]["revision"],
            alternative_node_id=alternative_id,
            kind="monetary_benefit",
            financial_treatment="benefit",
            category="alternative_value",
            label="Alternative probable benefit",
            conservative_amount=4000,
            base_amount=6000,
            favorable_amount=8000,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=6000,
            start_month=1,
            end_month=12,
            recurrence="monthly",
        ),
    )
    assert alternative_benefit.status_code == 201, alternative_benefit.text
    alternative_people = client.post(
        f"{base}/items",
        headers=headers,
        json=_line(
            expected_revision=alternative_benefit.json()["case"]["revision"],
            alternative_node_id=alternative_id,
            kind="human_resource",
            financial_treatment="none",
            category="alternative_team",
            label="Alternative implementation team",
            conservative_amount=None,
            base_amount=None,
            favorable_amount=None,
            committed_amount=None,
            realized_amount=None,
            forecast_amount=None,
            planned_quantity=80,
            actual_quantity=0,
            unit="horas",
            operational_status="blocked",
            blocker="Specialist availability is not yet confirmed.",
            include_in_totals=False,
        ),
    )
    assert alternative_people.status_code == 201, alternative_people.text
    alternative_payload = alternative_people.json()
    assert alternative_payload["metrics"] == payload["metrics"]
    alternative_profile = next(
        profile
        for profile in alternative_payload["alternative_comparison"]["profiles"]
        if profile["alternative_node_id"] == alternative_id
    )
    assert alternative_profile["complete"] is True
    assert alternative_profile["total_cost"] == 50000.0
    assert alternative_profile["probable_gross_benefit"] == 72000.0
    assert alternative_profile["probable_net_benefit"] == 22000.0
    assert alternative_profile["roi_pct"] == 44.0
    assert alternative_profile["resources"]["planned_human_hours"] == 80.0
    assert alternative_profile["resources"]["material_lines"] == 1
    assert alternative_profile["resources"]["blocked_lines"] == 1
    payload = alternative_payload

    reviewed = client.post(
        f"{base}/review",
        headers=headers,
        json={
            "expected_revision": payload["case"]["revision"],
            "rationale": "The horizon, sources, scenarios and non-monetized outcomes are adequate for this decision.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["case"]["status"] == "reviewed"
    assert reviewed.json()["integrity_verified"] is True
    reviewed_revision = reviewed.json()["case"]["revision"]

    readiness = client.get(
        f"/api/pilot/missions/{mission_payload['code']}/completion-readiness",
        headers=headers,
    )
    assert readiness.status_code == 200, readiness.text
    business_checks = {
        row["key"]: row
        for row in readiness.json()["checks"]
        if row["key"].startswith("business_case_")
    }
    assert business_checks["business_case_structured"]["passed"] is True
    assert business_checks["business_case_reviewed"]["passed"] is True

    updated_people = client.patch(
        f"{base}/items/{people_id}",
        headers=headers,
        json={"expected_revision": reviewed_revision, "actual_quantity": 200},
    )
    assert updated_people.status_code == 200, updated_people.text
    assert updated_people.json()["metrics"]["actual_human_hours"] == 200.0
    assert updated_people.json()["case"]["status"] == "active"
    assert updated_people.json()["readiness"]["reviewed"] is False

    stale_retirement = client.delete(
        f"{base}/items/{funding_id}?expected_revision={reviewed_revision}",
        headers=headers,
    )
    assert stale_retirement.status_code == 409, stale_retirement.text

    retired = client.delete(
        f"{base}/items/{funding_id}?expected_revision={updated_people.json()['case']['revision']}",
        headers=headers,
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["metrics"]["funding_available"] == 0.0
    assert retired.json()["metrics"]["funding_gap"] == 106200.0
    assert len(retired.json()["history"]) == retired.json()["case"]["revision"]
    assert retired.json()["history"][0]["event_type"] == "item_retired"

    audit = client.get("/api/pilot/admin/audit?limit=100", headers=headers)
    assert audit.status_code == 200, audit.text
    actions = {row["action"] for row in audit.json()["events"]}
    assert "pilot.business_case.case_created" in actions
    assert "pilot.business_case.item_created" in actions
    assert "pilot.business_case.reviewed" in actions
    assert "pilot.business_case.item_updated" in actions
    assert "pilot.business_case.item_retired" in actions


def test_financial_plan_v31_rows_do_not_inherit_unsubstantiated_headline_returns() -> None:
    """The supplied five-year rows must stand on their own, independent of a claimed 10-year ROI."""

    case = {
        "case_kind": "commercial",
        "currency": "EUR",
        "horizon_months": 60,
        "discount_rate_pct": 8,
        "planned_outcome_quantity": None,
        "actual_outcome_quantity": None,
    }

    def row(label: str, treatment: str, amount: float, month: int) -> dict:
        return {
            "label": label,
            "kind": "monetary_cost" if treatment == "cost" else "monetary_benefit",
            "financial_treatment": treatment,
            "include_in_totals": True,
            "base_amount": amount,
            "conservative_amount": amount,
            "favorable_amount": amount,
            "forecast_amount": amount,
            "committed_amount": None,
            "realized_amount": None,
            "planned_quantity": None,
            "actual_quantity": None,
            "unit": "EUR",
            "start_month": month,
            "end_month": None,
            "recurrence": "one_off",
            "phase": "execution",
            "evidence_node_id": None,
        }

    items = [row("Total project investment", "cost", 972500, 0)]
    items.extend(
        row(f"OPEX year {year}", "cost", amount, (year - 1) * 12)
        for year, amount in enumerate((333500, 359700, 427000, 450100, 474800), start=1)
    )
    items.extend(
        row(f"Revenue year {year}", "benefit", amount, (year - 1) * 12)
        for year, amount in enumerate((357620, 470000, 547420, 595000, 620000), start=1)
    )

    metrics = _live_metrics(case, items)
    base = metrics["scenarios"]["base"]
    assert base["total_cost"] == 3017600.0
    assert base["gross_benefit"] == 2590040.0
    assert base["net_benefit"] == -427560.0
    assert base["roi_pct"] == -14.17
    assert base["payback_months"] is None
    assert base["npv"] < 0
