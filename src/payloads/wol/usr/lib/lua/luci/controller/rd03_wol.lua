module("luci.controller.rd03_wol", package.seeall)

function index()
    -- LuCI's disk/fast index reloads this function without captured locals.
    -- Keep registration self contained; no module-local helper upvalues here.
    local page = entry({"web", "rd03wol"}, call("action_page"), nil)
    page.sysauth = "admin"
    page.sysauth_authenticator = "htmlauth"
    local api = entry({"web", "rd03wol", "api"}, call("action_api"), nil)
    api.sysauth = "admin"
    api.sysauth_authenticator = "htmlauth"
    api.leaf = true
end

local function reply(status, value)
    local http = require("luci.http")
    http.status(status)
    http.header("Cache-Control", "no-store")
    http.prepare_content("application/json; charset=utf-8")
    http.write(require("luci.json").encode(value))
end

local function encode(value)
    return (value:gsub("([^%w%-_%.~])", function(c)
        return string.format("%%%02X", string.byte(c))
    end))
end

-- Run one fixed executable. Form values are passed as one encoded argument;
-- they never become shell syntax or a command line to a shell.
local function run_backend(arguments)
    local nixio = require("nixio")
    local reader, writer = nixio.pipe()
    if not reader or not writer then
        return nil
    end
    local pid = nixio.fork()
    if pid == 0 then
        reader:close()
        nixio.dup(writer, nixio.stdout)
        writer:close()
        nixio.exec("/usr/libexec/rd03-wol-api", "--luci", unpack(arguments))
        os.exit(127)
    end
    writer:close()
    if not pid then
        reader:close()
        return nil
    end
    local parts, size = {}, 0
    while true do
        local part = reader:read(4096)
        if not part or #part == 0 then
            break
        end
        size = size + #part
        if size > 16384 then
            reader:close()
            nixio.waitpid(pid)
            return nil
        end
        parts[#parts + 1] = part
    end
    reader:close()
    local _, kind, code = nixio.waitpid(pid)
    if kind ~= "exited" or code ~= 0 then
        return nil
    end
    return table.concat(parts)
end

local function is_admin()
    local context = require("luci.dispatcher").context
    return context.authuser == "admin"
        and type(context.authsession) == "string"
        and #context.authsession > 0
end

function action_page()
    if not is_admin() then
        local http = require("luci.http")
        http.status(403)
        http.write("Forbidden")
        return
    end
    require("luci.template").render("web/rd03wol")
end

function action_api()
    local http = require("luci.http")
    if not is_admin() then
        reply(403, {code = 403, message = "请先登录小米后台。"})
        return
    end

    local method = http.getenv("REQUEST_METHOD") or ""
    if method ~= "GET" and method ~= "POST" then
        reply(405, {code = 405, message = "不支持此请求方式。"})
        return
    end
    if method == "POST" then
        local length = tonumber(http.getenv("CONTENT_LENGTH") or "")
        if not length or length <= 0 or length > 1024 then
            reply(400, {code = 400, message = "请求过长或格式错误。"})
            return
        end
    end

    local arguments = {method}
    if method == "POST" then
        local parts = {}
        for _, key in ipairs({"action", "csrf", "mac", "name"}) do
            local value = http.formvalue(key)
            if value ~= nil then
                if type(value) ~= "string" or #value > 256 then
                    reply(400, {code = 400, message = "参数错误。"})
                    return
                end
                parts[#parts + 1] = key .. "=" .. encode(value)
            end
        end
        arguments[2] = table.concat(parts, "&")
    end

    local raw = run_backend(arguments)
    if not raw then
        reply(503, {code = 503, message = "唤醒服务暂时不可用。"})
        return
    end
    local valid, result = pcall(require("luci.json").decode, raw)
    if not valid or type(result) ~= "table" or tonumber(result.code) == nil then
        reply(503, {code = 503, message = "唤醒服务返回错误。"})
        return
    end
    reply(200, result)
end
