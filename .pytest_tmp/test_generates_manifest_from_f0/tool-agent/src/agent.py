from langchain.tools import tool

@tool
def search_documents(query: str) -> str:
    """Search the document database."""
    return f"Results for: {query}"

@tool
def write_report(content: str) -> str:
    """Write a report to disk."""
    with open("report.txt", "w") as f:
        f.write(content)
    return "Report written"

def main():
    result = search_documents("test query")
    write_report(result)

if __name__ == "__main__":
    main()
