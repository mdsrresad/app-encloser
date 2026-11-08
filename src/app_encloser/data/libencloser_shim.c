#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <spawn.h>
#include <unistd.h>

static int (*real_execve)(const char *pathname, char *const argv[], char *const envp[]) = NULL;
static int (*real_posix_spawn)(pid_t *pid, const char *path, const posix_spawn_file_actions_t *file_actions,
                              const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) = NULL;
static int (*real_posix_spawnp)(pid_t *pid, const char *file, const posix_spawn_file_actions_t *file_actions,
                               const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) = NULL;

static const char* check_redirect(const char* path) {
    if (!path) return path;
    if (strstr(path, "nft") != NULL) {
        const char *shim = getenv("ENCLOSER_NFT_SHIM");
        if (shim && access(shim, X_OK) == 0) {
            return shim;
        }
    }
    return path;
}

int execve(const char *pathname, char *const argv[], char *const envp[]) {
    if (!real_execve) real_execve = dlsym(RTLD_NEXT, "execve");
    return real_execve(check_redirect(pathname), argv, envp);
}

int execv(const char *path, char *const argv[]) {
    int (*real_execv)(const char *, char *const[]) = dlsym(RTLD_NEXT, "execv");
    return real_execv(check_redirect(path), argv);
}

int execvp(const char *file, char *const argv[]) {
    int (*real_execvp)(const char *, char *const[]) = dlsym(RTLD_NEXT, "execvp");
    return real_execvp(check_redirect(file), argv);
}

int posix_spawn(pid_t *pid, const char *path, const posix_spawn_file_actions_t *file_actions,
                const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) {
    if (!real_posix_spawn) real_posix_spawn = dlsym(RTLD_NEXT, "posix_spawn");
    return real_posix_spawn(pid, check_redirect(path), file_actions, attrp, argv, envp);
}

int posix_spawnp(pid_t *pid, const char *file, const posix_spawn_file_actions_t *file_actions,
                 const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) {
    if (!real_posix_spawnp) real_posix_spawnp = dlsym(RTLD_NEXT, "posix_spawnp");
    return real_posix_spawnp(pid, check_redirect(file), file_actions, attrp, argv, envp);
}
