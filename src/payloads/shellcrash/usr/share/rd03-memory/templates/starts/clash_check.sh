
clash_check() { #clash启动前检查
    #检测vless/hysteria协议
    [ "$crashcore" != "meta" ] && [ -n "$(cat $core_config | grep -oE 'type: vless|type: hysteria')" ] && core_exchange meta 'vless/hy协议'
    #检测是否存在高级版规则或者tun模式
    if [ "$crashcore" = "clash" ]; then
        [ -n "$(cat $core_config | grep -aiE '^script:|proxy-providers|rule-providers|rule-set')" ] ||
            [ "$redir_mod" = "混合模式" ] ||
            [ "$redir_mod" = "Tun模式" ] && core_exchange meta '当前内核不支持的配置'
    fi
    [ "$crashcore" = "clash" ] && [ "$firewall_area" = 2 -o "$firewall_area" = 3 ] && [ -z "$(grep '0:7890' /etc/passwd)" ] &&
        core_exchange meta '当前内核不支持非root用户启用本机代理'
    check_core || return 1
    # Compact local rules are selected by rd03-prepare-config. No full geodata download.
    return 0
}
