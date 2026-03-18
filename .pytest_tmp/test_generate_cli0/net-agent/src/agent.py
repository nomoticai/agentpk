import requests
import os

def main():
    api_key = os.environ.get("API_KEY")
    resp = requests.post("https://api.example.com/data", json={"key": api_key})
    return resp.json()

if __name__ == "__main__":
    main()
