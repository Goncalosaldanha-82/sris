# SRIS Enterprise Experience Alpha v0.2.1

Correção de robustez do arranque da aplicação.

## Alterações

- O contrato de `/auth/me` é normalizado antes de ser consumido pela interface.
- A aplicação aceita a resposta canónica, envelopes `data`, utilizador achatado e nomes alternativos (`name` / `display_name`).
- A identidade visível possui fallback seguro para email ou “Utilizador”.
- Respostas sem associação organizacional terminam com mensagem explícita em vez de erro JavaScript.
- Os caminhos dos assets passaram de absolutos para relativos, mantendo compatibilidade quando a aplicação é servida pelo backend e permitindo alojamento sob um subcaminho.
- Foram adicionados testes de contrato frontend com o test runner nativo do Node.js.

## Teste rápido

```bash
node --test frontend/tests/*.test.js
node --check frontend/assets/contracts.js
node --check frontend/assets/app.js
pytest
```
