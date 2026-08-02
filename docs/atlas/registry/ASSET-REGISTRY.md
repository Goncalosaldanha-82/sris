# ATLAS Asset Registry

**Versão:** 0.1  
**Estado:** Active

| ID | Tipo | Título | Estado | Localização | Dependências |
|---|---|---|---|---|---|
| CON-000 | Constituição | Constituição do Project ATLAS | Working | `../constitution/` | — |
| ASM-000 | Método | Atlas Scientific Method | Working | `../asm/` | CON-000 |
| GRQ-001 | Pergunta | Grand Research Question | Working | `../research-notes/` | ASM-000 |
| MISSION-000 | Missão | Unidade atómica do SRIS | Active | `../missions/` | GRQ-001 |
| TICC-000 | Teoria | TICC provisional core | Provisional | `../theories/` | GRQ-001 |
| ONT-000 | Ontologia | Ontologia provisória | Active | `../ontology/` | MISSION-000 |
| ARA-001 | Agente | ATLAS Repository Agent v0.1 | Experimental | `../../backend/app/atlas_agent/` | ASM-000 |
| KV-001 | Vault | ATLAS Knowledge Vault | Active | `../knowledge-vault/` | CON-000, ASM-000 |
