package main

import (
    "fmt"
    "net/http"
)

func main() {
    resp, _ := http.Get("https://api.example.com")
    fmt.Println(resp.StatusCode)
}
