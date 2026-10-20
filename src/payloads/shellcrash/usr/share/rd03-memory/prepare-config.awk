# Buffer this small YAML so provider insertion can depend on the whole rule list.
function provider_ip(indent) {
    return indent "rd03-cn-ip: {type: file, behavior: ipcidr, format: mrs, path: /usr/share/rd03-memory/rules/cn-ip.mrs}"
}
function provider_cn(indent) {
    return indent "cn: {type: file, behavior: domain, format: mrs, path: /usr/share/rd03-memory/rules/cn-domain.mrs}"
}
{
    lines[NR]=$0
    if ($0 ~ /^[ \t]*#/) next
    value=$0; sub(/^[ \t]*-[ \t]*/,"",value); sub(/[ \t]*$/,"",value)
    if (value=="GEOIP,CN,DIRECT" || value=="'GEOIP,CN,DIRECT'" || value=="\"GEOIP,CN,DIRECT\"") count++
    if (value=="RULE-SET,rd03-cn-ip,DIRECT" || value=="'RULE-SET,rd03-cn-ip,DIRECT'" || value=="\"RULE-SET,rd03-cn-ip,DIRECT\"") converted++
    if ($0 ~ /^rule-providers:/) {
        providers++
        if ($0 !~ /^rule-providers:[ \t]*$/) bad=1
    }
    if ($0 ~ /^[ \t]+rd03-cn-ip:/) {
        reserved++
        if ($0 !~ /^[ \t]+rd03-cn-ip: \{type: file, behavior: ipcidr, format: mrs, path: \/(data\/rd03-memory|usr\/share\/rd03-memory)\/rules\/cn-ip\.mrs\}[ \t]*$/) bad=1
    }
}
END {
    if (bad || count>1 || converted>1 || count+converted>1 || providers>1 || reserved>1 || (reserved && !converted)) exit 9
    use_ip=(count+converted==1)
    inproviders=0
    for (i=1;i<=NR;i++) {
        text=lines[i]
        if (text ~ /^[ \t]*#/) {print text; continue}
        if (text ~ /^[a-zA-Z][a-zA-Z0-9_-]*:/) inproviders=0
        if (text ~ /^rule-providers:/) {
            inproviders=1; print text
            if (use_ip && !reserved) print provider_ip("  ")
            continue
        }
        if (inproviders && text ~ /^[ \t]+rd03-cn-ip:/) {
            match(text,/^[ \t]+/); print provider_ip(substr(text,1,RLENGTH)); continue
        }
        if (inproviders && text ~ /^[ \t]+cn: \{type: http, behavior: domain, format: mrs, path: \.\/ruleset\/cn\.mrs, url: https:\/\/testingcf\.jsdelivr\.net\/gh\/juewuy\/ShellCrash@update\/bin\/geodata\/mrs_geosite_cn\.mrs\}[ \t]*$/) {
            match(text,/^[ \t]+/); print provider_cn(substr(text,1,RLENGTH)); continue
        }
        if (inproviders && text ~ /^[ \t]+cn: \{type: file, behavior: domain, format: mrs, path: \/(data\/rd03-memory|usr\/share\/rd03-memory)\/rules\/cn-domain\.mrs\}[ \t]*$/) {
            match(text,/^[ \t]+/); print provider_cn(substr(text,1,RLENGTH)); continue
        }
        if (text ~ /^[ \t]+fallback-filter:[ \t]*\{.*\}[ \t]*$/) {
            sub(/geoip:[ \t]*true/,"geoip: false",text)
            sub(/geosite:[ \t]*\[[^]]*\]/,"geosite: []",text)
        }
        value=text; sub(/^[ \t]*-[ \t]*/,"",value); sub(/[ \t]*$/,"",value)
        if (value=="GEOIP,CN,DIRECT" || value=="'GEOIP,CN,DIRECT'" || value=="\"GEOIP,CN,DIRECT\"") sub(/GEOIP,CN,DIRECT/,"RULE-SET,rd03-cn-ip,DIRECT",text)
        print text
    }
    if (use_ip && !providers) {print "rule-providers:"; print provider_ip("  ")}
}
