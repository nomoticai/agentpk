package main
import "os"
func main() {
    f, _ := os.Create("output.txt")
    f.Close()
    data, _ := os.ReadFile("input.txt")
    _ = data
}
