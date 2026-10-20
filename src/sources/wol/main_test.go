package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestNormalizeMAC(t *testing.T) {
	good := []string{"02:11:22:33:44:55", "02-11-22-33-44-55", "021122334455"}
	for _, in := range good {
		got, _, err := normalizeMAC(in)
		if err != nil || got != "02:11:22:33:44:55" {
			t.Fatalf("normalizeMAC(%q) = %q, %v", in, got, err)
		}
	}
	for _, in := range []string{"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff", "01:11:22:33:44:55", "bad", " 02:11:22:33:44:55"} {
		if _, _, err := normalizeMAC(in); err == nil {
			t.Errorf("normalizeMAC(%q) accepted invalid address", in)
		}
	}
}

func TestMagicPacket(t *testing.T) {
	_, mac, _ := normalizeMAC("02:11:22:33:44:55")
	p, err := magicPacket(mac)
	if err != nil || len(p) != 102 || !bytes.Equal(p[:6], bytes.Repeat([]byte{0xff}, 6)) || !bytes.Equal(p[6:], bytes.Repeat(mac, 16)) {
		t.Fatalf("invalid packet: len=%d err=%v", len(p), err)
	}
}

func TestRequestLimits(t *testing.T) {
	if _, err := parseRequest("POST", strings.Repeat("x", 1025)); err == nil {
		t.Fatal("oversized query accepted")
	}
	if _, err := parseRequest("GET", "x=1"); err == nil {
		t.Fatal("GET query accepted")
	}
	if _, err := parseRequest("POST", "action=save&action=wake"); err == nil {
		t.Fatal("duplicate action accepted")
	}
}

func TestAppCRUDAndCSRF(t *testing.T) {
	dir := t.TempDir()
	a := app{dataDir: filepath.Join(dir, "data"), tmpDir: filepath.Join(dir, "tmp"), now: func() time.Time { return time.Unix(100, 0) }, random: bytes.NewReader(bytes.Repeat([]byte{0xab}, 32))}
	get := a.handle("GET", "")
	if get.Code != 0 || len(get.CSRF) != 64 || len(get.Devices) != 0 {
		t.Fatalf("GET: %#v", get)
	}
	bad := a.handle("POST", "action=save&csrf=wrong&mac=02%3A11%3A22%3A33%3A44%3A55&name=pc")
	if bad.Code == 0 {
		t.Fatal("bad csrf accepted")
	}
	q := "action=save&csrf=" + get.CSRF + "&mac=02%3A11%3A22%3A33%3A44%3A55&name=pc"
	saved := a.handle("POST", q)
	if saved.Code != 0 || len(saved.Devices) != 1 {
		t.Fatalf("save: %#v", saved)
	}
	a.send = func(net.HardwareAddr) error { return nil }
	woke := a.handle("POST", "action=wake&csrf="+get.CSRF+"&mac=02%3A11%3A22%3A33%3A44%3A55")
	if woke.Code != 0 || woke.Message != "唤醒包已发送" || woke.Devices[0].LastSent != 100 {
		t.Fatalf("wake: %#v", woke)
	}
	deleted := a.handle("POST", "action=delete&csrf="+get.CSRF+"&mac=02%3A11%3A22%3A33%3A44%3A55")
	if deleted.Code != 0 || len(deleted.Devices) != 0 {
		t.Fatalf("delete: %#v", deleted)
	}
	b, err := os.ReadFile(filepath.Join(a.dataDir, "devices.json"))
	if err != nil {
		t.Fatal(err)
	}
	var state state
	if json.Unmarshal(b, &state) != nil || len(state.Devices) != 0 {
		t.Fatalf("bad persisted state: %s", b)
	}
}

func TestSelftestNoIO(t *testing.T) {
	r := selftest()
	if r.Code != 0 || !r.Selftest {
		t.Fatalf("selftest: %#v", r)
	}
	if _, err := io.ReadAll(strings.NewReader(r.Message)); err != nil {
		t.Fatal(err)
	}
}

func TestFailedWakePreservesLastSent(t *testing.T) {
	dir := t.TempDir()
	a := app{dataDir: filepath.Join(dir, "data"), tmpDir: filepath.Join(dir, "tmp"), now: func() time.Time { return time.Unix(100, 0) }, random: bytes.NewReader(bytes.Repeat([]byte{0xab}, 32))}
	get := a.handle("GET", "")
	q := "&csrf=" + get.CSRF + "&mac=02%3A11%3A22%3A33%3A44%3A55"
	if r := a.handle("POST", "action=save"+q+"&name=pc"); r.Code != 0 {
		t.Fatal(r)
	}
	a.send = func(net.HardwareAddr) error { return errors.New("injected send failure") }
	if r := a.handle("POST", "action=wake"+q); r.Code != 6 {
		t.Fatal(r)
	}
	if r := a.handle("GET", ""); r.Code != 0 || r.Devices[0].LastSent != 0 {
		t.Fatal(r)
	}
}

func TestCorruptStoragePreserved(t *testing.T) {
	dir := t.TempDir()
	a := app{dataDir: filepath.Join(dir, "data"), tmpDir: filepath.Join(dir, "tmp"), now: time.Now, random: bytes.NewReader(bytes.Repeat([]byte{0xab}, 32))}
	if r := a.handle("GET", ""); r.Code != 0 {
		t.Fatal(r)
	}
	path := filepath.Join(a.dataDir, "devices.json")
	corrupt := []byte("{broken")
	if err := os.WriteFile(path, corrupt, 0600); err != nil {
		t.Fatal(err)
	}
	if r := a.handle("GET", ""); r.Code != 3 {
		t.Fatal(r)
	}
	got, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(got, corrupt) {
		t.Fatal("corrupt state was changed")
	}
}

func TestEmptyDevicesSerialized(t *testing.T) {
	b, err := json.Marshal(success(state{}, "token", ""))
	if err != nil || !bytes.Contains(b, []byte(`"devices":[]`)) {
		t.Fatalf("empty list omitted: %s, %v", b, err)
	}
}

func TestUnlistedDeviceCannotWake(t *testing.T) {
	dir := t.TempDir()
	sent := false
	a := app{dataDir: filepath.Join(dir, "data"), tmpDir: filepath.Join(dir, "tmp"), now: time.Now, random: bytes.NewReader(bytes.Repeat([]byte{0xab}, 32)), send: func(net.HardwareAddr) error { sent = true; return nil }}
	get := a.handle("GET", "")
	r := a.handle("POST", "action=wake&csrf="+get.CSRF+"&mac=02%3A11%3A22%3A33%3A44%3A55")
	if r.Code != 2 || sent {
		t.Fatalf("unlisted device wake: %#v, sent=%v", r, sent)
	}
}
