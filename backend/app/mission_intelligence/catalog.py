from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import ContextDossier


ASSETS_ROOT = Path(__file__).resolve().parents[3] / "frontend" / "assets"
CATALOG_PATH = ASSETS_ROOT / "sris-mission-catalog-v1.3.json"
STAGING_ENVIRONMENT_ID = "625472d4-144c-460a-b152-d1890f1f80db"
ACADEMIC_HIDDEN_MISSIONS = {"CA-AWARD-APPLICATION"}


def _academic_staging_runtime() -> bool:
    """Apply the academic presentation only to the known Railway staging runtime."""
    return os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip() == STAGING_ENVIRONMENT_ID


def _prepend_unique(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    record_id = str(record.get("id") or "")
    records[:] = [item for item in records if str(item.get("id") or "") != record_id]
    records.insert(0, record)


def _apply_academic_research_boundary(missions: dict[str, Any]) -> None:
    """Present the two field cases with an explicit boundary between promoter and research.

    The promoter may preserve observations, declared local memory, documentary sources,
    unknowns and hypotheses. Scientific method, sampling, instrumentation, chronology
    and interpretation begin only when a competent research team accepts the case.
    """
    m1 = missions.get("M-001")
    if isinstance(m1, dict):
        m1["method_notice"] = (
            "Caso real aberto. Os registos foram declarados pelo promotor e ainda não "
            "tiveram validação independente. Não está identificada qualquer nascente "
            "na parcela. A água observada em abril de 2026 é registada apenas como "
            "linha de água/escoamento observado; origem, permanência e regime "
            "hidrogeológico não foram determinados."
        )
        analysis = m1.setdefault("analysis", {})
        analysis["context"] = (
            "Parcela de aproximadamente 5 ha em Podentes, Penela: cerca de 2 ha de "
            "eucalipto e 3 ha de vegetação espontânea. Em abril de 2026 foi observada "
            "presença de água, incluindo linha de água com escoamento visível. Não está "
            "identificada qualquer nascente na parcela. Não existe medição de caudal, "
            "série temporal ou caracterização da origem e permanência dessa água."
        )
        analysis["available_evidence"] = (
            "OBS-0001: caracterização aproximada da parcela por observação direta. "
            "OBS-0002: presença de água observada e fotografada em abril de 2026, "
            "classificada apenas como linha de água/escoamento observado; não existe "
            "evidência para a designar como nascente. OBS-0003: estrato arbustivo "
            "desenvolvido, sem quantificação de carga de combustível."
        )
        situation = m1.setdefault("situation", {})
        attention = list(situation.get("attention") or [])
        attention = [
            item for item in attention
            if str(item.get("title") or "") != "Nenhuma nascente identificada na parcela."
        ]
        attention.insert(
            0,
            {
                "title": "Nenhuma nascente identificada na parcela.",
                "description": (
                    "A presença de água observada não permite inferir uma nascente. "
                    "A designação permanece linha de água/escoamento até existir "
                    "caracterização competente."
                ),
                "level": "Fronteira semântica",
            },
        )
        situation["attention"] = attention

    m2 = missions.get("M-002")
    if not isinstance(m2, dict):
        return

    m2["status"] = "Caso científico aberto"
    m2["confidence"] = "Baixa"
    m2["decision"] = "DEC-M002-001 · Encaminhar o caso para investigação competente"
    m2["method_notice"] = (
        "Caso científico aberto. O promotor limita-se a preservar observações, memória "
        "local declarada, fontes documentais, hipóteses e lacunas. Não executa nem "
        "antecipa a investigação científica. Desenho de estudo, amostragem, "
        "instrumentação, cronologia e interpretação pertencem à equipa de investigação "
        "competente e às entidades com legitimidade para autorizar o trabalho."
    )
    m2["subtitle"] = (
        "Nascente, regueira associada, memória comunitária e fontes académicas: "
        "relações por demonstrar, investigação por definir."
    )

    requirements = m2.setdefault("analysis_requirements", {})
    requirements["research_boundary"] = {
        "required": True,
        "reason": (
            "A plataforma deve parar onde terminam as competências e a evidência do "
            "promotor; a metodologia científica é definida por investigadores competentes."
        ),
    }

    situation = m2.setdefault("situation", {})
    situation["summary"] = (
        "Dragos reúne elementos reais mas de natureza diferente: uma nascente conhecida "
        "localmente; uma regueira fisicamente observável que segue em direção à aldeia, "
        "com derivações, troços junto à estrada e passagens por condutas antigas, alguns "
        "hoje obstruídos; memória local de utilização comunitária; e fontes académicas "
        "independentes sobre o microtopónimo e uma árula romana encontrada em Dragos. "
        "A idade, função, estatuto jurídico e relação entre estes elementos não estão demonstrados."
    )
    situation["attention"] = [
        {
            "title": "A investigação começa onde termina o promotor.",
            "description": (
                "O SRIS organiza o caso e torna explícitas as lacunas; não transforma "
                "o promotor em investigador nem prescreve metodologia científica."
            ),
            "level": "Fronteira de competência",
        },
        {
            "title": "Regime jurídico e acesso por verificar.",
            "description": (
                "O uso comunitário histórico declarado e a existência física da regueira "
                "não demonstram, por si só, titularidade pública, servidão ou autorização de acesso."
            ),
            "level": "Legitimidade",
        },
        {
            "title": "Cronologia e função da regueira desconhecidas.",
            "description": (
                "A infraestrutura é observável, mas a sua idade, fases construtivas, "
                "função e administração histórica não foram estabelecidas."
            ),
            "level": "Investigação necessária",
        },
        {
            "title": "Relação arqueológica continua por demonstrar.",
            "description": (
                "A árula romana e o microtopónimo justificam investigação contextual; "
                "não provam uso romano da nascente, da regueira ou propriedades medicinais da água."
            ),
            "level": "Fronteira epistemológica",
        },
    ]
    situation["chain"] = [
        {
            "number": "01",
            "label": "Observação física",
            "value": "Nascente + regueira",
            "note": "Existência declarada pelo promotor; sem levantamento científico sistemático.",
            "state": "completed",
        },
        {
            "number": "02",
            "label": "Memória local",
            "value": "Uso comunitário declarado",
            "note": "Serve como pista de investigação; ainda não como estatuto jurídico ou facto histórico fechado.",
            "state": "attention",
        },
        {
            "number": "03",
            "label": "Fontes académicas",
            "value": "2 pistas independentes",
            "note": "Microtopónimo/nascente e árula romana em Dragos; relações funcionais não demonstradas.",
            "state": "completed",
        },
        {
            "number": "04",
            "label": "Hipóteses",
            "value": "Abertas",
            "note": "Sistema histórico de distribuição e eventuais relações territoriais permanecem por testar.",
            "state": "open",
        },
        {
            "number": "05",
            "label": "Acesso e competências",
            "value": "Por verificar",
            "note": "Titularidade, regime da água/regueira e autorizações ainda não estão fechados.",
            "state": "attention",
        },
        {
            "number": "06",
            "label": "Investigação",
            "value": "Por definir por equipa competente",
            "note": "O SRIS não antecipa método, amostragem, instrumentação ou interpretação.",
            "state": "open",
        },
        {
            "number": "07",
            "label": "Conclusão",
            "value": "Não existe",
            "note": "Nenhuma narrativa histórica, hidrogeológica ou patrimonial foi demonstrada.",
            "state": "unavailable",
        },
    ]

    analysis = m2.setdefault("analysis", {})
    analysis["context"] = (
        "A Nascente de Dragos é conhecida localmente e está associada, segundo observação "
        "do promotor, a uma regueira que segue em direção à aldeia, deriva em certos pontos, "
        "passa junto à estrada e entra em condutas antigas, com alguns troços hoje obstruídos. "
        "Existe memória local declarada de utilização comunitária. Separadamente, fontes "
        "académicas da Universidade de Coimbra documentam o microtopónimo/nascente e uma "
        "árula romana encontrada em Dragos. Nenhuma destas peças demonstra ainda a cronologia "
        "da regueira, o seu estatuto jurídico ou uma relação funcional com a ocupação romana."
    )
    analysis["central_question"] = (
        "Que relações entre a Nascente de Dragos, a regueira observável, a memória de uso "
        "comunitário e as fontes académicas existentes são cientificamente investigáveis, "
        "sem antecipar método, cronologia ou conclusão?"
    )
    analysis["available_evidence"] = (
        "Observação do promotor da nascente e da regueira associada; memória local declarada "
        "de uso comunitário; tese/Estudo Geral da Universidade de Coimbra sobre a permanência "
        "da Nascente de Dragos e do microtopónimo; Ficheiro Epigráfico 228, n.º 797, que "
        "documenta uma árula romana encontrada numa vinha associada a Dragos."
    )
    analysis["unknowns"] = (
        "Cronologia, extensão, função e fases da regueira; estatuto jurídico da nascente, "
        "água e infraestrutura; regime de acesso e autorizações; georreferenciação e relação "
        "espacial exata entre elementos; características hidrogeológicas e químicas; eventual "
        "relação funcional com ocupação antiga. A metodologia para responder a estas questões "
        "não é definida pelo promotor."
    )
    result = analysis.setdefault("result", {})
    result["headline"] = "O caso está preparado para investigação — não para conclusão."
    result["summary"] = (
        "O valor atual de Dragos está na separação rigorosa entre observação física, memória "
        "local, documentação académica e relações ainda não demonstradas. O próximo salto de "
        "conhecimento depende de investigação competente e legitimada, não de mais inferência do promotor."
    )
    result["principal_risk"] = (
        "Converter uma combinação sugestiva de nascente, regueira, memória comunitária, "
        "microtopónimo e achado romano numa narrativa histórica antes de existir investigação independente."
    )
    result["next_decision"] = (
        "Submeter o caso a leitura crítica de investigadores competentes e verificar o regime "
        "de acesso e as autorizações aplicáveis. O promotor não define nem executa o protocolo científico."
    )
    result["confidence"] = "Baixa"

    evidence = m2.setdefault("evidence", [])
    _prepend_unique(
        evidence,
        {
            "id": "OBS-M002-REGUEIRA",
            "type": "Observação",
            "title": "Regueira fisicamente observável associada à Nascente de Dragos",
            "description": (
                "Segundo observação direta do promotor, existe uma regueira que segue da "
                "zona da Nascente de Dragos em direção à aldeia, com derivações em certos "
                "pontos, troços junto à estrada e passagens por condutas antigas; parte do "
                "percurso encontra-se hoje obstruída por falta de uso e manutenção."
            ),
            "method": "Observação direta declarada pelo promotor; sem levantamento científico sistemático.",
            "limitation": (
                "Percurso, extensão, cronologia, função, materiais e natureza pública ou privada "
                "não foram validados por investigação independente."
            ),
            "status": "Registada",
            "confidence": "Moderada",
            "source": "Observação direta do promotor",
        },
    )
    _prepend_unique(
        evidence,
        {
            "id": "REP-M002-USO-COMUNITARIO",
            "type": "Representação",
            "title": "Memória local de utilização comunitária da água",
            "description": (
                "Segundo conhecimento e memória local declarados pelo promotor, a água da "
                "Nascente de Dragos e a regueira associada serviram historicamente a aldeia "
                "e derivavam para diferentes zonas."
            ),
            "method": "Declaração de memória local preservada como pista de investigação.",
            "limitation": (
                "Não foi ainda corroborada por registos administrativos, cartografia histórica, "
                "testemunhos independentes ou determinação jurídica do estatuto da infraestrutura."
            ),
            "status": "Por corroborar",
            "confidence": "Baixa",
            "source": "Memória local declarada pelo promotor",
        },
    )
    _prepend_unique(
        evidence,
        {
            "id": "HYP-M002-DISTRIBUICAO",
            "type": "Hipótese",
            "title": "Possível sistema histórico organizado de distribuição de água",
            "description": (
                "A configuração observada da regueira e a memória local podem ser compatíveis "
                "com um sistema histórico organizado de distribuição comunitária."
            ),
            "method": "Hipótese formulada a partir da separação entre observação física e memória local.",
            "limitation": (
                "Não estabelece idade, autoria, administração, estatuto público, continuidade histórica "
                "nem relação com ocupação romana."
            ),
            "status": "Por verificar",
            "confidence": "Baixa",
            "source": "M-002",
        },
    )

    learning = m2.setdefault("learning", [])
    learning[:] = [
        item for item in learning
        if str(item.get("id") or "") != "LRN-M002-BOUNDARY"
    ]
    learning.insert(
        0,
        {
            "id": "LRN-M002-BOUNDARY",
            "title": "Parar antes da investigação também é rigor",
            "description": (
                "Quando o caso ultrapassa as competências e a evidência do promotor, o sistema "
                "deve preservar as perguntas e entregar a metodologia a investigadores competentes, "
                "em vez de fabricar uma investigação amadora."
            ),
        },
    )


@lru_cache(maxsize=1)
def load_demo_catalog() -> dict[str, Any]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != "sris_mission_catalog":
        raise RuntimeError("Invalid SRIS mission catalog schema")
    if payload.get("schema_version") != "1.3":
        raise RuntimeError("Unsupported SRIS mission catalog version")

    missions = payload.get("missions")
    if not isinstance(missions, dict) or not missions:
        raise RuntimeError("SRIS mission catalog is empty")

    if _academic_staging_runtime():
        _apply_academic_research_boundary(missions)
        for mission_code in ACADEMIC_HIDDEN_MISSIONS:
            missions.pop(mission_code, None)

    for code, mission in missions.items():
        dossier = mission.get("context_dossier")
        if dossier:
            parsed = ContextDossier.model_validate(dossier)
            if parsed.mission_id != code:
                raise RuntimeError(
                    f"Context dossier mission identity mismatch for {code}"
                )
    return payload


def demo_mission(mission_code: str) -> dict[str, Any] | None:
    return load_demo_catalog()["missions"].get(mission_code)
