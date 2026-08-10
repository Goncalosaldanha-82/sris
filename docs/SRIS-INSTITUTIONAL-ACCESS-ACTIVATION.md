# SRIS institutional access activation

## Why this exists

The historical `bootstrap_admin.py` used the legacy SRIS data model while the
deployed application authenticates against `app.atlas_platform`. Password
recovery also assumed that the intended user already existed. Together, those
conditions could leave the public demonstration working while no institutional
owner could sign in.

The activation flow repairs either state:

- no user exists: create the canonical user;
- a user exists with an obsolete or unknown password hash: replace it;
- no organization or membership exists: create them;
- a membership exists with another role: make the configured user the owner.

The whole operation is protected by an exact email and a high-entropy,
single-use token. The endpoint is absent from OpenAPI and returns `404` whenever
the temporary gate is not fully configured.

## Safe sequence

Always prove the flow in `staging` before touching `production`.

1. From the local repository, run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
     ".\scripts\ACTIVATE_SRIS_INSTITUTIONAL_ACCESS.ps1" `
     -BaseUrl "https://sris-staging.up.railway.app"
   ```

   On its first execution the script generates a fresh token, copies it to the
   clipboard and saves only a Windows DPAPI-encrypted copy under the current
   user's local application data. The PowerShell window may be closed without
   losing the prepared token. Never paste it into chat, source code or Git.

2. In the Railway `sris` service for the target environment, set or replace:

   - `SRIS_ACCESS_ACTIVATION_EMAIL=goncalo.saldanha82@gmail.com`
   - `SRIS_ACCESS_ACTIVATION_TOKEN=<paste with Ctrl+V>`
   - `ATLAS_SELF_REGISTRATION_ENABLED=false`
   - `ATLAS_ORGANIZATION_CREATION_ENABLED=false`

3. Deploy and wait for `ACTIVE`.
4. Run exactly the same PowerShell command again. The script recovers the
   encrypted token; it never asks the operator to paste a token into a hidden
   prompt.

5. Confirm that the deployment is `ACTIVE`, then enter the new password only at
   the two hidden prompts.

6. Require the final output `ACESSO INSTITUCIONAL CONFIRMADO`. The script proves:

   - password login;
   - `/api/auth/me`;
   - organization access;
   - `owner` membership.

7. Delete both temporary `SRIS_ACCESS_ACTIVATION_*` variables and deploy again.
8. Sign in through the browser and confirm the header says
   `Sessão institucional · Proprietário · SRIS`.

If the API returns `404`, the script does not discard the prepared token or ask
for the password again in a loop. It copies the same token back to the clipboard
and instructs the operator to replace only `SRIS_ACCESS_ACTIVATION_TOKEN`, deploy
and rerun the same command. Use `-ResetPreparedToken` only when deliberately
abandoning that prepared activation and generating a new token.

For production, repeat the sequence with a separate state and:

```powershell
-BaseUrl "https://sris-production.up.railway.app"
```

Never copy a staging activation token into production. The organization UUID
printed after successful activation is not a secret; it is the value later used
for the separately governed AI pilot gate.

## Security properties

- no password is stored in the repository, command line or Railway variable;
- passwords are hashed with Argon2;
- the activation token is compared in constant time and recorded only as SHA-256;
- token reuse returns `409` and cannot change the password;
- invalid or missing gate configuration returns the same undiscoverable `404`;
- the prepared token survives a closed PowerShell window only as DPAPI-encrypted
  state readable by the same Windows user and is deleted after success;
- temporary secrets are removed from the PowerShell process and clipboard;
- public account and organization creation are closed by default on Railway.
