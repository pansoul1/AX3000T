//go:build linux

package main

import (
	"errors"
	"net"
	"os"
	"syscall"
	"time"
)

func acquireLock(path string) (func(), error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	deadline := time.Now().Add(3 * time.Second)
	for {
		err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			return func() { _ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN); f.Close() }, nil
		}
		if (err != syscall.EWOULDBLOCK && err != syscall.EAGAIN) || time.Now().After(deadline) {
			f.Close()
			return nil, err
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func broadcastAddress(ip net.IP, mask net.IPMask) (net.IP, error) {
	ip = ip.To4()
	ones, bits := mask.Size()
	if ip == nil || bits != 32 || ones > 30 || ones < 1 || len(mask) != 4 {
		return nil, errors.New("LAN has no broadcast subnet")
	}
	broadcast := make(net.IP, 4)
	for i := 0; i < 4; i++ {
		broadcast[i] = ip[i] | ^mask[i]
	}
	return broadcast, nil
}

func lanAddresses() (net.IP, net.IP, error) {
	iface, err := net.InterfaceByName(interfaceName)
	if err != nil || iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagBroadcast == 0 {
		return nil, nil, errors.New("LAN interface unavailable")
	}
	addrs, err := iface.Addrs()
	if err != nil {
		return nil, nil, err
	}
	for _, addr := range addrs {
		network, ok := addr.(*net.IPNet)
		if !ok || network.IP.To4() == nil || network.IP.IsLoopback() || network.IP.IsUnspecified() {
			continue
		}
		broadcast, err := broadcastAddress(network.IP, network.Mask)
		if err == nil {
			return network.IP.To4(), broadcast, nil
		}
	}
	return nil, nil, errors.New("LAN IPv4 unavailable")
}

func sendMagic(mac net.HardwareAddr) error {
	packet, err := magicPacket(mac)
	if err != nil {
		return err
	}
	ip, broadcast, err := lanAddresses()
	if err != nil {
		return err
	}
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: ip, Port: 0})
	if err != nil {
		return err
	}
	defer conn.Close()
	raw, err := conn.SyscallConn()
	if err != nil {
		return err
	}
	var socketErr error
	if err := raw.Control(func(fd uintptr) {
		if socketErr = syscall.SetsockoptInt(int(fd), syscall.SOL_SOCKET, syscall.SO_BROADCAST, 1); socketErr == nil {
			socketErr = syscall.SetsockoptString(int(fd), syscall.SOL_SOCKET, syscall.SO_BINDTODEVICE, interfaceName)
		}
	}); err != nil {
		return err
	}
	if socketErr != nil {
		return socketErr
	}
	if err := conn.SetWriteDeadline(time.Now().Add(2 * time.Second)); err != nil {
		return err
	}
	for i := 0; i < 3; i++ {
		n, err := conn.WriteToUDP(packet, &net.UDPAddr{IP: broadcast, Port: 9})
		if err != nil {
			return err
		}
		if n != len(packet) {
			return errors.New("short datagram")
		}
		if i != 2 {
			time.Sleep(15 * time.Millisecond)
		}
	}
	return nil
}
