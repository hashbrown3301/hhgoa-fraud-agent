from dataclasses import dataclass

AUTO_ACTIONS = {
    "ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER", "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH",
    "GENERATE_REPORT", "CREATE_CASE", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD",
}
ALL_ACTIONS = AUTO_ACTIONS | {
    "DECLINE_TRANSACTION", "BLOCK_CARD", "BLOCK_ALL_CARDS", "FILE_REPORT",
}

BLOCK_L1_MAX = 2500      # BLOCK_CARD: L1 up to this exposure, L2 above
REPORT_MIN_EXPOSURE = 1000
CASE_MIN_PROB = 0.30     # policy 3a
VERIFY_BELOW_PROB = 0.70 # R1
ESCALATE_EXPOSURE = 500  # R4 / R8


def route(action: str, exposure: float = 0.0) -> str:
    """Approval route for an action (policy section 2)."""
    if action not in ALL_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    if action in AUTO_ACTIONS:
        return "auto"
    if action == "DECLINE_TRANSACTION":
        return "L1"
    if action == "BLOCK_CARD":
        return "L1" if exposure <= BLOCK_L1_MAX else "L2"
    return "L2"  # BLOCK_ALL_CARDS, FILE_REPORT


def should_open_case(prob: float, requested_evidence: bool, disputed: bool) -> bool:
    """Policy 3a: open a case at p >= 0.30, when asking for evidence, or on a dispute."""
    return prob >= CASE_MIN_PROB or requested_evidence or disputed


def should_file_report(prob_fraud: float, exposure: float,
                       shared_link: bool, coordinated_or_undocumented: bool,
                       strong_threshold: float = 0.70) -> bool:
    """Policy 3a: confirmed/strongly suspected AND at least one trigger.
    strong_threshold is OUR choice; the policy doesn't define 'strongly suspected'."""
    strongly = prob_fraud >= strong_threshold
    trigger = (exposure > REPORT_MIN_EXPOSURE) or shared_link or coordinated_or_undocumented
    return strongly and trigger


def can_block_all(confirmed_fraud_cards: int, credentials_compromised: bool) -> bool:
    """R10."""
    return confirmed_fraud_cards >= 2 or credentials_compromised


def may_block_on_single_signal(prob: float, single_signal: bool) -> bool:
    """R1: a single signal below 0.70 must be verified, not blocked."""
    return not (single_signal and prob < VERIFY_BELOW_PROB)


def can_stop(prob: float, independent_evidence: int, verification_settled: bool,
             no_further_value: bool) -> tuple[bool, str]:
    """Policy section 6."""
    if (prob >= 0.85 or prob <= 0.15) and independent_evidence >= 2:
        return True, f"probability {prob:.2f} with {independent_evidence} independent pieces of evidence"
    if verification_settled:
        return True, "verification response settled the question"
    if no_further_value:
        return True, "further steps unlikely to change the decision"
    return False, ""


@dataclass
class Recommendation:
    action: str
    route: str
    reason: str


def recommend(action: str, reason: str, exposure: float = 0.0) -> Recommendation:
    return Recommendation(action, route(action, exposure), reason)