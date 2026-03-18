package main

import "os/exec"

func main() {
    cmd := exec.Command("ls", "-la")
    cmd.Run()
}
