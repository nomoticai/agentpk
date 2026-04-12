from langchain.tools import tool

@tool
def search_docs(query: str) -> str:
    return "results"
