# Test Report — SRIS Enterprise Experience Alpha v0.2.1

## Automated results

- Backend/API: **19 passed, 0 failed** (`pytest -q`)
- Frontend auth-contract tests: **4 passed, 0 failed** (`node --test frontend/tests/*.test.js`)
- JavaScript syntax: `contracts.js` and `app.js` passed `node --check`

## Regression fixed

The frontend no longer assumes that `/auth/me` always returns `user.full_name` inside one exact envelope. The response is normalized and tested against:

1. canonical `{ user, memberships }`;
2. flattened user payload;
3. `{ data: { user, memberships } }` envelope;
4. malformed or empty payload.

A missing organizational membership now produces an explicit startup error rather than an uncaught JavaScript exception.

## End-to-end contract exercised

The backend suite verifies login, `/auth/me`, organization membership, static delivery of `contracts.js` and `app.js`, and the experience endpoints used after startup.
