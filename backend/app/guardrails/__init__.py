"""Guardrails: input and output checks around a guest turn (gap: output side did not exist).

The runtime has fenced retrieved knowledge as labelled data since the beginning — that is the
input side, and it lives in `app.core.prompting`. Two things were missing, and both matter more
once the assistant handles booking details and starts acting on guest requests:

- **Inbound PII.** A guest types an email and a phone number to make a booking. Those must not
  reach the model at all, because anything the model sees it can quote, echo into a log, or leak
  into a support export.
- **Outbound PII.** The harder direction. Redaction that blanks a guest's own email back to them
  is worse than no redaction: it breaks a legitimate answer and looks like a fault. So the outbound
  rule is asymmetric — redact what the model could only have *invented*, and leave what the guest
  supplied.

Every check here is deterministic and offline. A guardrail that calls a model to decide whether to
redact costs a model call per turn, can be argued out of, and fails open when the provider is down —
the opposite of what a guardrail is for.
"""

from app.guardrails.pii import PIIKind, PIIMatch, find_pii, redact, redact_outbound

__all__ = [
    "PIIKind",
    "PIIMatch",
    "find_pii",
    "redact",
    "redact_outbound",
]