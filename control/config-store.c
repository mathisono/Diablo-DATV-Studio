/* Atomically replace a bounded Portsdown config from stdin. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
  if (argc != 2 || argv[1][0] != '/') { fprintf(stderr, "usage: config-store /absolute/path\n"); return 2; }
  char *target = argv[1];
  char *slash = strrchr(target, '/');
  if (!slash || !slash[1]) return 2;
  char *tmp = malloc(strlen(target) + 16);
  if (!tmp) return 1;
  sprintf(tmp, "%s.tmp.XXXXXX", target);
  int fd = mkstemp(tmp);
  if (fd < 0) { perror("mkstemp"); free(tmp); return 1; }
  struct stat original;
  if (stat(target, &original) == 0) {
    if (fchmod(fd, original.st_mode & 0777) < 0) goto fail;
    if (fchown(fd, original.st_uid, original.st_gid) < 0 && errno != EPERM) goto fail;
  } else if (errno != ENOENT) goto fail;
  char buf[4096]; size_t total = 0;
  while (1) {
    ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
    if (n < 0) { if (errno == EINTR) continue; goto fail; }
    if (n == 0) break;
    total += (size_t)n;
    if (total > 65536) { errno = EFBIG; goto fail; }
    for (ssize_t off = 0; off < n;) {
      ssize_t wrote = write(fd, buf + off, (size_t)(n - off));
      if (wrote < 0) { if (errno == EINTR) continue; goto fail; }
      off += wrote;
    }
  }
  if (fsync(fd) < 0 || close(fd) < 0) { fd = -1; goto fail; }
  fd = -1;
  if (rename(tmp, target) < 0) goto fail;
  char *dir = strndup(target, (size_t)(slash - target));
  if (dir) {
    int dirfd = open(*dir ? dir : "/", O_DIRECTORY | O_RDONLY);
    if (dirfd >= 0) { if (fsync(dirfd) < 0) perror("directory fsync"); close(dirfd); }
    free(dir);
  }
  free(tmp); return 0;
fail:
  perror("config-store");
  if (fd >= 0) close(fd);
  unlink(tmp); free(tmp); return 1;
}
