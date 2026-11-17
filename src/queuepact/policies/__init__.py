"""Pure policy helpers: routing prerequisites and deterministic dispatch order."""
from ..models import Service as S, SERVICES, PREP, Policy


def eligible(student):
    done = student.completed
    result = []
    if S.DOCUMENT_VERIFICATION not in done and student.documents_ready:
        result.append(S.DOCUMENT_VERIFICATION)
    if S.PHOTO_CAPTURE not in done:
        result.append(S.PHOTO_CAPTURE)
    if S.FEE_PAYMENT not in done and S.DOCUMENT_VERIFICATION in done:
        result.append(S.FEE_PAYMENT)
    if S.FINAL_ENROLLMENT not in done and all(s in done for s in SERVICES[:3]):
        result.append(S.FINAL_ENROLLMENT)
    return result


def candidates(student, policy):
    if policy == Policy.ORDINARY:
        return [PREP] if not student.documents_ready else [next(s for s in SERVICES if s not in student.completed)]
    return eligible(student) + ([PREP] if not student.documents_ready else [])


def dispatch_key(student, now, threshold, policy):
    protected = policy in (Policy.SMART, Policy.V2) and now - student.wait_age >= threshold
    if protected:
        return (0, student.wait_age, student.source.id)
    return (1, student.queue_order, student.source.id)
