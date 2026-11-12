# @amakuru/api-client

TypeScript types generated from the Amakuru OpenAPI document.

```bash
# From repo root (API deps installed):
make openapi      # writes docs/api/openapi.json and packages/api-client/openapi.json
make api-client   # runs openapi-typescript → src/schema.ts
```

Hand-written HTTP clients are not allowed in this package. The admin app may keep a thin fetch wrapper until it switches to the generated types.
