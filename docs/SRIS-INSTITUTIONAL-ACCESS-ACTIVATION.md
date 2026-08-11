# SRIS institutional access activation

## Purpose

Managed SRIS environments keep public account and organization creation closed.
The first institutional owner is established through a browser-only, one-time
activation. Ordinary users then enter by invitation and recover access through
expiring email links.

The previous PowerShell procedure has been retired. It required one raw secret
to be synchronized between a local process and Railway and could therefore
produce clipboard and keyboard-layout mismatches. The current procedure never
asks the operator to copy an environment token or retype a password after the
API has accepted it.

## Staging sequence

1. In the `sris` service for `staging`, keep these temporary gates present:

   - `SRIS_ACCESS_ACTIVATION_EMAIL=<institutional owner email>`
   - `SRIS_ACCESS_ACTIVATION_TOKEN=<any existing non-empty private value>`
   - `ATLAS_SELF_REGISTRATION_ENABLED=false`
   - `ATLAS_ORGANIZATION_CREATION_ENABLED=false`

   The activation token remains entirely inside Railway. Its exact value is
   never entered in PowerShell or in the browser.

2. Deploy and wait for `ACTIVE`.
3. Open the deployment log and locate the bounded block headed:

   ```text
   SRIS: PRIMEIRO ACESSO INSTITUCIONAL DISPONIVEL
   ```

4. Open the URL printed in that block. If the URL is not clickable, open
   `/account.html?mode=activate` on the staging domain and type the four groups
   shown after `CODIGO`.
5. Enter the configured email, the owner's full name and the new password once,
   with confirmation. The same API request repairs/creates the canonical user,
   creates/repairs the `SRIS` organization and `owner` membership, consumes the
   code and returns the authenticated browser session.
6. Confirm that the application header identifies an institutional owner.
7. Delete only the two temporary `SRIS_ACCESS_ACTIVATION_*` variables and deploy
   again. The account, password and session are stored in the database and do
   not depend on those variables.

Do not repeat this sequence in production until staging has been proved. Never
reuse staging activation values in production.

## Security properties

- the Railway activation value never leaves the server;
- the short browser proof is derived with HMAC-SHA-256 using the deployment's
  existing JWT secret and is disclosed only in the privileged deployment log;
- the proof is deterministic for one environment configuration, so restarts do
  not generate a succession of valid secrets;
- the proof is recorded only by SHA-256 and becomes unusable atomically with the
  account/password transaction;
- invalid email, invalid proof, consumed proof and disabled gate share the same
  non-disclosing response;
- password hashing uses Argon2 and successful activation returns the same
  authenticated session used by the browser application;
- public registration and public organization creation remain closed.
