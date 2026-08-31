# SRIS Pilot V1 — September 2026

## Delivery target

Plataforma funcional para pilotos controlados com organizações públicas ou privadas, preservando a transversalidade do núcleo SRIS.

## Product thesis

Uma organização deve iniciar cada nova decisão materialmente melhor porque missões e pilotos anteriores existiram, produziram prova e preservaram aprendizagem revalidável.

## Arquitetura de produto

```text
Organização
└── Unidade, serviço, instalação, território ou projeto
    └── Piloto
        ├── Pilot Charter
        ├── Data Readiness
        ├── Baseline e Scorecard
        ├── Missão ou missões governadas
        ├── Implementação
        ├── Resultado e Value Case
        └── Recomendação de escala

Memória organizacional
└── Aprendizagem publicada, reutilizável, revalidável e invalidável
```

O núcleo é transversal. Perfis configuráveis adaptam vocabulário, métricas, fontes e modelos ao setor sem alterar o contrato metodológico.

Perfis iniciais:

- Transversal;
- Hospitality;
- Setor público;
- Operações industriais;
- Laboratório territorial.

Modelos iniciais:

- decisão e intervenção mensurável;
- Hospitality · eficiência de recursos;
- Hospitality · inteligência operacional;
- serviço público · melhoria mensurável;
- investimento · validação antes de escala.

## Cinco momentos de utilização

> Contexto → Evidência → Decisão → Medição → Memória

## Oito registos canónicos

> Observação → Evidência → Hipótese → Alternativa → Decisão → Ação → Resultado → Aprendizagem

Pressupostos, restrições, lacunas, incerteza, proveniência e confiança são condições transversais, não etapas.

## Jornada principal

1. Comando — mostrar pilotos, missões, decisões, resultados e próximos passos que requerem atenção.
2. Novo piloto — escolher um modelo ou começar livremente, definindo problema, parceiro, contexto e decisão.
3. Pilot Charter — acordar âmbito, papéis, dados, métricas, recursos, risco, entregáveis e gates.
4. Data Readiness — identificar, receber, mapear e validar fontes sem exigir integração complexa inicial.
5. Baseline — separar valor absoluto, atividade de normalização, fonte, período, método e limitações.
6. Missão — executar os oito registos canónicos com revisão humana.
7. Implementação — acompanhar ações, marcos, riscos, bloqueios, responsáveis, prazos e prova.
8. Outcome — comparar baseline, objetivo e resultado sem atribuição fictícia.
9. Value Case — distinguir custo, benefício esperado, estimado, observado e realizado.
10. Scale Recommendation — escalar, repetir, adaptar, suspender ou parar com condições explícitas.
11. Memória — preservar aprendizagem e exigir revalidação num novo contexto.

## Provas do piloto

- tempo até início informado;
- prontidão de dados;
- baseline aprovada;
- decisão fundamentada;
- execução acompanhada;
- resultado fechado;
- benefício e custo com estatuto explícito;
- aprendizagem publicada;
- reutilização contextual;
- decisão de escala verificável.

## Gates de entrega

- serviço e PostgreSQL isolados;
- autenticação, convite e recuperação testados;
- criação e persistência de piloto e missão;
- importação documental e estruturada;
- exportação verificável;
- mobile físico;
- backup e restauro;
- assistência desligável e governada;
- uma missão real fechada;
- regressão final sobre build congelado.

## Non-negotiables

- nenhuma afirmação da interface pode ultrapassar os dados armazenados;
- o fornecedor de IA não é sistema de registo;
- nenhum benefício é realizado sem baseline, período, fonte, cálculo e avaliação de atribuição;
- histórico é substituído ou invalidado, nunca apagado silenciosamente;
- perfis setoriais não bifurcam o núcleo do produto;
- programas de inovação são canais para pilotos, não versões distintas da aplicação.
