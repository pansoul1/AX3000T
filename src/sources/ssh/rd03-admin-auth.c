/* Use the vendor's current admin password for this Dropbear instance only. SPDX-License-Identifier: 0BSD */
#define _POSIX_C_SOURCE 200809L
#include <string.h>
#ifdef RD03_AUTH_TEST
#include <stdlib.h>
struct spwd { char *sp_namp; char *sp_pwdp; long sp_lstchg, sp_min, sp_max, sp_warn, sp_inact, sp_expire; unsigned long sp_flag; };
static int (*test_verifier)(const char *) = NULL;
void rd03_set_test_verifier(int (*verifier)(const char *)) { test_verifier = verifier; }
#else
#include <shadow.h>
#include <unistd.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <errno.h>
#include <stdlib.h>
#include <signal.h>
#endif

static char marker[] = "$rd03-web-admin$";
static char denied[] = "$rd03-auth-denied$";
static struct spwd root_entry = {
    .sp_namp = "root", .sp_pwdp = marker, .sp_lstchg = 1, .sp_min = 0,
    .sp_max = 99999, .sp_warn = 7, .sp_inact = -1, .sp_expire = -1,
    .sp_flag = (unsigned long)-1
};

#ifndef RD03_AUTH_TEST
/* Loaded hooks survive fork; prevent this loader setting from reaching login shells. */
__attribute__((constructor)) static void private_loader_environment(void) {
    unsetenv("LD_PRELOAD");
}
#endif

/* No persistent shadow modification; the override is private to Dropbear's loader. */
struct spwd *getspnam(const char *name) {
    return name && !strcmp(name, "root") ? &root_entry : NULL;
}

static int vendor_check(const char *candidate) {
    size_t size = candidate ? strlen(candidate) : 0;
    if (!size || size > 256) return 0;
#ifdef RD03_AUTH_TEST
    return test_verifier && test_verifier(candidate) == 1;
#else
    int input[2]; if (pipe(input)) return 0;
    pid_t child = fork();
    if (child < 0) { close(input[0]); close(input[1]); return 0; }
    if (!child) {
        close(input[1]);
        if (dup2(input[0], STDIN_FILENO) < 0) _exit(126);
        if (input[0] != STDIN_FILENO) close(input[0]);
        int quiet = open("/dev/null", O_WRONLY);
        if (quiet < 0 || dup2(quiet, STDOUT_FILENO) < 0 || dup2(quiet, STDERR_FILENO) < 0) _exit(126);
        if (quiet > STDERR_FILENO) close(quiet);
        /* Do not apply this shim to Lua or any child command. Password is only on stdin. */
        if (unsetenv("LD_PRELOAD")) _exit(126);
        signal(SIGALRM, SIG_DFL); alarm(5);
        execl("/usr/bin/lua", "lua", "/usr/libexec/rd03-admin-check.lua", (char *)NULL);
        _exit(127);
    }
    close(input[0]);
    void (*old_sigpipe)(int) = signal(SIGPIPE, SIG_IGN);
    size_t done = 0;
    while (done < size) {
        ssize_t n = write(input[1], candidate + done, size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        done += (size_t)n;
    }
    close(input[1]);
    if(old_sigpipe != SIG_ERR) signal(SIGPIPE, old_sigpipe);
    int status;
    while (waitpid(child, &status, 0) < 0) { if (errno != EINTR) return 0; }
    return done == size && WIFEXITED(status) && WEXITSTATUS(status) == 0;
#endif
}

/* The marker can only be produced by the root getspnam override above. Fail closed otherwise. */
char *crypt(const char *candidate, const char *setting) {
    return setting && !strcmp(setting, marker) && vendor_check(candidate) ? marker : denied;
}
