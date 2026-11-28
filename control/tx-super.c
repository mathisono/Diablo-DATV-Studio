/* Portsdown process supervisor. No RF backend is enabled by default. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CLIENTS 16
#define LINE 512
#define LOG_LINE 1024

enum role { TX, RX, PREVIEW, SRT1, SRT2, SRT3, SRT4, SRT5, HDMI, PICAM, IPTS, IPCAM1, IPCAM2, SOURCE_TS, ROLE_COUNT };
struct child { pid_t pid; int logfd; char pending[LOG_LINE]; size_t used; };
struct client { int fd; char input[LINE]; size_t used; };

static volatile sig_atomic_t stopping;
static struct child children[ROLE_COUNT];
static struct client clients[CLIENTS];
static const char *role_names[] = { "TX", "RX", "PREVIEW", "SRT1", "SRT2", "SRT3", "SRT4", "SRT5", "HDMI", "PICAM", "IPTS", "IPCAM1", "IPCAM2", "SOURCE_TS" };
static const char *executables[ROLE_COUNT];
static const char *board;
static const char *express_ctrl;
static const char *safe_off_exec;
static const char *sockpath;
static const char *config_path;
static bool slave_mode;
static long long last_peer_hb;

static long long monotonic_ms(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static bool board_config_matches(void)
{
  if (!config_path) return false;
  FILE *file = fopen(config_path, "r");
  if (!file) return false;
  char line[512], configured[64] = "";
  while (fgets(line, sizeof(line), file)) {
    if (strncmp(line, "modeoutput=", 11) != 0) continue;
    char *value = line + 11;
    value[strcspn(value, "\r\n")] = 0;
    if (strlen(value) >= sizeof(configured)) break;
    strcpy(configured, value);
    break;
  }
  fclose(file);
  if (strcmp(board, "express") == 0)
    return strcmp(configured, "DATVEXPRESS") == 0 || strcmp(configured, "DATVEXPRESS_S2") == 0;
  if (strcmp(board, "pluto") == 0) return strcmp(configured, "PLUTO") == 0;
  if (strcmp(board, "lime") == 0)
    return strcmp(configured, "LIMEMINI") == 0 || strcmp(configured, "LIMEUSB") == 0 || strcmp(configured, "LIMEDVB") == 0;
  if (strcmp(board, "dektec_asi") == 0) return strcmp(configured, "DEKTEC_ASI") == 0;
  if (strcmp(board, "sdrangel") == 0) return strcmp(configured, "SDRANGEL") == 0;
  return false;
}

/* Separate from the source choice on MASTER. No local capture or UDP-only
 * input is allowed to key a remote SLAVE, including direct socket commands. */
static bool slave_input_matches(void)
{
  if (!config_path) return false;
  FILE *file = fopen(config_path, "r");
  if (!file) return false;
  char line[512];
  bool input = false, layout = false, encoding = false, transport = false;
  while (fgets(line, sizeof(line), file)) {
    line[strcspn(line, "\r\n")] = 0;
    if (strncmp(line, "modeinput=", 10) == 0) input = strcmp(line + 10, "IPTSIN") == 0;
    if (strncmp(line, "source_layout=", 14) == 0) layout = strcmp(line + 14, "DIRECT") == 0;
    if (strncmp(line, "encoding=", 9) == 0) encoding = strcmp(line + 9, "IPTS in") == 0;
    if (strncmp(line, "iptransport=", 12) == 0) transport = strcmp(line + 12, "srt") == 0;
  }
  fclose(file);
  return input && layout && encoding && transport;
}

static bool source_ts_selected(void)
{
  if (!config_path) return false;
  FILE *file = fopen(config_path, "r");
  if (!file) return false;
  char line[512], layout[32] = "", input[32] = "";
  while (fgets(line, sizeof(line), file)) {
    if (strncmp(line, "source_layout=", 14) == 0) {
      char *value = line + 14; value[strcspn(value, "\r\n")] = 0;
      if (strlen(value) < sizeof(layout)) strcpy(layout, value);
    } else if (strncmp(line, "modeinput=", 10) == 0) {
      char *value = line + 10; value[strcspn(value, "\r\n")] = 0;
      if (strlen(value) < sizeof(input)) strcpy(input, value);
    }
  }
  fclose(file);
  return strcmp(layout, "MULTIVIEW") == 0 ||
    (strcmp(layout, "DIRECT") == 0 &&
     (strcmp(input, "SRT") == 0 || strcmp(input, "IPCAM1") == 0 || strcmp(input, "IPCAM2") == 0));
}

static void on_signal(int signo) { (void)signo; stopping = 1; }
static void nonblock(int fd) { int f = fcntl(fd, F_GETFL); if (f >= 0) (void)fcntl(fd, F_SETFL, f | O_NONBLOCK); }
static void send_client(int fd, const char *s) { if (fd >= 0) (void)send(fd, s, strlen(s), MSG_NOSIGNAL | MSG_DONTWAIT); }
static void broadcast(const char *s) { for (int i = 0; i < CLIENTS; i++) send_client(clients[i].fd, s); }

static bool safe_off(void)
{
  if (strcmp(board, "express") == 0) {
    int fd = open(express_ctrl, O_WRONLY | O_APPEND | O_NONBLOCK | O_CLOEXEC);
    if (fd >= 0) {
      static const char msg[] = "set ptt rx\nset car off\n";
      if (write(fd, msg, sizeof(msg) - 1) != (ssize_t)(sizeof(msg) - 1))
        fprintf(stderr, "Express safe-off write failed: %s\n", strerror(errno));
      close(fd);
    } else fprintf(stderr, "Express safe-off open failed: %s\n", strerror(errno));
  }
  if (!safe_off_exec || safe_off_exec[0] != '/' || access(safe_off_exec, X_OK) != 0) return false;
  pid_t pid = fork();
  if (pid == 0) { (void)setsid(); execl(safe_off_exec, safe_off_exec, (char *)NULL); _exit(127); }
  if (pid < 0) return false;
  int status = 0;
  struct timespec delay = { .tv_sec = 0, .tv_nsec = 10000000 };
  for (int i = 0; i < 50; i++) {
    pid_t done = waitpid(pid, &status, WNOHANG);
    if (done == pid) return WIFEXITED(status) && WEXITSTATUS(status) == 0;
    if (done < 0 && errno != EINTR) break;
    nanosleep(&delay, NULL);
  }
  (void)kill(-pid, SIGKILL);
  (void)waitpid(pid, &status, 0);
  fprintf(stderr, "Safe-off hook timed out or failed\n");
  return false;
}

static bool stop_role(enum role role)
{
  struct child *c = &children[role];
  bool off_ok = role != TX || safe_off();
  if (c->pid <= 0) return off_ok;
  pid_t pid = c->pid;
  (void)kill(-pid, SIGTERM);
  struct timespec delay = { .tv_sec = 0, .tv_nsec = 10000000 };
  for (int i = 0; i < 50; i++) {
    if (waitpid(pid, NULL, WNOHANG) == pid) break;
    nanosleep(&delay, NULL);
  }
  /* Kill the group even if its leader exited before its descendants. */
  (void)kill(-pid, SIGKILL);
  (void)waitpid(pid, NULL, WNOHANG);
  c->pid = 0;
  if (c->logfd >= 0) { close(c->logfd); c->logfd = -1; }
  c->used = 0;
  char msg[64];
  snprintf(msg, sizeof(msg), "STATE %s stopped\n", role_names[role]);
  broadcast(msg);
  return off_ok;
}

static bool start_role(enum role role)
{
  if (slave_mode && role != TX) return false; /* Receiver/TX pipeline owns any preview tap. */
  if ((role == TX || role == RX) && strcmp(board, "sdrangel") == 0) {
    const char *peer_role = getenv("PORTSDOWN_PEER_ROLE");
    if ((peer_role && strcmp(peer_role, "STANDALONE") != 0) || !board_config_matches()) return false;
  }
  if (children[role].pid > 0) return true;
  if (role == PREVIEW && (children[TX].pid > 0 || children[RX].pid > 0)) return false;
  const char *execpath = executables[role];
  if (!execpath || execpath[0] != '/' || access(execpath, X_OK) != 0) return false;
  if (role == TX) {
    if (strcmp(board, "express") != 0 && strcmp(board, "pluto") != 0 &&
        strcmp(board, "lime") != 0 && strcmp(board, "dektec_asi") != 0 &&
        strcmp(board, "sdrangel") != 0) return false;
    if (!safe_off_exec || safe_off_exec[0] != '/' || access(safe_off_exec, X_OK)) return false;
    (void)stop_role(PREVIEW); /* Release /dev/video0 before starting TX. */
    (void)stop_role(HDMI);
    (void)stop_role(PICAM);
    (void)stop_role(IPTS);
    (void)stop_role(IPCAM1);
    (void)stop_role(IPCAM2);
    if (!safe_off()) { (void)start_role(PREVIEW); return false; }
  } else if (role == RX) {
    (void)stop_role(PREVIEW);
  }
  int pipefd[2];
  if (pipe2(pipefd, O_CLOEXEC) < 0) return false;
  pid_t pid = fork();
  if (pid < 0) { close(pipefd[0]); close(pipefd[1]); return false; }
  if (pid == 0) {
    close(pipefd[0]);
    if (setsid() < 0) _exit(126);
    dup2(pipefd[1], STDOUT_FILENO);
    dup2(pipefd[1], STDERR_FILENO);
    close(pipefd[1]);
    if (role >= SRT1 && role <= SRT5) {
      char slot[2] = { (char)('1' + role - SRT1), 0 };
      execl(execpath, execpath, slot, (char *)NULL);
    } else if (role >= HDMI && role <= IPCAM2) {
      execl(execpath, execpath, role_names[role], (char *)NULL);
    } else if ((role == TX || role == RX) && strcmp(board, "sdrangel") == 0)
      execl(execpath, execpath, role == TX ? "tx" : "rx", (char *)NULL);
    else execl(execpath, execpath, (char *)NULL);
    _exit(127);
  }
  close(pipefd[1]); nonblock(pipefd[0]);
  children[role] = (struct child){ .pid = pid, .logfd = pipefd[0] };
  char msg[64];
  snprintf(msg, sizeof(msg), "STATE %s started\n", role_names[role]);
  broadcast(msg);
  return true;
}

static void command(int fd, const char *line)
{
  if (strcmp(line, "PEER_HB") == 0 && slave_mode) {
    last_peer_hb = monotonic_ms(); send_client(fd, "OK\n"); return;
  }
  if (strcmp(line, "STATUS") == 0) {
    char result[512];
    snprintf(result, sizeof(result), "STATUS tx=%s rx=%s preview=%s board=%s peer=%s link=%s srt1=%s srt2=%s srt3=%s srt4=%s srt5=%s hdmi=%s picam=%s ipts=%s ipcam1=%s ipcam2=%s source_ts=%s tx_pid=%ld rx_pid=%ld\n",
      children[TX].pid ? "running" : "stopped", children[RX].pid ? "running" : "stopped",
      children[PREVIEW].pid ? "running" : "stopped", board,
      slave_mode ? "slave" : "standalone", slave_mode && last_peer_hb > 0 && monotonic_ms() - last_peer_hb < 1500 ? "ok" : "stale",
      children[SRT1].pid ? "running" : "stopped", children[SRT2].pid ? "running" : "stopped",
      children[SRT3].pid ? "running" : "stopped", children[SRT4].pid ? "running" : "stopped",
      children[SRT5].pid ? "running" : "stopped",
      children[HDMI].pid ? "running" : "stopped",
      children[PICAM].pid ? "running" : "stopped",
      children[IPTS].pid ? "running" : "stopped",
      children[IPCAM1].pid ? "running" : "stopped",
      children[IPCAM2].pid ? "running" : "stopped",
      children[SOURCE_TS].pid ? "running" : "stopped", (long)children[TX].pid, (long)children[RX].pid);
    send_client(fd, result);
    return;
  }
  for (int role = 0; role < ROLE_COUNT; role++) {
    char start[32], stop[32];
    snprintf(start, sizeof(start), "START_%s", role_names[role]);
    snprintf(stop, sizeof(stop), "STOP_%s", role_names[role]);
    if (strcmp(line, start) == 0) {
      if (role == TX && slave_mode && (last_peer_hb == 0 || monotonic_ms() - last_peer_hb >= 1500)) {
        send_client(fd, "ERR peer heartbeat stale\n"); return;
      }
      if (role == TX && slave_mode && !slave_input_matches()) {
        send_client(fd, "ERR SLAVE requires IPTS over SRT\n"); return;
      }
      if (role == TX && children[RX].pid) { send_client(fd, "ERR RX active\n"); return; }
      if (role == TX && !board_config_matches()) { send_client(fd, "ERR config board mismatch or unavailable\n"); return; }
      if (role == TX && source_ts_selected()) { send_client(fd, "ERR selected source TS RF route unavailable\n"); return; }
      if (role == SOURCE_TS && !source_ts_selected()) { send_client(fd, "ERR source TS route not selected\n"); return; }
      if (role == RX && children[TX].pid) { send_client(fd, "ERR TX active\n"); return; }
      send_client(fd, start_role((enum role)role) ? "OK\n" : "ERR unavailable\n");
      return;
    }
    if (strcmp(line, stop) == 0) {
      bool off_ok = stop_role((enum role)role);
      if (role == TX || role == RX) (void)start_role(PREVIEW);
      send_client(fd, off_ok ? "OK\n" : "ERR safe-off hook failed\n"); return;
    }
  }
  send_client(fd, "ERR unknown command\n");
}

static void read_client(struct client *c)
{
  char buf[256]; ssize_t n = recv(c->fd, buf, sizeof(buf), 0);
  if (n <= 0) { close(c->fd); *c = (struct client){ .fd = -1 }; return; }
  for (ssize_t i = 0; i < n; i++) {
    if (buf[i] == '\n') {
      c->input[c->used] = 0;
      if (c->used && c->input[c->used - 1] == '\r') c->input[c->used - 1] = 0;
      command(c->fd, c->input); c->used = 0;
    } else if (c->used + 1 < sizeof(c->input)) c->input[c->used++] = buf[i];
    else { send_client(c->fd, "ERR line too long\n"); c->used = 0; }
  }
}

static void read_log(enum role role)
{
  struct child *c = &children[role];
  char buf[256]; ssize_t n = read(c->logfd, buf, sizeof(buf));
  if (n <= 0) return;
  for (ssize_t i = 0; i < n; i++) {
    if (buf[i] == '\n' || c->used + 1 >= sizeof(c->pending)) {
      c->pending[c->used] = 0;
      char msg[LOG_LINE + 32];
      snprintf(msg, sizeof(msg), "LOG %s %s\n", role_names[role], c->pending);
      broadcast(msg); c->used = 0;
    } else if (buf[i] != '\r') c->pending[c->used++] = buf[i];
  }
}

int main(void)
{
  const char *dir = getenv("PORTSDOWN_RUN_DIR");
  if (!dir || !*dir) dir = "/run/portsdown";
  board = getenv("PORTSDOWN_BOARD"); if (!board) board = "none";
  express_ctrl = getenv("PORTSDOWN_EXPRESS_CTRL"); if (!express_ctrl) express_ctrl = "/tmp/expctrl";
  safe_off_exec = getenv("PORTSDOWN_SAFE_OFF_EXEC");
  config_path = getenv("PORTSDOWN_CONFIG");
  if (!config_path) {
    const char *base = getenv("PORTSDOWN_DIR");
    if (base && base[0] == '/') {
      static char default_config[4096];
      if (snprintf(default_config, sizeof(default_config), "%s/scripts/portsdown_config.txt", base) < (int)sizeof(default_config))
        config_path = default_config;
    }
  }
  slave_mode = getenv("PORTSDOWN_PEER_ROLE") && strcmp(getenv("PORTSDOWN_PEER_ROLE"), "SLAVE") == 0;
  executables[TX] = getenv("PORTSDOWN_TX_EXEC");
  executables[RX] = getenv("PORTSDOWN_RX_EXEC");
  executables[PREVIEW] = getenv("PORTSDOWN_PREVIEW_EXEC");
  for (int i = SRT1; i <= SRT5; i++) executables[i] = getenv("PORTSDOWN_SRT_EXEC");
  for (int i = HDMI; i <= IPCAM2; i++) executables[i] = getenv("PORTSDOWN_SOURCE_PREVIEW_EXEC");
  executables[SOURCE_TS] = getenv("PORTSDOWN_SOURCE_TS_EXEC");
  for (int i = 0; i < ROLE_COUNT; i++) children[i].logfd = -1;
  for (int i = 0; i < CLIENTS; i++) clients[i].fd = -1;
  if (mkdir(dir, 0750) < 0 && errno != EEXIST) { perror("mkdir"); return 1; }
  struct stat dirstat;
  if (lstat(dir, &dirstat) < 0 || !S_ISDIR(dirstat.st_mode) || dirstat.st_uid != geteuid()) {
    fprintf(stderr, "Unsafe runtime directory\n"); return 1;
  }
  char path[sizeof(((struct sockaddr_un *)0)->sun_path)];
  if (snprintf(path, sizeof(path), "%s/tx.sock", dir) >= (int)sizeof(path)) return 1;
  sockpath = path;
  int server = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (server < 0) { perror("socket"); return 1; }
  struct sockaddr_un addr = { .sun_family = AF_UNIX };
  strcpy(addr.sun_path, path);
  struct stat oldsock;
  if (lstat(path, &oldsock) == 0) {
    if (!S_ISSOCK(oldsock.st_mode) || oldsock.st_uid != geteuid()) {
      fprintf(stderr, "Unsafe existing control socket\n"); return 1;
    }
    int probe = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (probe >= 0) {
      if (connect(probe, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
        fprintf(stderr, "Supervisor already running\n"); close(probe); return 1;
      }
      close(probe);
    }
    if (unlink(path) < 0) { perror("stale socket unlink"); return 1; }
  } else if (errno != ENOENT) { perror("socket path stat"); return 1; }
  mode_t old = umask(007);
  if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(server, 16) < 0) {
    perror("bind/listen"); return 1;
  }
  umask(old); nonblock(server);
  struct sigaction sa = { .sa_handler = on_signal };
  sigaction(SIGINT, &sa, NULL); sigaction(SIGTERM, &sa, NULL); sigaction(SIGHUP, &sa, NULL);
  if (safe_off_exec && !safe_off()) fprintf(stderr, "Startup safe-off hook failed; TX remains unavailable\n");
  (void)start_role(PREVIEW);
  while (!stopping) {
    struct pollfd pfd[1 + CLIENTS + ROLE_COUNT];
    int kind[1 + CLIENTS + ROLE_COUNT], id[1 + CLIENTS + ROLE_COUNT], count = 0;
    pfd[count] = (struct pollfd){ .fd = server, .events = POLLIN }; kind[count] = 0; id[count++] = 0;
    for (int i = 0; i < CLIENTS; i++) if (clients[i].fd >= 0) {
      pfd[count] = (struct pollfd){ .fd = clients[i].fd, .events = POLLIN }; kind[count] = 1; id[count++] = i;
    }
    for (int i = 0; i < ROLE_COUNT; i++) if (children[i].logfd >= 0) {
      pfd[count] = (struct pollfd){ .fd = children[i].logfd, .events = POLLIN }; kind[count] = 2; id[count++] = i;
    }
    int ready = poll(pfd, count, 100);
    if (ready > 0) for (int i = 0; i < count; i++) if (pfd[i].revents) {
      if (kind[i] == 0) {
        int fd = accept4(server, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
        if (fd >= 0) {
          int slot = -1; for (int j = 0; j < CLIENTS; j++) if (clients[j].fd < 0) { slot = j; break; }
          if (slot < 0) close(fd); else clients[slot] = (struct client){ .fd = fd };
        }
      } else if (kind[i] == 1) read_client(&clients[id[i]]);
      else if (pfd[i].revents & POLLIN) read_log((enum role)id[i]);
    }
    for (int i = 0; i < ROLE_COUNT; i++) if (children[i].pid > 0) {
      if (waitpid(children[i].pid, NULL, WNOHANG) == children[i].pid) {
        if (i == TX) safe_off();
        /* The leader may have left encoder/backend descendants behind. */
        (void)kill(-children[i].pid, SIGKILL);
        children[i].pid = 0;
        if (children[i].logfd >= 0) close(children[i].logfd);
        children[i].logfd = -1;
        char msg[64]; snprintf(msg, sizeof(msg), "STATE %s exited\n", role_names[i]); broadcast(msg);
        if (i == TX || i == RX) (void)start_role(PREVIEW);
      }
    }
    if (slave_mode && children[TX].pid > 0 && (last_peer_hb == 0 || monotonic_ms() - last_peer_hb >= 1500)) {
      broadcast("FAULT peer heartbeat lost; stopping TX\n");
      stop_role(TX);
      (void)start_role(PREVIEW);
    }
  }
  for (int i = 0; i < ROLE_COUNT; i++) stop_role((enum role)i);
  safe_off();
  for (int i = 0; i < CLIENTS; i++) if (clients[i].fd >= 0) close(clients[i].fd);
  close(server); unlink(sockpath);
  return 0;
}
