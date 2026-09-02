# SRIS Pilot & Mission Intelligence — Build v34

## Estado do produto

O Pilot V1 opera como uma única plataforma transversal para desenhar, executar, medir e aprender com decisões e intervenções em contexto real.

Tourism Advance, Hospitality Open Innovation e programas futuros são origens possíveis de um piloto. Não constituem modos de produto nem aplicações separadas.

## Arquitetura

```text
Organização
└── Unidade, serviço, instalação, território ou projeto
    └── Piloto
        ├── Pilot Charter
        ├── Data Readiness
        ├── Baseline e Scorecard
        ├── Missão ou missões governadas
        ├── Implementação
        ├── Value Case
        ├── Resultado
        ├── Relatórios
        └── Recomendação de escala

Memória organizacional
└── Aprendizagem publicada, reutilizável, revalidável e invalidável
```

## Contrato metodológico

### Cinco momentos apresentados ao utilizador

> Contexto → Evidência → Decisão → Medição → Memória

### Oito registos canónicos persistentes

> Observação → Evidência → Hipótese → Alternativa → Decisão → Ação → Resultado → Aprendizagem

### Condições transversais

- pressupostos;
- restrições;
- lacunas;
- incerteza;
- proveniência;
- confiança.

Contexto, Medição e Memória organizam a experiência e a governação. Não são tipos adicionais de registo canónico.

## Núcleo transversal e perfis

O núcleo metodológico é único. Perfis adaptam vocabulário, fontes típicas e métricas sem alterar a ontologia, a autoridade humana ou a memória.

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

## Pilot Charter

O contrato operacional contém:

- problema;
- decisão;
- objetivo;
- âmbito e exclusões;
- parceiro e contexto;
- sponsor, Pilot Owner, Data Owner, operação e revisão;
- datas;
- critério de sucesso;
- condições de suspensão;
- intervenção;
- recursos;
- riscos;
- reversibilidade;
- nível de integração;
- condições de privacidade.

As revisões usam controlo otimista de versão e produzem auditoria.

## Data Readiness e Scorecard

Cada fonte regista:

- tipo;
- sistema e formato;
- responsável;
- frequência;
- método de acesso;
- estado de prontidão;
- qualidade;
- obrigatoriedade;
- limitações.

Cada métrica separa:

- baseline;
- objetivo;
- resultado;
- atividade de normalização;
- unidade;
- fonte;
- método;
- período;
- confiança;
- limitações.

Uma alteração absoluta não é automaticamente promovida a eficiência, impacto ou causalidade.

## Piloto e missão

O Piloto organiza colaboração, dados, execução, valor e escala.

A Missão preserva o percurso canónico da decisão. Uma missão pode ser criada diretamente a partir do piloto; o contrato pré-preenche o contexto e a ligação é criada automaticamente depois da gravação.

Nenhum piloto substitui a missão como fonte de verdade dos oito registos canónicos.

## Value Case

O valor é organizado em seis dimensões:

- económica;
- operacional;
- recursos;
- experiência;
- governação;
- aprendizagem.

Cada elemento mantém um estatuto explícito:

- esperado;
- estimado;
- observado;
- realizado.

Um valor realizado exige:

- período;
- referência da baseline;
- fonte;
- cálculo;
- avaliação de atribuição.

Limitações e confiança permanecem visíveis. Valor esperado ou estimado nunca é somado silenciosamente ao valor realizado.

## Equipa do piloto

Papéis formais:

- Sponsor;
- Pilot Owner;
- Mission Owner;
- Data Owner;
- Operação;
- Revisor;
- Mentor do programa;
- Observador.

Os papéis do piloto complementam, mas não substituem, a matriz de acesso da organização. Um mentor ou observador não adquire autoridade sobre a decisão formal, execução, validação do resultado, publicação da aprendizagem ou escala.

## Report Suite

Relatórios disponíveis a partir dos mesmos dados persistentes:

1. Pilot Brief;
2. Data Readiness Report;
3. Decision Dossier;
4. Pilot Progress Report;
5. Pilot Outcome Report;
6. Scale Recommendation;
7. Dossier completo.

Todos podem ser exportados em formato verificável. O relatório completo agrega contrato, governação, fontes, scorecard, missões, implementação, Value Case e escala.

## Acesso e identidade

O piloto mantém dois modos coerentes sobre o mesmo sistema de identidade:

- criação autónoma de um workspace piloto, quando a configuração a permite;
- adesão institucional por convite.

Login, convite e recuperação usam tokens pessoais, temporários, auditáveis e de utilização única. A recuperação institucional substitui o percurso piloto antigo na interface.

## Assistência

A assistência é opcional. Quando não está configurada, missões, evidência, decisão, medição, Business Case e memória continuam operacionais.

Conteúdo assistido permanece proposta. Decisão formal, autorização para executar, validação do resultado, publicação da aprendizagem e decisão de escala permanecem humanas.

## Persistência e migrações

Novos objetos:

- `sris_pilots`;
- `sris_pilot_missions`;
- `sris_pilot_metrics`;
- `sris_pilot_data_sources`;
- `sris_pilot_work_items`;
- `sris_pilot_value_items`;
- `sris_pilot_collaborators`.

Migrações:

- `20260901_0023_pilot_mission_platform.py`;
- `20260901_0024_pilot_value_collaboration_reports.py`.

## Isolamento

Este build pertence exclusivamente a:

- branch `pilot-v1-september-2026`;
- serviço `sris-pilot-v1-staging`;
- PostgreSQL exclusivo do piloto.

Não altera o site institucional, a demonstração Tourism Advance anterior ou `sris-production`.

## Aceitação operacional ainda externa ao código

Antes de admitir dados confidenciais ou declarar produção comercial, continuam obrigatórios:

- email transacional configurado e testado;
- convite, ativação, recuperação, replay e revogação em ambiente público;
- projeto e chave de IA isolados, se a assistência fizer parte do piloto;
- exportações em browsers reais;
- iPhone e Android físicos;
- backup e restauro;
- teste negativo de isolamento entre organizações e RLS endurecida;
- rotação da palavra-passe do proprietário;
- uma missão real concluída com aprendizagem publicada;
- regressão final sobre um build congelado;
- revisão externa de segurança antes de dados sensíveis.
