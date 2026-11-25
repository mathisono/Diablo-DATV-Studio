CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L

all: tx-super config-store auth-store

tx-super: tx-super.c
	$(CC) $(CFLAGS) -o $@ $<

config-store: config-store.c
	$(CC) $(CFLAGS) -o $@ $<

auth-store: auth-store.c
	$(CC) $(CFLAGS) -o $@ $< -lcrypto

clean:
	rm -f tx-super config-store auth-store

.PHONY: all clean
