package main

import (
	"fmt"
	"net/http"
	"os"
)

func main() {
	apiKey := os.Getenv("API_KEY")
	resp, err := http.Get("https://api.example.com/data")
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	defer resp.Body.Close()
	fmt.Println("Status:", resp.StatusCode, "Key:", apiKey)
}
