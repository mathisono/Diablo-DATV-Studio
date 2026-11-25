/* Private shared-password records; passwords arrive on stdin, never argv.
 * OpenSSL PBKDF2/SHA256 and RAND_bytes, no custom cryptography. */
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define ITERATIONS 600000
static void hex(const unsigned char *in, size_t n, char *out) {
    for (size_t i=0;i<n;i++) sprintf(out+2*i,"%02x",in[i]);
}
static int unhex(const char *s, unsigned char *out, size_t n) {
    if (strlen(s)!=n*2) return 0;
    for (size_t i=0;i<n;i++) { unsigned x; char pair[3]={s[2*i],s[2*i+1],0};
        if (strspn(pair,"0123456789abcdef")!=2 || sscanf(pair,"%2x",&x)!=1) return 0;
        out[i]=(unsigned char)x;
    } return 1;
}
static int derive(const char *pw, int len, const unsigned char *salt, int n, unsigned char *out) {
    return PKCS5_PBKDF2_HMAC(pw,len,salt,n,ITERATIONS,EVP_sha256(),32,out);
}
static FILE *private_open(const char *path, int create) {
    int fd=open(path,(create ? O_WRONLY|O_CREAT|O_EXCL : O_RDONLY)|O_NOFOLLOW,0600);
    if (fd<0) return NULL;
    struct stat s;
    if (fstat(fd,&s) || !S_ISREG(s.st_mode) || s.st_uid!=geteuid() || (s.st_mode&077)) { close(fd);return NULL; }
    FILE *f=fdopen(fd,create?"w":"r"); if (!f) close(fd);return f;
}
int main(int argc,char **argv) {
    if (argc!=3 || (strcmp(argv[1],"create") && strcmp(argv[1],"verify") && strcmp(argv[1],"peer-key"))) return 2;
    unsigned char salt[16],want[32],got[32],key[32];
    char sh[33],wh[65],kh[65],pw[130]={0}; int rc=1;
    if (!strcmp(argv[1],"create")) {
        size_t n=fread(pw,1,sizeof(pw),stdin);
        if (n<12 || n>128 || memchr(pw,0,n) || memchr(pw,'\n',n) || memchr(pw,'\r',n)) goto done;
        static const unsigned char domain[]="Diablo DATV Studio peer TLS PSK v1";
        if (!RAND_bytes(salt,16) || !derive(pw,(int)n,salt,16,want) || !derive(pw,(int)n,domain,sizeof(domain)-1,key)) goto done;
        hex(salt,16,sh);hex(want,32,wh);hex(key,32,kh);
        FILE *f=private_open(argv[2],1);if (!f) goto done;
        int ok=fprintf(f,"v1 %s %s %s\n",sh,wh,kh)>0 && fflush(f)==0 && fsync(fileno(f))==0;
        if (fclose(f)) ok=0;
        rc=ok?0:1;
    } else {
        FILE *f=private_open(argv[2],0);if (!f) goto done;
        char version[4],extra;
        int count=fscanf(f,"%3s %32s %64s %64s %c",version,sh,wh,kh,&extra);fclose(f);
        if (count!=4 || strcmp(version,"v1") || !unhex(sh,salt,16) || !unhex(wh,want,32) || !unhex(kh,key,32)) goto done;
        if (!strcmp(argv[1],"peer-key")) { printf("%s\n",kh);rc=0;goto done; }
        size_t n=fread(pw,1,sizeof(pw),stdin);
        if (n<12 || n>128 || memchr(pw,0,n)) goto done;
        if (!derive(pw,(int)n,salt,16,got)) goto done;
        rc=CRYPTO_memcmp(got,want,32)?1:0;
    }
done:
    OPENSSL_cleanse(pw,sizeof(pw));OPENSSL_cleanse(key,sizeof(key));OPENSSL_cleanse(kh,sizeof(kh));
    return rc;
}
