#!/bin/sh
CRASHDIR=/data/ShellCrash
mkdir -p /tmp/ShellCrash
touch "$CRASHDIR/.start_error"
[ -f /tmp/ShellCrash/core_test.log ] || printf '%s
' 'RD03: startup failed; no diagnostic core was launched.' > /tmp/ShellCrash/core_test.log
logger -t ShellCrash 'Startup failed. No automatic core retry. See /tmp/ShellCrash/core_test.log.'
"$CRASHDIR/start.sh" stop
