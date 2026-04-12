package main
import "os"
func main() {
    key := os.Getenv("API_KEY")
    _ = key
}
