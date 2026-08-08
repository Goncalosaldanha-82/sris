import pytest

from app.core.encryption import encryption


pytestmark = pytest.mark.skip(
    reason=(
        "Legacy SRIS v0.9 specification: its /api/v1 domain application and fixtures "
        "were disconnected when production was consolidated on ATLAS Core."
    )
)


def human_provenance(actor="Técnico responsável", method="Revisão documentada"):
    return {
        "origin_type": "human",
        "origin_actor": actor,
        "acquisition_type": "document",
        "method_or_modality": method,
        "limitations": "A proveniência identifica a origem, mas não valida por si só o conteúdo.",
        "verification_status": "declared",
    }

def ai_provenance(model="Example Model", version="2026-07"):
    return {
        "origin_type": "ai_model",
        "origin_actor": "Agente de análise",
        "acquisition_type": "generated",
        "method_or_modality": "Inferência assistida por modelo",
        "model_or_system": model,
        "version": version,
        "input_context_reference": "run://test/001",
        "limitations": "Saída de modelo sujeita a erro e verificação independente.",
        "verification_status": "in_review",
    }


def mission(client, auth, code="M-1", name="Mission"):
    return client.post("/api/v1/missions", headers=auth, json={"code": code, "name": name}).json()


def investigation(client, auth, mission_id, title="Question"):
    return client.post(
        "/api/v1/investigations",
        headers=auth,
        json={
            "mission_id": mission_id,
            "title": title,
            "question": "Porque aconteceu?",
            "limitations": "Pergunta inicial; não estabelece causalidade.",
        },
    ).json()


def test_login_and_me(client, auth):
    r = client.get("/api/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "admin@example.com"


def test_tenant_isolation(client, auth, reset):
    r = client.post("/api/v1/missions", headers=auth, json={"code": "M-1", "name": "Private"})
    assert r.status_code == 200
    bad = {**auth, "X-Organization-ID": reset["org2"].id}
    assert client.get("/api/v1/missions", headers=bad).status_code == 403


def test_normalized_posteriors_compete_and_sum_to_one(client, auth):
    m = mission(client, auth)
    inv = investigation(client, auth, m["id"])
    h1 = client.post(
        "/api/v1/hypotheses",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "statement": "Eucaliptal é a causa dominante",
            "prior": 0.5,
            "limitations": "Hipótese concorrente ainda não testada.",
        },
    ).json()
    h2 = client.post(
        "/api/v1/hypotheses",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "statement": "Seca é a causa dominante",
            "prior": 0.3,
            "limitations": "Hipótese concorrente ainda não testada.",
        },
    ).json()
    r = client.post(
        "/api/v1/evidence",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "hypothesis_id": h1["id"],
            "title": "Literatura dirigida",
            "source": "Artigo técnico",
            "method": "Revisão dirigida",
            "provenance": human_provenance(method="Revisão dirigida"),
            "limitations": "Contexto edafoclimático diferente.",
            "weight": 0.8,
            "direction": "supports",
        },
    )
    assert r.status_code == 200
    data = client.get(f"/api/v1/investigations/{inv['id']}/posteriors", headers=auth).json()
    assert abs(data["sum"] - 1.0) < 1e-10
    probs = {row["id"]: row["posterior"] for row in data["hypotheses"]}
    assert probs[h1["id"]] > probs[h2["id"]] > 0


def test_information_value_ranks_discriminating_evidence(client, auth):
    m = mission(client, auth, "M-VOI")
    inv = investigation(client, auth, m["id"], "Distinguish")
    h1 = client.post(
        "/api/v1/hypotheses",
        headers=auth,
        json={"investigation_id": inv["id"], "statement": "H1", "prior": 0.5, "limitations": "Em teste."},
    ).json()
    h2 = client.post(
        "/api/v1/hypotheses",
        headers=auth,
        json={"investigation_id": inv["id"], "statement": "H2", "prior": 0.5, "limitations": "Em teste."},
    ).json()
    strong = client.post(
        "/api/v1/evidence-proposals",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "title": "Teste discriminante",
            "expected_effects": {h1["id"]: 1, h2["id"]: -1},
            "weight": 0.9,
            "estimated_cost": 100,
            "estimated_days": 2,
            "risk_level": "low",
            "feasibility": "high",
            "limitations": "Efeitos esperados ainda são pressupostos de desenho.",
        },
    )
    assert strong.status_code == 200
    weak = client.post(
        "/api/v1/evidence-proposals",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "title": "Teste pouco discriminante",
            "expected_effects": {h1["id"]: 0.1, h2["id"]: 0.1},
            "weight": 0.2,
            "estimated_cost": 1000,
            "estimated_days": 30,
            "risk_level": "medium",
            "feasibility": "medium",
            "limitations": "Pouco poder discriminante esperado.",
        },
    )
    assert weak.status_code == 200
    rows = client.get(f"/api/v1/investigations/{inv['id']}/information-value", headers=auth).json()["proposals"]
    assert rows[0]["title"] == "Teste discriminante"
    assert rows[0]["expected_information_gain_kl"] > rows[1]["expected_information_gain_kl"]


def test_required_limitations_are_rejected_with_useful_message(client, auth):
    m = mission(client, auth, "M-VAL")
    r = client.post(
        "/api/v1/observations",
        headers=auth,
        json={"mission_id": m["id"], "title": "Leitura", "method": "Observação direta", "limitations": ""},
    )
    assert r.status_code == 422
    assert "limitação declarada é obrigatória" in r.text.lower()


def test_encryption(reset):
    x = encryption.encrypt(reset["org1"].id, "secret")
    assert x != "secret"
    assert encryption.decrypt(reset["org1"].id, x) == "secret"


def test_first_class_epistemic_objects_and_refutation(client, auth):
    m = mission(client, auth, "M-2", "Traceability")
    inv = investigation(client, auth, m["id"])
    d = client.post(
        "/api/v1/decisions",
        headers=auth,
        json={"mission_id": m["id"], "investigation_id": inv["id"], "title": "Act", "rationale": "Because"},
    ).json()
    a = client.post(
        "/api/v1/assumptions",
        headers=auth,
        json={
            "mission_id": m["id"],
            "investigation_id": inv["id"],
            "decision_id": d["id"],
            "statement": "Historical flow existed",
            "method": "Testemunho",
            "limitations": "Sem registo contemporâneo.",
        },
    ).json()
    h = client.post(
        "/api/v1/hypotheses",
        headers=auth,
        json={"investigation_id": inv["id"], "statement": "Hypothesis", "limitations": "Ainda não testada."},
    ).json()
    e = client.post(
        "/api/v1/evidence",
        headers=auth,
        json={
            "investigation_id": inv["id"],
            "hypothesis_id": h["id"],
            "title": "Archive",
            "source": "Arquivo",
            "method": "Recuperação documental",
            "provenance": human_provenance(method="Recuperação documental"),
            "limitations": "Método original desconhecido.",
            "direction": "supports",
            "weight": 0.8,
        },
    ).json()
    r = client.post(f"/api/v1/evidence/{e['id']}/refutes/assumptions/{a['id']}", headers=auth)
    assert r.status_code == 200 and r.json()["assumption"]["status"] == "refuted"
    rels = client.get("/api/v1/relations", headers=auth).json()
    assert any(x["relation_type"] == "refutes" and x["target_id"] == a["id"] for x in rels)


def test_attribution_assessment_is_reconstructible(client, auth):
    m = mission(client, auth, "M-3", "Attribution")
    inv = investigation(client, auth, m["id"])
    d = client.post(
        "/api/v1/decisions",
        headers=auth,
        json={"mission_id": m["id"], "investigation_id": inv["id"], "title": "Decision", "rationale": "Test"},
    ).json()
    client.post(
        "/api/v1/assumptions",
        headers=auth,
        json={
            "mission_id": m["id"],
            "decision_id": d["id"],
            "statement": "Assumed",
            "status": "refuted",
            "method": "Declaração do decisor",
            "limitations": "Sem verificação independente.",
        },
    )
    act = client.post("/api/v1/actions", headers=auth, json={"decision_id": d["id"], "title": "Execute"}).json()
    out = client.post(
        "/api/v1/outcomes",
        headers=auth,
        json={
            "action_id": act["id"],
            "observed": "Changed",
            "baseline": {},
            "measured": {"external_variables": ["rain"]},
            "limitations": "Medição única sem controlo.",
        },
    ).json()
    a = client.post(f"/api/v1/outcomes/{out['id']}/attribution", headers=auth, json={})
    assert a.status_code == 200
    data = a.json()
    assert data["status"] == "not_supported"
    assert data["penalty"] >= 0.55
    assert data["reasons"]


def test_constraint_status_has_explicit_contract(client, auth):
    m = mission(client, auth, "M-C")
    c = client.post(
        "/api/v1/constraints",
        headers=auth,
        json={
            "mission_id": m["id"],
            "statement": "Prazo máximo",
            "source": "Contrato",
            "limitations": "Interpretação jurídica não validada.",
        },
    ).json()
    missing_reason = client.post(f"/api/v1/constraints/{c['id']}/status", headers=auth, json={"status": "violated", "reason": ""})
    assert missing_reason.status_code == 422
    ok = client.post(f"/api/v1/constraints/{c['id']}/status", headers=auth, json={"status": "violated", "reason": "Prazo ultrapassado"})
    assert ok.status_code == 200 and ok.json()["status"] == "violated"


def test_reasoning_audit_detects_missing_alternatives(client, auth):
    m = mission(client, auth, "M-4", "Audit")
    inv = investigation(client, auth, m["id"])
    d = client.post(
        "/api/v1/decisions",
        headers=auth,
        json={"mission_id": m["id"], "investigation_id": inv["id"], "title": "Decision", "rationale": "Test"},
    ).json()
    gaps = client.get("/api/v1/reasoning-audit", headers=auth, params={"mission_id": m["id"]}).json()
    assert any(x["rule"] == "DEC_NO_ALT" and x["ref"] == d["id"] for x in gaps)


def test_graph_includes_assumptions_and_observations(client, auth):
    m = mission(client, auth, "M-5", "Graph")
    client.post(
        "/api/v1/observations",
        headers=auth,
        json={
            "mission_id": m["id"],
            "title": "Observed",
            "method": "Observação direta",
            "limitations": "Single reading",
        },
    )
    client.post(
        "/api/v1/assumptions",
        headers=auth,
        json={
            "mission_id": m["id"],
            "statement": "Assumed",
            "method": "Declaração",
            "limitations": "Sem teste independente.",
        },
    )
    g = client.get("/api/v1/graph", headers=auth, params={"mission_id": m["id"]}).json()
    kinds = {x["type"] for x in g["nodes"]}
    assert "observation" in kinds and "assumption" in kinds


def test_opportunity_public_api_is_retired(client, auth):
    r = client.get("/api/v1/opportunities", headers=auth)
    assert r.status_code == 410
    assert "retirado" in r.json()["detail"].lower()


def test_outcome_contract_explains_missing_observed(client, auth):
    r = client.post('/api/v1/outcomes', headers=auth, json={'action_id':'missing','limitations':'Teste incompleto.'})
    assert r.status_code == 422
    body = r.json()
    assert body['detail'] == 'O pedido contém campos inválidos ou incompletos.'
    assert any(x['field'] == 'observed' for x in body['errors'])


def test_frontend_and_openapi_are_served(client):
    index = client.get('/')
    assert index.status_code == 200 and 'Compreender antes de decidir' in index.text
    spec = client.get('/api/openapi.json')
    assert spec.status_code == 200
    assert '/api/v1/investigations/{investigation_id}/information-value' in spec.json()['paths']
    assert '/api/v1/opportunities' not in spec.json()['paths']


def test_workspace_exposes_normalized_posteriors_and_information_value(client, auth):
    m = mission(client, auth, 'M-WORK')
    inv = investigation(client, auth, m['id'])
    client.post('/api/v1/hypotheses', headers=auth, json={'investigation_id':inv['id'],'statement':'H1','prior':0.6,'limitations':'Em teste.'})
    client.post('/api/v1/hypotheses', headers=auth, json={'investigation_id':inv['id'],'statement':'H2','prior':0.4,'limitations':'Em teste.'})
    w = client.get(f"/api/v1/workspace/{m['id']}", headers=auth)
    assert w.status_code == 200
    data = w.json()
    assert abs(data['posteriors'][0]['sum'] - 1.0) < 1e-10
    assert data['information_value'][0]['algorithm_version'] == 'voi-kl-1'


def test_experience_entry_and_guidance(client, auth):
    m = mission(client, auth, "M-EXP", "Experience")
    entry = client.get(f"/api/v1/experience/missions/{m['id']}/entry", headers=auth)
    assert entry.status_code == 200
    data = entry.json()
    assert data["mission"]["code"] == "M-EXP"
    assert data["available_intentions"] == ["understand", "investigate", "decide", "review", "learn"]
    guidance = client.get(f"/api/v1/experience/missions/{m['id']}/guidance/investigate", headers=auth)
    assert guidance.status_code == 200
    assert guidance.json()["questions"][0]["id"] == "INV.Q.001"


def test_experience_impact_follows_refutation_chain(client, auth):
    m = mission(client, auth, "M-IMPACT", "Impact")
    inv = investigation(client, auth, m["id"])
    d = client.post(
        "/api/v1/decisions", headers=auth,
        json={"mission_id": m["id"], "investigation_id": inv["id"], "title": "Decision", "rationale": "Reason"},
    ).json()
    a = client.post(
        "/api/v1/assumptions", headers=auth,
        json={"mission_id": m["id"], "investigation_id": inv["id"], "decision_id": d["id"], "statement": "Assumption", "method": "Declared", "limitations": "Untested"},
    ).json()
    h = client.post(
        "/api/v1/hypotheses", headers=auth,
        json={"investigation_id": inv["id"], "statement": "Hypothesis", "limitations": "Untested"},
    ).json()
    e = client.post(
        "/api/v1/evidence", headers=auth,
        json={"investigation_id": inv["id"], "hypothesis_id": h["id"], "title": "Archive", "source": "Archive", "method": "Review", "provenance": human_provenance(method="Review"), "limitations": "Partial", "direction": "supports", "weight": .8},
    ).json()
    client.post(f"/api/v1/evidence/{e['id']}/refutes/assumptions/{a['id']}", headers=auth)
    impact = client.get(f"/api/v1/experience/missions/{m['id']}/impact/{e['id']}", headers=auth)
    assert impact.status_code == 200
    assert any(edge["type"] == "refutes" and edge["target"] == a["id"] for edge in impact.json()["edges"])


def test_experience_timeline_and_focus_are_mission_scoped(client, auth):
    m1 = mission(client, auth, "M-T1", "Timeline One")
    m2 = mission(client, auth, "M-T2", "Timeline Two")
    o = client.post(
        "/api/v1/observations", headers=auth,
        json={"mission_id": m1["id"], "title": "Observed", "method": "Direct", "limitations": "Single observation"},
    ).json()
    timeline = client.get(f"/api/v1/experience/missions/{m1['id']}/timeline", headers=auth)
    assert timeline.status_code == 200
    assert any(moment["object_id"] == o["id"] for moment in timeline.json()["moments"])
    focus = client.get(f"/api/v1/experience/missions/{m1['id']}/focus/observation/{o['id']}", headers=auth)
    assert focus.status_code == 200
    wrong = client.get(f"/api/v1/experience/missions/{m2['id']}/focus/observation/{o['id']}", headers=auth)
    assert wrong.status_code == 404


def test_frontend_boot_contract_matches_auth_me(client, auth):
    me = client.get('/api/auth/me', headers=auth)
    assert me.status_code == 200
    payload = me.json()
    assert isinstance(payload.get('user'), dict)
    assert payload['user'].get('email')
    assert isinstance(payload.get('memberships'), list)
    assert payload['memberships'][0].get('organization_id')

    index = client.get('/')
    assert index.status_code == 200
    assert 'assets/contracts.js' in index.text
    assert 'assets/app.js' in index.text
    contracts = client.get('/assets/contracts.js')
    assert contracts.status_code == 200
    assert 'normalizeMe' in contracts.text


def test_guided_reasoning_session_persists_and_completes(client, auth):
    m=mission(client,auth,"M-GUIDED","Guided")
    created=client.post(f"/api/v1/experience/missions/{m['id']}/guided-sessions",headers=auth,json={"intention":"understand"})
    assert created.status_code==200
    data=created.json(); sid=data["id"]
    assert data["status"]=="active" and data["current_question"]
    for q in data["questions"]:
        r=client.post(f"/api/v1/experience/guided-sessions/{sid}/answers",headers=auth,json={"question_id":q["id"],"answer":"Resposta de teste com contexto."})
        assert r.status_code==200
        data=r.json()
    assert data["status"]=="awaiting_confirmation"
    assert data["preview_objects"]
    assert len(data["answers"])==len(data["questions"])
    confirmed=client.post(f"/api/v1/experience/guided-sessions/{sid}/confirm",headers=auth)
    assert confirmed.status_code==200
    data=confirmed.json()
    assert data["status"]=="completed"
    fetched=client.get(f"/api/v1/experience/guided-sessions/{sid}",headers=auth).json()
    assert fetched["status"]=="completed"

def test_guided_reasoning_rejects_wrong_question(client, auth):
    m=mission(client,auth,"M-GUIDED-2","Guided")
    data=client.post(f"/api/v1/experience/missions/{m['id']}/guided-sessions",headers=auth,json={"intention":"review"}).json()
    r=client.post(f"/api/v1/experience/guided-sessions/{data['id']}/answers",headers=auth,json={"question_id":"WRONG","answer":"Teste"})
    assert r.status_code==409


def _complete_guided(client, auth, mission_id, intention, answers):
    data = client.post(
        f"/api/v1/experience/missions/{mission_id}/guided-sessions",
        headers=auth, json={"intention": intention},
    ).json()
    for question, answer in zip(data["questions"], answers):
        response = client.post(
            f"/api/v1/experience/guided-sessions/{data['id']}/answers",
            headers=auth, json={"question_id": question["id"], "answer": answer},
        )
        assert response.status_code == 200
        data = response.json()
    assert data["status"] == "awaiting_confirmation"
    confirm = client.post(
        f"/api/v1/experience/guided-sessions/{data['id']}/confirm",
        headers=auth,
    )
    assert confirm.status_code == 200
    return confirm.json()


def test_guided_understand_materializes_observation(client, auth):
    m = mission(client, auth, "M-MAT-OBS", "Materialize observation")
    data = _complete_guided(client, auth, m["id"], "understand", [
        "A regeneração natural aumentou na parcela norte.",
        "Observação direta com registo fotográfico.",
        "Uma observação isolada não permite atribuir causalidade.",
    ])
    assert data["status"] == "completed"
    created = data["materialized_objects"]
    assert any(x["type"] == "observation" for x in created)
    rows = client.get("/api/v1/observations", headers=auth).json()
    row = next(x for x in rows if x["id"] == next(y["id"] for y in created if y["type"] == "observation"))
    assert row["mission_id"] == m["id"]
    assert "causalidade" in row["limitations"]


def test_guided_investigate_materializes_investigation_hypotheses_and_proposal(client, auth):
    m = mission(client, auth, "M-MAT-INV", "Materialize investigation")
    data = _complete_guided(client, auth, m["id"], "investigate", [
        "Porque aumentou a mortalidade?",
        "Seca prolongada; Praga localizada",
        "Amostragem independente de solo e fitossanidade.",
    ])
    kinds = [x["type"] for x in data["materialized_objects"]]
    assert kinds.count("investigation") == 1
    assert kinds.count("hypothesis") == 2
    assert kinds.count("evidence_proposal") == 1
    inv_id = next(x["id"] for x in data["materialized_objects"] if x["type"] == "investigation")
    posterior = client.get(f"/api/v1/investigations/{inv_id}/posteriors", headers=auth).json()
    assert abs(posterior["sum"] - 1.0) < 1e-10


def test_guided_decide_materializes_decision_and_alternatives(client, auth):
    m = mission(client, auth, "M-MAT-DEC", "Materialize decision")
    data = _complete_guided(client, auth, m["id"], "decide", [
        "Adotar conversão progressiva em mosaico.",
        "Não intervir; Conversão total; Conversão progressiva",
        "Rever se a regeneração ficar abaixo do limiar durante dois ciclos.",
    ])
    kinds = [x["type"] for x in data["materialized_objects"]]
    assert kinds.count("decision") == 1
    assert kinds.count("alternative") == 3
    decision_id = next(x["id"] for x in data["materialized_objects"] if x["type"] == "decision")
    gaps = client.get("/api/v1/reasoning-audit", headers=auth, params={"mission_id": m["id"]}).json()
    assert not any(x["rule"] == "DEC_NO_ALT" and x["ref"] == decision_id for x in gaps)


def test_guided_completion_is_idempotent_on_fetch(client, auth):
    m = mission(client, auth, "M-MAT-IDEMP", "Materialize once")
    data = _complete_guided(client, auth, m["id"], "learn", [
        "A monitorização mensal revelou sinais úteis.",
        "Não demonstrou causalidade nem transferência universal.",
        "Apenas em contextos com método e baseline comparáveis.",
    ])
    created = data["materialized_objects"]
    fetched = client.get(f"/api/v1/experience/guided-sessions/{data['id']}", headers=auth).json()
    assert fetched["materialized_objects"] == created
    rows = client.get("/api/v1/learnings", headers=auth).json()
    assert sum(1 for x in rows if x["id"] == created[0]["id"]) == 1



def test_guided_preview_can_be_edited_before_confirmation(client, auth):
    m = mission(client, auth, "M-GUIDED-EDIT", "Guided edit")
    data = client.post(
        f"/api/v1/experience/missions/{m['id']}/guided-sessions",
        headers=auth, json={"intention": "understand"},
    ).json()
    original = [
        "A mortalidade aumentou.",
        "Observação direta.",
        "Sem baseline comparável.",
    ]
    for question, answer in zip(data["questions"], original):
        data = client.post(
            f"/api/v1/experience/guided-sessions/{data['id']}/answers",
            headers=auth, json={"question_id": question["id"], "answer": answer},
        ).json()
    assert data["status"] == "awaiting_confirmation"
    assert data["materialized_objects"] == []
    assert data["preview_objects"][0]["title"] == "A mortalidade aumentou."

    updated = client.patch(
        f"/api/v1/experience/guided-sessions/{data['id']}/answers/UND.OBS.001",
        headers=auth, json={"answer": "A mortalidade aumentou apenas na parcela sul."},
    )
    assert updated.status_code == 200
    assert updated.json()["preview_objects"][0]["title"] == "A mortalidade aumentou apenas na parcela sul."

    confirmed = client.post(
        f"/api/v1/experience/guided-sessions/{data['id']}/confirm", headers=auth,
    )
    assert confirmed.status_code == 200
    created = confirmed.json()["materialized_objects"]
    observation_id = next(x["id"] for x in created if x["type"] == "observation")
    observation = next(x for x in client.get("/api/v1/observations", headers=auth).json() if x["id"] == observation_id)
    assert observation["title"] == "A mortalidade aumentou apenas na parcela sul."


def test_guided_confirm_is_idempotent(client, auth):
    m = mission(client, auth, "M-GUIDED-CONFIRM", "Guided confirm")
    data = _complete_guided(client, auth, m["id"], "learn", [
        "A observação mensal foi útil.",
        "Não demonstra causalidade.",
        "Apenas com contexto equivalente.",
    ])
    first = data["materialized_objects"]
    second = client.post(
        f"/api/v1/experience/guided-sessions/{data['id']}/confirm", headers=auth,
    )
    assert second.status_code == 200
    assert second.json()["materialized_objects"] == first

def test_experience_snapshot_keeps_entry_map_and_timeline_coherent(client, auth):
    m = mission(client, auth, "M-SNAPSHOT", "Snapshot coherence")
    observation = client.post(
        "/api/v1/observations", headers=auth,
        json={
            "mission_id": m["id"],
            "title": "Nova observação visível",
            "method": "Observação direta",
            "limitations": "Registo único sem comparação longitudinal.",
        },
    ).json()
    response = client.get(f"/api/v1/experience/missions/{m['id']}/snapshot", headers=auth)
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["entry"]["mission"]["id"] == m["id"]
    assert any(node["id"] == observation["id"] for node in snapshot["map"]["nodes"])
    assert any(moment["object_id"] == observation["id"] for moment in snapshot["timeline"]["moments"])
    assert snapshot["generated_at"]


def test_guided_completion_returns_fresh_experience_snapshot(client, auth):
    m = mission(client, auth, "M-LIVE", "Live projection refresh")
    data = _complete_guided(client, auth, m["id"], "understand", [
        "Foi observada regeneração natural na parcela sul.",
        "Observação direta com registo fotográfico datado.",
        "Não permite atribuir a regeneração à intervenção sem baseline.",
    ])
    assert data["status"] == "completed"
    assert "experience_snapshot" in data
    created_id = next(x["id"] for x in data["materialized_objects"] if x["type"] == "observation")
    snapshot = data["experience_snapshot"]
    assert any(node["id"] == created_id for node in snapshot["map"]["nodes"])
    assert any(moment["object_id"] == created_id for moment in snapshot["timeline"]["moments"])


def test_decision_workspace_is_explainable_and_tenant_scoped(client, auth):
    m = mission(client, auth, "M-DW", "Decision workspace")
    data = _complete_guided(client, auth, m["id"], "decide", [
        "Adotar conversão progressiva em mosaico.",
        "Não intervir; Conversão total; Conversão progressiva",
        "Rever se a regeneração ficar abaixo do limiar durante dois ciclos.",
    ])
    decision_id = next(x["id"] for x in data["materialized_objects"] if x["type"] == "decision")
    response = client.get(f"/api/v1/experience/missions/{m['id']}/decisions/{decision_id}/workspace", headers=auth)
    assert response.status_code == 200
    workspace = response.json()
    assert workspace["decision"]["id"] == decision_id
    assert workspace["confidence"]["algorithm_version"] == "decision-support-0.8"
    assert workspace["confidence"]["meaning"].startswith("Grau de sustentação")
    assert len(workspace["confidence"]["factors"]) == 5
    assert len(workspace["alternatives"]) == 3
    assert workspace["review"]["required"] is False


def test_decision_workspace_rejects_wrong_mission(client, auth):
    m1 = mission(client, auth, "M-DW-A", "Decision A")
    m2 = mission(client, auth, "M-DW-B", "Decision B")
    data = _complete_guided(client, auth, m1["id"], "decide", [
        "Decidir A.", "Alternativa A; Alternativa B", "Rever com nova evidência."
    ])
    decision_id = next(x["id"] for x in data["materialized_objects"] if x["type"] == "decision")
    response = client.get(f"/api/v1/experience/missions/{m2['id']}/decisions/{decision_id}/workspace", headers=auth)
    assert response.status_code == 404


def test_provenance_object_is_created_atomically_with_evidence(client, auth):
    m = mission(client, auth, "M-PROV", "Provenance")
    inv = investigation(client, auth, m["id"])
    h = client.post("/api/v1/hypotheses", headers=auth, json={"investigation_id": inv["id"], "statement": "Hipótese", "limitations": "Ainda não testada."}).json()
    response = client.post("/api/v1/evidence", headers=auth, json={
        "investigation_id": inv["id"], "hypothesis_id": h["id"],
        "title": "Análise assistida", "source": "Execução de modelo", "method": "Análise comparativa",
        "limitations": "A saída requer confirmação independente.", "direction": "supports", "weight": .6,
        "provenance": ai_provenance("SRIS Analysis Model", "1.0.0"),
    })
    assert response.status_code == 200
    evidence = response.json()
    assert evidence["provenance_id"]
    rows = client.get("/api/v1/provenance", headers=auth).json()
    provenance = next(row for row in rows if row["id"] == evidence["provenance_id"])
    assert provenance["origin_type"] == "ai_model"
    assert provenance["model_or_system"] == "SRIS Analysis Model"
    assert provenance["version"] == "1.0.0"
    assert provenance["verification_status"] == "in_review"

def test_non_human_provenance_requires_model_and_version(client, auth):
    m = mission(client, auth, "M-PROV-VAL", "Provenance validation")
    inv = investigation(client, auth, m["id"])
    response = client.post("/api/v1/evidence", headers=auth, json={
        "investigation_id": inv["id"], "title": "Saída sem versão", "source": "Modelo desconhecido",
        "method": "Inferência", "limitations": "Não verificada.",
        "provenance": {
            "origin_type": "ai_model", "acquisition_type": "generated",
            "method_or_modality": "Inferência", "limitations": "Modelo e versão não declarados."
        },
    })
    assert response.status_code == 422
    assert "model_or_system e version" in response.text

def test_reasoning_audit_flags_legacy_evidence_without_provenance(client, auth, reset):
    m = mission(client, auth, "M-PROV-AUD", "Provenance audit")
    inv = investigation(client, auth, m["id"])
    db = __import__("app.core.db", fromlist=["SessionLocal"]).SessionLocal()
    from app.models.models import Evidence
    row = Evidence(organization_id=reset["org1"].id, investigation_id=inv["id"], title="Legacy", source="Legacy import", method="Unknown", limitations="Imported legacy record.")
    db.add(row); db.commit(); legacy_id=row.id; db.close()
    gaps = client.get("/api/v1/reasoning-audit", headers=auth, params={"mission_id": m["id"]}).json()
    assert any(gap["rule"] == "EVD_NO_PROVENANCE" and gap["ref"] == legacy_id for gap in gaps)

def test_provenance_is_tenant_scoped(client, auth, reset):
    response = client.post("/api/v1/provenance", headers=auth, json=human_provenance())
    assert response.status_code == 200
    bad = {**auth, "X-Organization-ID": reset["org2"].id}
    assert client.get("/api/v1/provenance", headers=bad).status_code == 403
