"""Fraud detection agent entry point.

Scans financial transactions in real time and flags anomalies.
Triggered by ``transaction.created`` events.
"""

from __future__ import annotations

from typing import Any


def run(transaction_id: str) -> dict[str, Any]:
    """Analyse a single transaction and return a risk assessment.

    Parameters
    ----------
    transaction_id:
        Unique identifier of the transaction to evaluate.

    Returns
    -------
    dict
        Keys: ``flagged`` (bool), ``risk_score`` (float 0-1),
        ``reason`` (str or None).

    Example integration with LangChain
    -----------------------------------
    .. code-block:: python

        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4o")
        tools = [scan_transaction, flag_transaction, alert_compliance_team]
        agent = create_openai_tools_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools)
        result = executor.invoke({"transaction_id": transaction_id})
    """
    # TODO: implement real analysis logic
    print(f"Analysing transaction {transaction_id}")
    return {"flagged": False, "risk_score": 0.0, "reason": None}


def main() -> None:
    """Run the agent in standalone mode (for local testing)."""
    result = run("txn-example-001")
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
