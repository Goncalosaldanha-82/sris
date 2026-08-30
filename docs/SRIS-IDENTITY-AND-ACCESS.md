# SRIS identity and access lifecycle

## Operating model

Managed SRIS environments use invitation-only account creation. Public
self-registration and public organization creation remain disabled. The first
institutional owner is established through the separate, one-time activation
runbook; that owner then manages ordinary users through the platform.

The normal lifecycle is:

1. an `owner` or `admin` opens **Utilizadores**;
2. the inviter enters the person's name, email and permitted role;
3. SRIS emails a personal activation link;
4. a new user chooses a password, while an existing SRIS user confirms the
   current password before joining an additional organization;
5. SRIS creates the membership and records the event in the audit ledger;
6. the invitation becomes unusable after acceptance, revocation or expiry.

An `owner` may invite `admin`, `reviewer`, `contributor` and `observer` roles.
An `admin` may invite `reviewer`, `contributor` and `observer` roles. Ownership
cannot be transferred through an ordinary invitation or role change.

## Password recovery

The public recovery form always returns the same message, whether an email is
known, unknown, disabled, throttled or the mail service is unavailable. This
prevents the endpoint from becoming an account directory.

For an active account, SRIS emails a random, expiring, single-use link. Only a
SHA-256 digest is stored. A successful reset:

- changes the Argon2 password hash;
- consumes the reset token;
- revokes all other outstanding reset tokens;
- increments `auth_version`, immediately invalidating previous bearer tokens;
- writes an audit event.

The emailed secret is carried in the URL fragment (`#reset=` or `#invite=`),
which is not included in the initial page request. The account page removes the
fragment from browser history and submits the secret only inside an HTTPS JSON
body, never in an API path or query string that ordinary access logs record.

## Required Railway variables

Configure these variables only in the dedicated invitation pilot service.
Select exactly one transport. Resend is shown below; `brevo` with
`BREVO_API_KEY` is equivalent, and the SMTP variables remain supported for
institutional relays:

```text
ATLAS_SELF_REGISTRATION_ENABLED=false
ATLAS_ORGANIZATION_CREATION_ENABLED=false
SRIS_PUBLIC_BASE_URL=https://sris-pilot-v1-staging.up.railway.app
SRIS_EMAIL_PROVIDER=resend
SRIS_EMAIL_FROM=<verified sender>
SRIS_EMAIL_FROM_NAME=SRIS
RESEND_API_KEY=<secret>
SRIS_INVITATION_TTL_HOURS=72
SRIS_PASSWORD_RESET_TTL_MINUTES=30
SRIS_PASSWORD_RESET_COOLDOWN_SECONDS=60
```

The `sris-production` service is outside this pilot and must not receive these
variables, deployments or database links.

For Brevo, use `SRIS_EMAIL_PROVIDER=brevo` and `BREVO_API_KEY=<secret>`. For an
institutional SMTP relay, use `SRIS_EMAIL_PROVIDER=smtp` and the existing
`SRIS_SMTP_*` variables. The canonical username variable is
`SRIS_SMTP_USERNAME`; `SRIS_SMTP_USER` remains accepted for compatibility with
the first staging configuration. If several transports are configured without an
explicit provider, SRIS fails closed instead of choosing one silently.

The sender address must be accepted by the chosen provider. User passwords
are never Railway variables and are never chosen by administrators.

## Deployment verification

1. Deploy the migration and code in staging.
2. Confirm `/health` and `/api/auth/capabilities`.
3. Establish the first owner through the one-time activation flow.
4. Open **Utilizadores** and invite a disposable test address as `observer`.
5. Verify receipt, activation, first login and organization membership.
6. Request password recovery for the same address.
7. Verify the old password and the earlier access token no longer work.
8. Verify invitation replay and reset-link replay both fail.
9. Revoke the disposable membership.
10. Record the verified pilot configuration without propagating it to another
    Railway service.

Never reuse an invitation, recovery or initial-owner activation token between
environments.
