//go:build windows

// Windows supports offline host tests only; no Wake-on-LAN packet is sent here.
package main

import (
	"errors"
	"net"
	"os"
	"time"
)

func acquireLock(path string) (func(), error) {
	path += ".host-test"
	deadline := time.Now().Add(3 * time.Second)
	for {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err == nil {
			return func() { f.Close(); os.Remove(path) }, nil
		}
		if !os.IsExist(err) || time.Now().After(deadline) {
			return nil, err
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func sendMagic(mac net.HardwareAddr) error { return errors.New("Linux router required") }
