# Escalation and SLA policy

_CloudFlow help center · Policy · applies to all_

## When the assistant hands off to a human
Escalation is decided **in code** from the classifier and critic signals (Annex A.3):
- Groundedness below the threshold after one revision.
- Intent is a **refund, credit, billing dispute, legal matter, security incident or
  account deletion**.
- The customer **explicitly asks for a human**, or shows strong negative sentiment with
  repeated contact.
- A required **tool has failed**, or the knowledge base does not cover the question and
  the customer needs an outcome.

The assistant does **not** escalate answerable how-to / troubleshooting requests with
high groundedness and no policy risk — unnecessary escalation is a failure.

## SLAs
- Billing handoffs: first response within **1 business day (24 h)**.
- Security handoffs: first response within **4 hours**.

## Registry values
- `critic_min_groundedness = 0.6` (CRITIC-MIN-GROUNDEDNESS-01)
- `billing_response_sla_hours = 24` (ESCALATION-SLA-BILLING-01)
- `security_response_sla_hours = 4` (ESCALATION-SLA-SECURITY-01)
