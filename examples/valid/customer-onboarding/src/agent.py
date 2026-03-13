"""Customer onboarding agent entry point.

Guides new customers through account setup and verification.
Triggered by ``customer.signup`` events.
"""

from __future__ import annotations

from typing import Any


def run(customer_id: str) -> dict[str, Any]:
    """Execute the onboarding workflow for a single customer.

    Parameters
    ----------
    customer_id:
        Unique identifier of the customer who just signed up.

    Returns
    -------
    dict
        Keys: ``status`` (str), ``steps_completed`` (list[str]),
        ``welcome_sent`` (bool).

    Example integration with LangChain
    -----------------------------------
    .. code-block:: python

        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4o")
        tools = [read_customer_record, update_onboarding_status, send_welcome_email]
        agent = create_openai_tools_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools)
        result = executor.invoke({"customer_id": customer_id})
    """
    # TODO: implement real onboarding logic
    print(f"Onboarding customer {customer_id}")
    return {
        "status": "pending",
        "steps_completed": [],
        "welcome_sent": False,
    }


def main() -> None:
    """Run the agent in standalone mode (for local testing)."""
    result = run("cust-example-001")
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
