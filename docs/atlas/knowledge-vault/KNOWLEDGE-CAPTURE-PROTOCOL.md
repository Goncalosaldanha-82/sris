# Knowledge Capture Protocol

## Objetivo

Garantir que nenhuma decisão, hipótese, correção, risco ou aprendizagem relevante se perde fora do repositório.

## Fluxo

```text
Conteúdo de origem
→ Extração estruturada
→ Classificação
→ Registo
→ Ligação a ativos
→ Revisão humana
→ Commit
→ Pull Request
→ Aprovação
```

## Classificação mínima

- decisão;
- hipótese;
- conceito;
- risco;
- ação;
- observação;
- correção;
- alteração arquitetónica.

## Destino

| Tipo | Destino principal |
|---|---|
| Decisão estrutural | `constitution/` ou ADR existente |
| Hipótese | `hypotheses/` |
| Investigação | `research-notes/` ou `missions/` |
| Definição | `ontology/` |
| Alteração teórica | `theories/` |
| Experiência | `experiments/` |
| Evidência/resultado | `validation/` |
| Estado/dependência | `registry/` |
| Síntese transversal | `knowledge-vault/` |

## Regra de segurança

O Repository Agent pode preparar alterações, mas não adota conceitos nem faz merge sem revisão humana.
