# API integrations

Create an API key under `/api/v1/integrations/api-keys`, then ingest events:

```http
POST /api/v1/integrations/ingest/events
X-Organization-ID: <organization UUID>
X-API-Key: <key shown once>
Content-Type: application/json

{"event_type":"cost.updated","title":"Monthly electricity cost","source":"ERP","payload":{"value":8400,"currency":"EUR"}}
```

Outbound webhooks include `X-SRIS-Signature: sha256=<digest>`. Consumers must calculate HMAC-SHA256 over the raw request body using the secret shown at creation.
