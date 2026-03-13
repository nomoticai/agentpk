from typing import Optional


def run(invoice_id: Optional[str] = None) -> dict:
    """
    Process a vendor invoice.

    Args:
        invoice_id: The invoice to process. If None, processes the oldest
                    unprocessed invoice in the queue.

    Returns:
        dict with keys: status, invoice_id, action_taken
    """
    return {
        "status": "processed",
        "invoice_id": invoice_id,
        "action_taken": "submitted_for_approval",
    }
