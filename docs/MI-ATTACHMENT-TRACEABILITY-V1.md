# SRIS · Rastreabilidade de anexos v1

Data: 2026-08-16  
Release: `1.7.3`  
Contrato interativo: `2.3`

## Problema fechado

Guardar um anexo e mostrar o seu nome na interface não prova que o conteúdo foi
lido. Antes desta correção, a extração e o índice existiam, mas uma resposta do
fornecedor podia ser aceite sem citar qualquer anexo selecionado.

## Garantias do contrato

1. O upload devolve o estado real de extração, a existência do índice e o número
   de blocos derivados.
2. O arquivo preserva o original cifrado; o índice contém blocos cifrados e
   termos HMAC, nunca vocabulário em claro.
3. O manifesto distingue anexos preservados, selecionados para o turno e deixados
   fora da janela finita.
4. Cada anexo do turno que entrou na janela tem de aparecer em pelo menos um
   `based_on_ids` da resposta estruturada.
5. Uma resposta sem todas as citações obrigatórias é rejeitada com
   `provider_attachments_not_cited`; não é apresentada como análise concluída.
6. A resposta e as exportações mostram, por ficheiro, o modo de leitura, os
   blocos selecionados e as secções que o citaram.
7. Um ficheiro preservado mas não selecionado continua pesquisável e é mostrado
   como não lido neste turno, sem omissão silenciosa.

## Critério de aceitação

Um teste com anexos só passa quando é possível demonstrar a sequência completa:

`upload → extração/leitura direta → índice → seleção → citação → resposta/exportação`

O estatuto epistemológico permanece `in_review`. Citação prova utilização e
rastreabilidade; não transforma o conteúdo fornecido pelo utilizador em facto
verificado.
