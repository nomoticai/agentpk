"""Fraud detection agent — reads transactions, flags anomalies."""

import os
import json


def scan_transaction(transaction_id: str) -> dict:
    """Read transaction data."""
    return {"id": transaction_id, "amount": 0.0, "merchant": ""}


def flag_transaction(transaction_id: str, reason: str) -> bool:
    """Flag a transaction as suspicious."""
    return True


def alert_compliance_team(message: str) -> bool:
    """Notify compliance team."""
    return True


def main() -> None:
    """Process incoming transaction event."""
    event = json.loads(os.environ.get("TRANSACTION_EVENT", "{}"))
    transaction_id = event.get("transaction_id", "unknown")

    transaction = scan_transaction(transaction_id)

    # Simple threshold check
    if transaction.get("amount", 0) > 10000:
        flag_transaction(transaction_id, "amount_threshold_exceeded")
        alert_compliance_team(
            f"Transaction {transaction_id} flagged: amount threshold exceeded"
        )


if __name__ == "__main__":
    main()
