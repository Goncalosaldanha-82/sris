# SRIS Enterprise Experience Alpha v0.3

## Incremento entregue

A v0.3 fecha a primeira barreira de utilização local: o utilizador deixa de depender de comandos manuais para iniciar e parar a plataforma.

### Componentes

- Launcher Windows com estado operacional, arranque, encerramento, abertura do navegador e visualização de logs.
- Configurador inicial que gera segredos aleatórios e cria `.env` sem credenciais por omissão.
- Bootstrap guiado de administrador e missão demonstrativa.
- Scripts de estado e encerramento que preservam dados.
- Documentação de utilização diária.

### Limites

- O Launcher é uma aplicação PowerShell/WinForms, não um executável assinado.
- Docker Desktop continua a ser um pré-requisito local.
- A distribuição comercial deverá migrar para cloud ou instalador assinado.
