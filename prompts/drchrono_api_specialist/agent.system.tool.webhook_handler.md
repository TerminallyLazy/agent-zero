### webhook_handler

DrChrono webhook management for real-time event processing with secure signature verification

**Webhook Setup:**
- action: "setup" - Configure webhook endpoints and events
- callback_url: HTTPS URL to receive webhook notifications
- secret_token: Secret token for webhook signature verification
- events: Array of event types to subscribe to

**Signature Verification:**
- action: "verify" - Verify webhook signature authenticity
- webhook_payload: Raw webhook payload string
- signature: Webhook signature from DrChrono headers
- secret_token: Secret token for verification

**Event Processing:**
- action: "process" - Process incoming webhook events
- webhook_payload: Webhook event data
- event_type: Type of webhook event

**Management:**
- action: "list_events" - List available webhook events and configuration
- action: "remove" - Remove webhook configuration
- callback_url: URL of webhook to remove

**Verification Utilities:**
- action: "generate_verification" - Generate verification response for setup
- secret_token: Secret token for verification
- msg: Message parameter from DrChrono verification request

**Testing:**
- action: "test_endpoint" - Test webhook endpoint connectivity
- callback_url: URL to test

**Supported Events:**
- APPOINTMENT_CREATE, APPOINTMENT_MODIFY, APPOINTMENT_DELETE
- PATIENT_CREATE, PATIENT_MODIFY
- CLINICAL_NOTE_LOCK, CLINICAL_NOTE_UNLOCK
- LINE_ITEM_CREATE, LINE_ITEM_MODIFY, LINE_ITEM_DELETE
- TASK_CREATE, TASK_MODIFY, TASK_DELETE

**Example usage**:
~~~json
{
    "thoughts": [
        "Setting up webhook for appointment notifications",
        "Need secure HTTPS endpoint and event subscription"
    ],
    "headline": "Configuring DrChrono webhook for appointments",
    "tool_name": "webhook_handler",
    "tool_args": {
        "action": "setup",
        "callback_url": "https://myapp.com/webhooks/drchrono",
        "secret_token": "secure_webhook_secret_123",
        "events": ["APPOINTMENT_CREATE", "APPOINTMENT_MODIFY", "PATIENT_CREATE"]
    }
}
~~~

**Signature verification example**:
~~~json
{
    "thoughts": [
        "Verifying incoming webhook is authentic",
        "Security check to prevent malicious requests"
    ],
    "headline": "Verifying webhook signature",
    "tool_name": "webhook_handler",
    "tool_args": {
        "action": "verify",
        "webhook_payload": "{\"id\":\"123\",\"event\":\"APPOINTMENT_CREATE\"}",
        "signature": "sha256_signature_here",
        "secret_token": "secure_webhook_secret_123"
    }
}
~~~

**Event processing example**:
~~~json
{
    "thoughts": [
        "Processing appointment creation webhook",
        "Need to handle event and update systems"
    ],
    "headline": "Processing appointment webhook event",
    "tool_name": "webhook_handler",
    "tool_args": {
        "action": "process",
        "webhook_payload": "{\"id\":\"webhook_123\",\"event\":\"APPOINTMENT_CREATE\",\"object_id\":\"appointment_456\"}",
        "event_type": "APPOINTMENT_CREATE"
    }
}
~~~

Always use HTTPS URLs for webhook endpoints and verify signatures to ensure security.