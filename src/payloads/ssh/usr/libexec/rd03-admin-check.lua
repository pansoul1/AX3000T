-- Called by the Dropbear-only authentication shim. Candidate arrives on stdin.
-- Stock XQCryptoUtil.sha256 puts its input in a shell command; avoid that path.
-- The fixed OpenSSL process receives password bytes through anonymous pipes.
local MAX_PASSWORD = 256
local SALT = "a2ffa5c9be07488bbb04a3a47d3c5f6a"

local function verify(candidate)
    if not candidate or #candidate == 0 or #candidate > MAX_PASSWORD
        or candidate:find("\0", 1, true) then return false end

    local uci = require("luci.model.uci").cursor()
    if uci:get("xiaoqiang", "common", "INITTED") ~= "YES" then return false end
    local expected = uci:get("account", "common", "admin")
    -- Match the shipped XQSysUtil.getEncryptMode selection exactly.
    local legacy = uci:get("account", "legacy") or "0"
    local algorithm = legacy ~= "0" and "-sha256" or "-sha1"
    local length = algorithm == "-sha256" and 64 or 40
    if type(expected) ~= "string" or #expected ~= length
        or not expected:match("^[0-9a-f]+$") then return false end

    local nixio = require("nixio")
    local input_read, input_write = nixio.pipe()
    if not input_read or not input_write then return false end
    local output_read, output_write = nixio.pipe()
    if not output_read or not output_write then
        input_read:close(); input_write:close()
        return false
    end
    local pid = nixio.fork()
    if not pid then
        input_read:close(); input_write:close()
        output_read:close(); output_write:close()
        return false
    end
    if pid == 0 then
        input_write:close(); output_read:close()
        if not nixio.dup(input_read, nixio.stdin)
            or not nixio.dup(output_write, nixio.stdout) then os.exit(125) end
        input_read:close(); output_write:close()
        local sink = nixio.open("/dev/null", "w")
        if sink then nixio.dup(sink, nixio.stderr); sink:close() end
        nixio.exec("/usr/bin/openssl", "dgst", "-r", algorithm)
        os.exit(125)
    end

    input_read:close(); output_write:close()
    local payload = candidate .. SALT
    local position, wrote = 1, true
    while position <= #payload do
        local count = input_write:write(payload:sub(position))
        if not count or count <= 0 then wrote = false; break end
        position = position + count
    end
    input_write:close()
    payload = nil

    local chunks, size, read_ok = {}, 0, true
    while true do
        local chunk = output_read:read(128)
        if not chunk then read_ok = false; break end
        if #chunk == 0 then break end
        size = size + #chunk
        if size > 256 then read_ok = false; break end
        chunks[#chunks + 1] = chunk
    end
    output_read:close()
    local waited, reason, status = nixio.waitpid(pid)
    if not wrote or not read_ok or waited ~= pid
        or reason ~= "exited" or status ~= 0 then return false end

    local actual = table.concat(chunks):match("^([0-9a-fA-F]+)%s")
    if not actual or #actual ~= length then return false end
    actual = actual:lower()
    -- Compare every byte rather than accepting a prefix or early string match.
    local difference = 0
    for i = 1, length do
        if actual:byte(i) ~= expected:byte(i) then difference = difference + 1 end
    end
    return difference == 0
end

local candidate = io.read(MAX_PASSWORD + 1)
local checked, accepted = pcall(verify, candidate)
candidate = nil
os.exit(checked and accepted == true and 0 or 1)
