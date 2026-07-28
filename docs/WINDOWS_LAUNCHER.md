# SRIS Enterprise — Launcher Windows

## Primeira utilização

1. Instale e abra o Docker Desktop.
2. Execute `PRIMEIRA_CONFIGURACAO_SRIS.cmd`.
3. Defina o email, organização e palavra-passe do administrador.
4. Aguarde a construção dos serviços e o carregamento da missão demonstrativa.
5. Execute `ABRIR_SRIS_LAUNCHER.cmd`.

## Utilização diária

Execute `ABRIR_SRIS_LAUNCHER.cmd` e utilize os botões:

- **Iniciar SRIS** — inicia Docker e todos os serviços, espera pela aplicação e abre o navegador.
- **Abrir Plataforma** — abre `http://localhost:8000` quando a aplicação está operacional.
- **Parar SRIS** — encerra os contentores sem apagar os volumes nem os dados.
- **Atualizar Estado** — mostra o estado dos serviços.
- **Ver Logs** — apresenta as últimas linhas dos logs no próprio Launcher.
- **Abrir Pasta** — abre a pasta da instalação.

## Segurança

O configurador gera automaticamente segredos aleatórios para a instalação local. Não distribua o ficheiro `.env` e não o inclua em ZIPs públicos.

## Limite

Este Launcher simplifica a execução local da Alpha. A distribuição comercial recomendada continua a ser uma instalação cloud ou um instalador assinado, sem dependência visível de Docker para o cliente final.
