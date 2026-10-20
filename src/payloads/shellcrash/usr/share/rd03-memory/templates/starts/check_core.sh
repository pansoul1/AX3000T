# Embedded core was checksum/version checked by rd03-shellcrash-prepare.
. "$CRASHDIR/configs/command.env"
check_core() {
    [ -L "$TMPDIR/CrashCore" ] && [ "$(readlink "$TMPDIR/CrashCore")" = /usr/libexec/CrashCore ] && [ -x /usr/libexec/CrashCore ] || {
        touch "$CRASHDIR/.start_error"
        echo 'RD03: embedded core is unavailable; startup held.' >&2
        return 1
    }
}
