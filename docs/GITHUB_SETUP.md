# Colocar o SRIS no GitHub

1. Criar um repositório privado chamado `sris-enterprise` sem README, licença ou `.gitignore` adicionais.
2. Instalar GitHub Desktop.
3. Escolher **File → Add local repository** e selecionar esta pasta.
4. Caso ainda não seja um repositório, escolher **Create a repository here**.
5. Confirmar que `.env`, bases de dados, caches e backups não aparecem na lista de ficheiros.
6. Criar o commit `SRIS Enterprise Pilot Candidate v0.9 — Provenance Object`.
7. Publicar como repositório **Private**.
8. Em GitHub, criar a tag/release `v0.9.0-pilot`.

A workflow `.github/workflows/ci.yml` executa os testes em push e pull request.
