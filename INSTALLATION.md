# Instalação do ATLAS Knowledge Vault

## Método simples

1. Descompactar este pacote.
2. Copiar a pasta `docs` para a raiz do repositório SRIS.
3. Quando o Windows perguntar, escolher **combinar/mesclar pastas**.
4. Não substituir ficheiros existentes sem revisão.
5. Verificar as alterações no GitHub Desktop.

## Método automático

Abrir PowerShell dentro da pasta descompactada e executar:

```powershell
python install_atlas_knowledge_vault.py --repo "C:\Users\barba\Documents\GitHub\sris"
```

O instalador:

- cria a nova estrutura;
- não substitui ficheiros existentes;
- apresenta o que escreveu e o que ignorou;
- deixa as alterações prontas para revisão no GitHub Desktop.

## Commit sugerido

```text
Create ATLAS Knowledge Vault v0.1
```
