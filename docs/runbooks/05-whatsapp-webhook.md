# Runbook: WhatsApp webhook failures

## Symptoms

- Meta cannot verify the webhook
- Messages received but no replies
- Signature failures in logs

## Checks

```bash
grep -E '^(WHATSAPP_|META_)' .env
curl -sS "http://127.0.0.1:8000/api/v1/public/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=$WHATSAPP_VERIFY_TOKEN&hub.challenge=test"
docker compose logs api --tail=200 | rg -i whatsapp
```

Confirm tenant `channel_configs.whatsapp_enabled` and encrypted token exist.

## Mitigations

1. Align `WHATSAPP_VERIFY_TOKEN` with Meta app settings.
2. Ensure `META_APP_SECRET` matches the app; reject unsigned traffic in production.
3. Re-encrypt / rotate the tenant access token via admin Channels (Phase 7 polish) or DB ops.
4. Check Redis dedupe keys if every retry is skipped: `amakuru:wa:dedupe:*`.

## Verify

Challenge returns the challenge string; a signed test POST returns `{"status":"ok"}`.
