// rd03-wol-api is a short-lived backend called by an authenticated LuCI handler.
// It never starts a listener and accepts no paths or executable names from callers.
package main

import (
	"bytes"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

const interfaceName = "br-lan"
const maxStateBytes = 65536

type device struct {
	Name     string `json:"name"`
	MAC      string `json:"mac"`
	LastSent int64  `json:"last_sent,omitempty"`
}

type state struct {
	Version int      `json:"version"`
	Devices []device `json:"devices"`
}

type response struct {
	Code      int      `json:"code"`
	Message   string   `json:"message,omitempty"`
	CSRF      string   `json:"csrf,omitempty"`
	Devices   []device `json:"devices"`
	Interface string   `json:"interface,omitempty"`
	Selftest  bool     `json:"selftest,omitempty"`
}

type app struct {
	dataDir string
	tmpDir  string
	now     func() time.Time
	random  io.Reader
	send    func(net.HardwareAddr) error
}

func newApp() app {
	return app{dataDir: "/data/rd03-wol", tmpDir: "/tmp/rd03-wol", now: time.Now, random: rand.Reader, send: sendMagic}
}

func main() {
	var r response
	args := os.Args[1:]
	if len(args) == 1 && args[0] == "--selftest" {
		r = selftest()
	} else if len(args) >= 2 && len(args) <= 3 && args[0] == "--luci" {
		q := ""
		if len(args) == 3 {
			q = args[2]
		}
		a := newApp()
		r = a.handle(args[1], q)
	} else {
		r = failure(1, "调用参数无效")
	}
	// All API outcomes use JSON and exit zero; the caller can reliably parse code.
	if err := json.NewEncoder(os.Stdout).Encode(r); err != nil {
		os.Exit(1)
	}
}

func failure(code int, message string) response { return response{Code: code, Message: message} }

func normalizeMAC(value string) (string, net.HardwareAddr, error) {
	if len(value) > 32 || strings.TrimSpace(value) != value {
		return "", nil, errors.New("invalid MAC")
	}
	mac, err := net.ParseMAC(value)
	if err != nil || len(mac) != 6 || mac[0]&1 != 0 {
		return "", nil, errors.New("invalid MAC")
	}
	zero := true
	for _, b := range mac {
		zero = zero && b == 0
	}
	if zero {
		return "", nil, errors.New("invalid MAC")
	}
	return strings.ToUpper(mac.String()), mac, nil
}

func validName(value string) bool {
	if !utf8.ValidString(value) || value != strings.TrimSpace(value) {
		return false
	}
	n := utf8.RuneCountInString(value)
	if n < 1 || n > 64 {
		return false
	}
	for _, r := range value {
		if unicode.IsControl(r) {
			return false
		}
	}
	return true
}

func magicPacket(mac net.HardwareAddr) ([]byte, error) {
	if len(mac) != 6 {
		return nil, errors.New("invalid MAC length")
	}
	packet := make([]byte, 102)
	for i := 0; i < 6; i++ {
		packet[i] = 0xff
	}
	for i := 6; i < len(packet); i += 6 {
		copy(packet[i:i+6], mac)
	}
	return packet, nil
}

func parseRequest(method, query string) (url.Values, error) {
	if method == "GET" {
		if query != "" {
			return nil, errors.New("unexpected query")
		}
		return nil, nil
	}
	if method != "POST" || len(query) == 0 || len(query) > 1024 {
		return nil, errors.New("invalid method or length")
	}
	v, err := url.ParseQuery(query)
	if err != nil {
		return nil, err
	}
	for key, values := range v {
		if key != "action" && key != "csrf" && key != "mac" && key != "name" {
			return nil, errors.New("unknown parameter")
		}
		if len(values) != 1 || len(values[0]) > 256 {
			return nil, errors.New("duplicate or large parameter")
		}
	}
	if v.Get("action") != "save" && v.Get("action") != "delete" && v.Get("action") != "wake" {
		return nil, errors.New("unknown action")
	}
	return v, nil
}

func (a app) handle(method, query string) response {
	v, err := parseRequest(method, query)
	if err != nil {
		return failure(2, "请求参数无效")
	}
	if err := ensureDirectory(a.dataDir); err != nil {
		return failure(3, "无法访问设备记录目录")
	}
	unlock, err := acquireLock(filepath.Join(a.dataDir, ".lock"))
	if err != nil {
		return failure(3, "服务正忙，请稍后重试")
	}
	defer unlock()
	if err := ensureDirectory(a.tmpDir); err != nil {
		return failure(3, "无法初始化临时目录")
	}
	csrf, err := a.csrfToken()
	if err != nil {
		return failure(3, "无法初始化请求令牌")
	}
	s, err := readState(filepath.Join(a.dataDir, "devices.json"))
	if err != nil {
		return failure(3, "设备记录损坏或不可读，未修改原文件")
	}
	if method == "GET" {
		return success(s, csrf, "")
	}
	if len(v.Get("csrf")) != len(csrf) || subtle.ConstantTimeCompare([]byte(v.Get("csrf")), []byte(csrf)) != 1 {
		return failure(4, "页面已失效，请刷新后重试")
	}
	macText, mac, err := normalizeMAC(v.Get("mac"))
	if err != nil {
		return failure(2, "请输入有效的单播 MAC 地址")
	}
	idx := -1
	for i := range s.Devices {
		if s.Devices[i].MAC == macText {
			idx = i
			break
		}
	}
	message := ""
	switch v.Get("action") {
	case "save":
		name := strings.TrimSpace(v.Get("name"))
		if !validName(name) {
			return failure(2, "设备名称需为 1 到 64 个字符，不能包含控制字符")
		}
		if idx >= 0 {
			s.Devices[idx].Name = name
		} else {
			if len(s.Devices) >= 32 {
				return failure(2, "最多保存 32 台设备")
			}
			s.Devices = append(s.Devices, device{Name: name, MAC: macText})
		}
		message = "设备已保存"
	case "delete":
		if idx < 0 {
			return failure(2, "设备不存在")
		}
		s.Devices = append(s.Devices[:idx], s.Devices[idx+1:]...)
		message = "设备已删除"
	case "wake":
		if idx < 0 {
			return failure(2, "请先保存设备")
		}
		now := a.now().Unix()
		if now >= s.Devices[idx].LastSent && now-s.Devices[idx].LastSent < 2 {
			return failure(5, "刚刚已发送，请稍候再试")
		}
		if err := a.send(mac); err != nil {
			return failure(6, "发送失败，请检查路由器的 LAN 接口")
		}
		s.Devices[idx].LastSent = now
		message = "唤醒包已发送"
	}
	data, err := json.Marshal(s)
	if err != nil || atomicWrite(filepath.Join(a.dataDir, "devices.json"), append(data, '\n')) != nil {
		if v.Get("action") == "wake" {
			return failure(3, "唤醒包已发送，但记录保存失败")
		}
		return failure(3, "设备记录保存失败")
	}
	return success(s, csrf, message)
}

func success(s state, csrf, message string) response {
	// A non-nil empty list must be serialized as [] so clients can render it.
	devices := s.Devices
	if devices == nil {
		devices = make([]device, 0)
	}
	return response{Code: 0, CSRF: csrf, Devices: devices, Interface: interfaceName, Message: message}
}

// ensureDirectory rejects symlinks at the protected leaf directory.
func ensureDirectory(path string) error {
	if err := os.MkdirAll(path, 0700); err != nil {
		return err
	}
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("not a directory")
	}
	return os.Chmod(path, 0700)
}

func readLimited(path string, limit int64) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > limit {
		return nil, errors.New("invalid file type or size")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	b, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil || int64(len(b)) > limit {
		return nil, errors.New("file too large")
	}
	return b, nil
}

func readState(path string) (state, error) {
	s := state{Version: 1, Devices: make([]device, 0)}
	b, err := readLimited(path, maxStateBytes)
	if os.IsNotExist(err) {
		return s, nil
	}
	if err != nil {
		return s, err
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(&s); err != nil {
		return s, err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return s, errors.New("trailing data")
	}
	if s.Version != 1 || len(s.Devices) > 32 {
		return s, errors.New("invalid state")
	}
	seen := make(map[string]bool)
	for i, dev := range s.Devices {
		mac, _, err := normalizeMAC(dev.MAC)
		if err != nil || !validName(dev.Name) || dev.LastSent < 0 || seen[mac] {
			return s, errors.New("invalid device")
		}
		seen[mac] = true
		s.Devices[i].MAC = mac
	}
	return s, nil
}

func (a app) csrfToken() (string, error) {
	path := filepath.Join(a.tmpDir, "csrf")
	b, err := readLimited(path, 64)
	if err == nil {
		decoded, decodeErr := hex.DecodeString(string(b))
		if decodeErr == nil && len(decoded) == 32 {
			return string(b), os.Chmod(path, 0600)
		}
		return "", errors.New("invalid token file")
	}
	if !os.IsNotExist(err) {
		return "", err
	}
	var randomBytes [32]byte
	if _, err := io.ReadFull(a.random, randomBytes[:]); err != nil {
		return "", err
	}
	token := hex.EncodeToString(randomBytes[:])
	return token, atomicWrite(path, []byte(token))
}

func atomicWrite(path string, data []byte) (err error) {
	f, err := os.CreateTemp(filepath.Dir(path), ".rd03-wol-*")
	if err != nil {
		return err
	}
	name := f.Name()
	defer func() {
		f.Close()
		os.Remove(name)
	}()
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(data)
	}
	if err == nil {
		err = f.Sync()
	}
	if closeErr := f.Close(); err == nil {
		err = closeErr
	}
	if err == nil {
		err = os.Rename(name, path)
	}
	if err == nil {
		// Persist the directory entry where the platform supports directory fsync.
		if dir, openErr := os.Open(filepath.Dir(path)); openErr == nil {
			_ = dir.Sync()
			dir.Close()
		}
	}
	return err
}

func selftest() response {
	macText, mac, err := normalizeMAC("02:11:22:33:44:55")
	packet, packetErr := magicPacket(mac)
	_, parserErr := parseRequest("POST", "action=wake&csrf=example&mac=02%3A11%3A22%3A33%3A44%3A55")
	if err != nil || packetErr != nil || parserErr != nil || macText != "02:11:22:33:44:55" || len(packet) != 102 || !bytes.Equal(packet[:6], bytes.Repeat([]byte{255}, 6)) || !bytes.Equal(packet[6:], bytes.Repeat(mac, 16)) {
		return failure(7, "内部自检失败")
	}
	return response{Code: 0, Message: fmt.Sprintf("MAC、请求解析及 %d 字节唤醒包自检通过", len(packet)), Selftest: true}
}
