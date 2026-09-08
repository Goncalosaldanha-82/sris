# SRIS — Commercial Access Lifecycle

Status: canonical for Pilot V1 staging  
Build family: `pilot-commercial-access-lifecycle-v40`

## Canonical lifecycle

**Criar conta → Pedido de acesso → Aprovação SRIS → Convite único → Workspace atribuído → Entitlement comercial → Expiração/renovação**

The labels above describe one governed lifecycle, not seven independent account features.

## Separation of concerns

SRIS deliberately separates three things that are often collapsed into a single "account" concept:

1. **Identity (`User`)** — who the person is and how authentication is performed.
2. **Workspace membership (`Membership` + `Organization`)** — which workspace the person can access and with which role.
3. **Commercial entitlement (`CommercialEntitlement`)** — whether that workspace currently has the commercial right to use licensed SRIS operations, under which plan and until when.

An entitlement expiry never deletes the user, membership, missions, evidence, decisions, audit events or organizational memory. It removes the licensed right to execute governed workspace operations until renewal.

## 1. "Criar conta" is the public entry point, not self-registration

The entry page keeps the **Criar conta** tab, but the form only collects:

- full name;
- organization/project name;
- email.

It does **not** collect a password and does **not** create a `User`, `Organization` or `Membership`.

`POST /api/access-requests` returns the same neutral `202 Accepted` response for a newly created request and an already-pending request for the same email. This prevents the public endpoint from becoming an account-enumeration surface.

The legacy `POST /api/pilot/register` URL is retained only as a compatibility alias and now starts the same access-request lifecycle. It no longer creates credentials or workspaces directly.

## 2. SRIS approval is a platform responsibility

Approval is intentionally separate from tenant administration.

Platform approvers are configured explicitly through:

- `SRIS_ACCESS_APPROVER_EMAILS`, or
- `SRIS_PLATFORM_ADMIN_EMAILS`.

If neither variable grants the authenticated email approval rights, platform approval and renewal endpoints fail closed with `403 platform_approval_required`.

Being an `owner` or `admin` of a customer workspace does not make that user an SRIS platform approver.

## 3. Approval is atomic

For a normal new-organization request, approval performs one governed transaction:

1. creates the workspace (`Organization`), unless an existing workspace is explicitly assigned;
2. assigns commercial terms (`CommercialEntitlement`);
3. creates a personal, expiring, single-use invitation (`UserInvitation`);
4. links the access request to the workspace and invitation;
5. records audit events;
6. commits the transaction;
7. sends the invitation email in the background.

Approval fails before mutation when transactional authentication email is not ready. The platform therefore cannot show a request as approved while being unable to deliver the activation path.

## 4. The invitation remains the credential-creation boundary

The initial workspace invitation uses the existing canonical identity lifecycle:

- raw invitation token is never stored;
- only a purpose-bound hash is persisted;
- default validity is 72 hours, configurable within existing bounded limits;
- token is single-use;
- a new user defines the password during acceptance;
- an existing user confirms their existing password when accepting access to another workspace;
- acceptance creates the `Membership` with the role approved by SRIS.

The initial invitation may assign `owner` because it bootstraps a new workspace. Normal workspace owners/admins retain the existing, narrower role-assignment rules for subsequent invitations.

## 5. Entitlement is per workspace

Commercial access is stored in `sris_commercial_entitlements` with:

- `organization_id` (unique);
- `plan_code` (`pilot`, `professional`, `organization`);
- lifecycle status;
- start and expiry timestamps;
- optional commercial reference;
- approving SRIS user;
- renewal count;
- audit timestamps.

The effective status is evaluated at request time. SRIS does not depend on a background scheduler to notice an expiry.

## 6. Enforcement

`SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT` explicitly controls enforcement.

When unset:

- managed Railway environments default to **enforced**;
- local/test environments default to **not enforced**.

When enforced, an expired, suspended, cancelled or missing entitlement blocks licensed organization operations in the backend. This is not a front-end-only restriction.

The user may still authenticate and inspect the entitlement state. This is necessary to preserve identity, explain the access problem and support renewal without data loss.

## 7. Migration safety

Migration `20260907_0026` creates the access-request and commercial-entitlement tables.

Every organization that already exists at migration time receives a `grandfathered` entitlement with no expiry. It is treated as active by the gate. This prevents introducing the commercial lifecycle from accidentally locking existing Pilot V1 staging workspaces.

A grandfathered workspace can later be moved to explicit commercial terms by an SRIS commercial decision; migration itself never fabricates a renewal date.

## 8. Renewal

Only an SRIS platform approver can renew through:

`POST /api/admin/organizations/{organization_id}/commercial-entitlement/renew`

Renewal:

- reactivates an expired entitlement;
- can change the plan;
- extends from the existing expiry when it is still in the future, otherwise from the renewal time;
- increments `renewal_count`;
- records `commercial.entitlement_renewed` in the audit log.

## 9. Administrative surface

The workspace administration screen always shows the current workspace entitlement to authorized workspace administrators.

When the authenticated user is also an SRIS platform approver, the same screen additionally exposes:

- pending and decided access requests;
- approve/reject;
- plan and initial entitlement duration;
- initial invitation resend;
- entitlement renewal.

A normal customer owner/admin does not receive these platform-level controls.

## Audit actions

The lifecycle records, as applicable:

- `access.requested`
- `access.request_approved`
- `access.request_rejected`
- `user.invited`
- `user.invitation_resent`
- `commercial.entitlement_created`
- `commercial.entitlement_renewed`

## Required staging configuration

Before end-to-end approval can be declared operational:

1. transactional auth email must be ready;
2. `SRIS_ACCESS_APPROVER_EMAILS` must identify the SRIS operator(s);
3. migration `20260907_0026` must be at database head;
4. commercial entitlement enforcement must be enabled in managed staging (default when unset, explicit `true` preferred for auditability).
