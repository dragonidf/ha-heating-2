/* Linux-only disposable child fault injector; never linked into runtime code. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int fail_fd(int fd, const char *kind) {
    const char *root = getenv("WP1B_FAULT_ROOT");
    const char *mode = getenv("WP1B_FAULT_KIND");
    char marker[4096], descriptor[64], target[4096];
    if (!root || !mode || strcmp(mode, kind)) return 0;
    snprintf(marker, sizeof(marker), "%s/vfs-fault.enabled", root);
    if (access(marker, F_OK)) return 0;
    snprintf(descriptor, sizeof(descriptor), "/proc/self/fd/%d", fd);
    ssize_t count = readlink(descriptor, target, sizeof(target)-1);
    if (count < 0) return 0;
    target[count] = 0;
    size_t length = strlen(root);
    if (strncmp(target, root, length) || target[length] != '/' ||
        !strstr(target + length, "/control.sqlite3")) return 0;
    const char *message = !strcmp(kind, "sync") ? "WP1B_VFS_EIO\n" : "WP1B_VFS_ENOSPC\n";
    syscall(SYS_write, 2, message, strlen(message));
    errno = !strcmp(kind, "sync") ? EIO : ENOSPC;
    return 1;
}

int fsync(int fd) {
    if (fail_fd(fd, "sync")) return -1;
    int (*next)(int) = dlsym(RTLD_NEXT, "fsync");
    return next(fd);
}
int fdatasync(int fd) {
    if (fail_fd(fd, "sync")) return -1;
    int (*next)(int) = dlsym(RTLD_NEXT, "fdatasync");
    return next(fd);
}
ssize_t pwrite(int fd, const void *buffer, size_t count, off_t offset) {
    if (fail_fd(fd, "full")) return -1;
    ssize_t (*next)(int, const void *, size_t, off_t) = dlsym(RTLD_NEXT, "pwrite");
    return next(fd, buffer, count, offset);
}
ssize_t pwrite64(int fd, const void *buffer, size_t count, off64_t offset) {
    if (fail_fd(fd, "full")) return -1;
    ssize_t (*next)(int, const void *, size_t, off64_t) = dlsym(RTLD_NEXT, "pwrite64");
    return next(fd, buffer, count, offset);
}
