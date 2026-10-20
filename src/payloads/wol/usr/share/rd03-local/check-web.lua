-- Exercise the shipped CGI entry point instead of calling createtree() in an
-- uninitialized CLI context. The real request initializes vendor translation,
-- HTTP context and route-index state in the same order as a browser request.
local ok, err = xpcall(function()
    local ip_pipe = assert(io.popen("/sbin/uci -q get network.lan.ipaddr 2>/dev/null", "r"))
    local ip = (ip_pipe:read("*l") or ""):match("^%s*([%d%.]+)%s*$")
    ip_pipe:close()
    assert(ip and ip:match("^%d+%.%d+%.%d+%.%d+$") and #ip <= 15, "Cannot read the native LAN IPv4 address")
    for octet in ip:gmatch("%d+") do
        assert(tonumber(octet) <= 255, "Invalid native LAN IPv4 address")
    end
    local command = table.concat({
        "env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "REQUEST_METHOD=GET SERVER_PROTOCOL=HTTP/1.1 GATEWAY_INTERFACE=CGI/1.1",
        "SCRIPT_NAME=/cgi-bin/luci SCRIPT_FILENAME=/www/cgi-bin/luci",
        "PATH_INFO=/web/home REQUEST_URI=/cgi-bin/luci/web/home DOCUMENT_ROOT=/www",
        "DOCUMENT_URI=/cgi-bin/luci/web/home",
        "QUERY_STRING= CONTENT_LENGTH=0",
        "SERVER_NAME=miwifi.com SERVER_ADDR=" .. ip .. " SERVER_PORT=80",
        "REMOTE_ADDR=" .. ip .. " REMOTE_PORT=45678 HTTP_HOST=miwifi.com",
        "HTTP_USER_AGENT=RD03-WOL-Check HTTP_ACCEPT=text/html",
        "HTTP_ACCEPT_LANGUAGE=zh-CN HTTP_CONNECTION=close",
        "/usr/bin/lua /www/cgi-bin/luci </dev/null 2>&1"
    }, " ")
    local pipe = assert(io.popen(command, "r"), "Cannot launch the native CGI check")
    local chunks, size = {}, 0
    while true do
        local part = pipe:read(4096)
        if not part then break end
        size = size + #part
        if size > 1048576 then
            pipe:close()
            error("Native CGI check returned more than 1 MiB")
        end
        chunks[#chunks + 1] = part
    end
    pipe:close()
    local response = table.concat(chunks)
    local boundary = response:find("\r\n\r\n", 1, true) or response:find("\n\n", 1, true)
    if not boundary then
        error("Native CGI returned no valid header block:\n" .. response:sub(1, 8192))
    end
    local headers = response:sub(1, boundary)
    local status = tonumber(("\n" .. headers):match("\nStatus:%s*(%d%d%d)")) or 200
    local location = ("\n" .. headers):match("\nLocation:%s*([^\r\n]+)")
    if status ~= 200 and status ~= 302 and status ~= 303 then
        error("Native CGI returned HTTP " .. status .. ":\n" .. response:sub(1, 8192))
    end
    if status == 200 then
        if not headers:lower():find("content%-type:%s*text/html") then
            error("Native CGI returned unexpected content:\n" .. response:sub(1, 8192))
        end
        if not response:lower():find("<html", 1, true) then
            error("Native CGI returned no HTML page:\n" .. response:sub(1, 8192))
        end
    elseif not location then
        error("Native CGI redirect has no Location header")
    end
    io.stdout:write("Native Xiaomi CGI check passed (HTTP ", status, ").\n")

    -- Compile added templates with the native parser. This step does not call
    -- controllers or build a second, incorrectly bootstrapped route tree.
    if arg and arg[1] == "--wol" then
        require("luci.cacheloader")
        _G._ = require("luci.i18n").translate
        local template = require("luci.template")
        template.Template("web/rd03wol")
        template.Template("web/inc/header")
        io.stdout:write("Native WOL template compilation passed.\n")
    end
end, debug.traceback)
if not ok then
    io.stderr:write(tostring(err), "\n")
    os.exit(1)
end
