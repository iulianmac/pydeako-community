"""Helper for sending requests to local integrations."""

import json
from typing import Any
from uuid import uuid4


class _Request:
    """Request to send to local integrations."""

    body: dict[str, Any]

    def __init__(self, body: dict[str, Any]) -> None:
        """Initialize request with its JSON body."""
        self.body = body

    def get_body_str(self) -> str:
        """Get string representation of request."""
        return json.dumps(self.body)

    def get_transaction_id(self) -> str | None:
        """Get the transaction id the device's response will carry."""
        transaction_id: str | None = self.body.get("transactionId")
        return transaction_id

    def with_new_transaction_id(self) -> "_Request":
        """Copy this request with a new transaction id, to send it again."""
        return _Request({**self.body, "transactionId": str(uuid4())})
