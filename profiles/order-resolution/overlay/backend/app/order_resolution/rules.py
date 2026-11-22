import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.domain.errors import InvalidInput


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise InvalidInput(f"{name} must be a non-empty string of at most 128 characters.")
    return value


class OrderResolutionRules:
    """Validate synthetic inputs and calculate one authoritative proposal."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise InvalidInput("The payload must be a JSON object.")
        order = payload.get("order")
        evidence = payload.get("policy_evidence")
        if not isinstance(order, dict):
            raise InvalidInput("order must be a JSON object.")
        if not isinstance(evidence, list):
            raise InvalidInput("policy_evidence must be a JSON array.")

        order_id = _required_string(order.get("id"), "order.id")
        issue = _required_string(order.get("issue"), "order.issue")
        currency = _required_string(order.get("currency"), "order.currency")
        amount_value = order.get("amount")
        if not isinstance(amount_value, str):
            raise InvalidInput("order.amount must be a decimal string.")
        try:
            amount = Decimal(amount_value)
        except InvalidOperation as exc:
            raise InvalidInput("order.amount must be a decimal string.") from exc
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise InvalidInput("order.amount must be a positive two-decimal amount.")
        if currency != "USD":
            raise InvalidInput("Only USD is supported by the synthetic profile.")

        if issue == "late_delivery":
            delay_days = order.get("delay_days")
            if not isinstance(delay_days, int) or isinstance(delay_days, bool) or delay_days <= 3:
                raise InvalidInput("late_delivery requires an integer delay_days greater than 3.")
            policy_id = "POLICY-LATE@1"
            action = "partial_refund_10"
            action_amount = (amount * Decimal("0.10")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            approval_required = amount >= Decimal("100.00")
            reason_codes = ["late_delivery_over_3_days"]
        elif issue == "damaged_item":
            if "delay_days" in order:
                raise InvalidInput("damaged_item does not accept delay_days.")
            delay_days = None
            policy_id = "POLICY-DAMAGED@1"
            action = "replacement_shipment"
            action_amount = None
            approval_required = True
            reason_codes = ["damaged_item"]
        else:
            raise InvalidInput("The issue is not supported by this Order Resolution profile.")

        normalized_order: dict[str, object] = {
            "id": order_id,
            "amount": f"{amount:.2f}",
            "currency": currency,
            "issue": issue,
        }
        if delay_days is not None:
            normalized_order["delay_days"] = delay_days
        if not evidence:
            return self._failure(normalized_order, [], "policy_evidence_missing")
        if len(evidence) != 1:
            return self._failure(normalized_order, evidence, "policy_evidence_conflict")
        item = evidence[0]
        if not isinstance(item, dict):
            return self._failure(normalized_order, evidence, "policy_evidence_invalid")
        if (
            item.get("policy") != policy_id
            or item.get("current") is not True
            or item.get("applicable") is not True
            or item.get("digest_valid") is not True
        ):
            return self._failure(normalized_order, evidence, "policy_evidence_invalid")
        normalized_evidence = {
            "policy": policy_id,
            "current": True,
            "applicable": True,
            "digest_valid": True,
        }
        policy_evidence_digest = hashlib.sha256(_canonical([normalized_evidence])).hexdigest()
        input_digest = hashlib.sha256(
            _canonical({"order": normalized_order, "policy_evidence": [normalized_evidence]})
        ).hexdigest()
        proposal: dict[str, object] = {
            "version": 1,
            "input_digest": input_digest,
            "policy_id": policy_id,
            "policy_evidence_digest": policy_evidence_digest,
            "action": action,
            "destination_id": (
                "synthetic-refund" if action == "partial_refund_10" else "synthetic-fulfillment"
            ),
            "approval_required": approval_required,
            "reason_codes": reason_codes,
        }
        if action_amount is not None:
            proposal["amount"] = f"{action_amount:.2f}"
            proposal["currency"] = currency
        normalized = {
            "order": normalized_order,
            "policy_evidence": [normalized_evidence],
            "proposal": proposal,
        }
        if len(_canonical(normalized)) > 16_384:
            raise InvalidInput("The payload exceeds the 16 KiB limit.")
        return normalized

    @staticmethod
    def _failure(order: dict[str, object], evidence: list[object], code: str) -> dict[str, Any]:
        normalized = {
            "order": order,
            "policy_evidence": evidence,
            "proposal": None,
            "resolution_failure": code,
        }
        if len(_canonical(normalized)) > 16_384:
            raise InvalidInput("The payload exceeds the 16 KiB limit.")
        return normalized
