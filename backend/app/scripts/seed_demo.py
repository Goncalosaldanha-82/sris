"""Create a complete demonstration mission for an existing organization.

Usage:
  python -m app.scripts.seed_demo --organization-slug demo-organization
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.core.db import Base, SessionLocal, engine
from app.models.models import (
    Action, Alternative, Assumption, Constraint, Decision, Evidence,
    EvidenceProposal, Hypothesis, Implementation, Investigation, Learning,
    Mission, Observation, Organization, Outcome, Relation,
)
from app.services.confidence import recalculate_investigation_posteriors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-slug", required=True)
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=args.organization_slug).first()
        if not org:
            raise SystemExit(f"Organização não encontrada: {args.organization_slug}")
        existing = db.query(Mission).filter_by(organization_id=org.id, code="M-001").first()
        if existing:
            print(f"Demonstração já existe: {existing.id}")
            return

        m = Mission(
            organization_id=org.id,
            code="M-001",
            name="Conversão de povoamento em mosaico",
            objective="Avaliar a decisão florestal e a sustentação da atribuição do resultado observado.",
        )
        db.add(m); db.flush()
        inv = Investigation(
            organization_id=org.id,
            mission_id=m.id,
            title="Recuperação do caudal da nascente",
            question="Que explicação é mais consistente com a alteração observada no caudal?",
            limitations="Caso demonstrativo; não constitui validação científica nem atribuição causal.",
        )
        db.add(inv); db.flush()

        obs = Observation(
            organization_id=org.id,
            mission_id=m.id,
            investigation_id=inv.id,
            code="OBS-001",
            title="Nascente sem caudal em março",
            source="Observação direta",
            method="Registo de campo e fotografia",
            limitations="Sem série instrumental anterior; uma observação isolada.",
        )
        db.add(obs); db.flush()

        h1 = Hypothesis(
            organization_id=org.id,
            investigation_id=inv.id,
            statement="O povoamento denso é a causa dominante",
            prior=0.4,
            limitations="Não distingue efeitos do povoamento de variáveis climáticas e geológicas.",
        )
        h2 = Hypothesis(
            organization_id=org.id,
            investigation_id=inv.id,
            statement="O défice pluviométrico regional é a causa dominante",
            prior=0.3,
            limitations="Não explica isoladamente a magnitude local observada.",
        )
        h3 = Hypothesis(
            organization_id=org.id,
            investigation_id=inv.id,
            statement="Existe um efeito combinado entre povoamento e seca",
            prior=0.3,
            limitations="Hipótese mais abrangente e, por isso, mais difícil de refutar.",
        )
        db.add_all([h1,h2,h3]); db.flush()

        p1 = Provenance(organization_id=org.id, origin_type="system", origin_actor="Serviço climatológico", acquisition_type="api", source_reference="Série climatológica oficial", method_or_modality="Comparação com normal climatológica", model_or_system="Climatological Data Service", version="2026.1", limitations="Estação de referência afastada da parcela.", verification_status="confirmed")
        p2 = Provenance(organization_id=org.id, origin_type="human", origin_actor="Equipa de campo", acquisition_type="direct_observation", source_reference="Medição comparativa", method_or_modality="Comparação pontual com bacia vizinha", limitations="Existe apenas uma bacia de controlo e uma medição.", verification_status="declared")
        p3 = Provenance(organization_id=org.id, origin_type="human", origin_actor="Equipa técnica", acquisition_type="direct_observation", source_reference="Análise integrada de campo", method_or_modality="Triangulação entre observação, clima e povoamento", limitations="Não existe desenho experimental que isole os mecanismos.", verification_status="in_review")
        db.add_all([p1,p2,p3]); db.flush()

        e1 = Evidence(
            organization_id=org.id,
            investigation_id=inv.id,
            observation_id=obs.id,
            hypothesis_id=h2.id,
            provenance_id=p1.id,
            direction="supports",
            title="Precipitação anual abaixo da normal",
            source="Série climatológica oficial",
            method="Comparação com normal climatológica",
            limitations="Estação de referência afastada da parcela.",
            weight=0.72,
        )
        e2 = Evidence(
            organization_id=org.id,
            investigation_id=inv.id,
            hypothesis_id=h1.id,
            provenance_id=p2.id,
            direction="contradicts",
            title="Nascente de controlo também apresentou quebra",
            source="Medição comparativa",
            method="Comparação pontual com bacia vizinha",
            limitations="Existe apenas uma bacia de controlo e uma medição.",
            weight=0.8,
        )
        e3 = Evidence(
            organization_id=org.id,
            investigation_id=inv.id,
            hypothesis_id=h3.id,
            provenance_id=p3.id,
            direction="supports",
            title="Sinais compatíveis com efeito combinado",
            source="Análise integrada de campo",
            method="Triangulação entre observação, clima e povoamento",
            limitations="Não existe desenho experimental que isole os mecanismos.",
            weight=0.55,
        )
        db.add_all([e1,e2,e3]); db.flush()
        db.add_all([
            Relation(organization_id=org.id, source_type="provenance", source_id=p1.id, target_type="evidence", target_id=e1.id, relation_type="produced", explanation="Origem e condições do contributo."),
            Relation(organization_id=org.id, source_type="provenance", source_id=p2.id, target_type="evidence", target_id=e2.id, relation_type="produced", explanation="Origem e condições do contributo."),
            Relation(organization_id=org.id, source_type="provenance", source_id=p3.id, target_type="evidence", target_id=e3.id, relation_type="produced", explanation="Origem e condições do contributo."),
        ]); db.flush()

        decision = Decision(
            organization_id=org.id,
            mission_id=m.id,
            investigation_id=inv.id,
            title="Executar conversão faseada em mosaico",
            rationale="Opção escolhida sob incerteza para reduzir risco de erosão e preservar continuidade operacional.",
            expected_outcome="Redução gradual da carga e melhoria das condições hídricas locais.",
        )
        db.add(decision); db.flush()
        assumption = Assumption(
            organization_id=org.id,
            mission_id=m.id,
            investigation_id=inv.id,
            decision_id=decision.id,
            code="ASS-001",
            statement="A nascente tinha historicamente caudal em março",
            method="Testemunho local",
            limitations="Sem registo contemporâneo ao período histórico referido.",
            status="refuted",
            valid_to=datetime.now(timezone.utc),
        )
        constraint = Constraint(
            organization_id=org.id,
            mission_id=m.id,
            investigation_id=inv.id,
            decision_id=decision.id,
            code="RST-001",
            statement="O licenciamento seria obtido em seis meses",
            source="Estimativa informal",
            limitations="Prazo não suportado por série estatística.",
            status="violated",
            valid_to=datetime.now(timezone.utc),
        )
        alternative = Alternative(
            organization_id=org.id,
            mission_id=m.id,
            investigation_id=inv.id,
            decision_id=decision.id,
            code="ALT-001",
            title="Corte raso integral",
            status="rejected",
            rejection_reason="Risco de erosão elevado",
            limitations="Custo e risco estimados sem orçamento formal.",
        )
        db.add_all([assumption,constraint,alternative]); db.flush()

        action = Action(organization_id=org.id, decision_id=decision.id, title="Executar primeira fase")
        implementation = Implementation(
            organization_id=org.id,
            decision_id=decision.id,
            code="IMP-001",
            title="Primeira fase da conversão",
            status="completed",
            deviations=["Execução 14 meses após a decisão"],
        )
        db.add_all([action,implementation]); db.flush()
        outcome = Outcome(
            organization_id=org.id,
            action_id=action.id,
            expected="Recuperação gradual do caudal",
            observed="Caudal pontual de 0,4 L/s em abril",
            baseline={},
            measured={"external_variables":["precipitação acima da média"]},
            limitations="Medição única, sem série de comparação e sem controlo suficiente.",
        )
        db.add(outcome); db.flush()
        learning = Learning(
            organization_id=org.id,
            outcome_id=outcome.id,
            statement="A documentação disponível não sustenta atribuir o resultado à intervenção.",
            status="confirmed",
            confidence=0.9,
            limitations="Conclusão sobre a evidência disponível, não sobre o fenómeno físico.",
        )
        db.add(learning); db.flush()

        db.add_all([
            Relation(organization_id=org.id, source_type="observation", source_id=obs.id, target_type="investigation", target_id=inv.id, relation_type="originates", explanation="A observação abre a investigação."),
            Relation(organization_id=org.id, source_type="hypothesis", source_id=h3.id, target_type="decision", target_id=decision.id, relation_type="informs", explanation="A hipótese combinada informou a decisão."),
            Relation(organization_id=org.id, source_type="assumption", source_id=assumption.id, target_type="decision", target_id=decision.id, relation_type="conditions", explanation="Pressuposto posteriormente refutado."),
            Relation(organization_id=org.id, source_type="implementation", source_id=implementation.id, target_type="outcome", target_id=outcome.id, relation_type="precedes", explanation="Sequência temporal; não prova causalidade."),
            Relation(organization_id=org.id, source_type="outcome", source_id=outcome.id, target_type="learning", target_id=learning.id, relation_type="generates", explanation="O resultado contribuiu para a aprendizagem metodológica."),
        ])

        db.add_all([
            EvidenceProposal(
                organization_id=org.id,
                investigation_id=inv.id,
                title="Série piezométrica de bacia de controlo por 24 meses",
                description="Recolha contínua antes de nova intervenção.",
                expected_effects={h1.id:-0.7,h2.id:0.3,h3.id:0.5},
                weight=0.85,
                estimated_cost=3500,
                estimated_days=730,
                risk_level="low",
                feasibility="high",
                limitations="Os efeitos esperados são pressupostos de desenho, não resultados.",
            ),
            EvidenceProposal(
                organization_id=org.id,
                investigation_id=inv.id,
                title="Registos históricos adicionais de caudal",
                description="Pesquisa em arquivo municipal e local.",
                expected_effects={h1.id:0.2,h2.id:0.6,h3.id:0.1},
                weight=0.7,
                estimated_cost=400,
                estimated_days=15,
                risk_level="low",
                feasibility="medium",
                limitations="Pode não existir documentação com método suficientemente claro.",
            ),
        ])
        recalculate_investigation_posteriors(db,org.id,inv.id)
        db.commit()
        print(f"Demonstração criada: missão {m.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
