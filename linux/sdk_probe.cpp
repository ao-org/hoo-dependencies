#include <openssl/ssl.h>
#include <openssl/evp.h>
#include <zlib.h>
#include <cstring>
#include <iostream>
int main() {
    if (std::strcmp(OpenSSL_version(OPENSSL_VERSION), OPENSSL_VERSION_TEXT)) return 1;
    if (std::strcmp(zlibVersion(), ZLIB_VERSION)) return 2;
    SSL_CTX* ctx=SSL_CTX_new(TLS_client_method()); if(!ctx) return 3; SSL_CTX_free(ctx);
    unsigned char digest[32]; unsigned size=0;
    if(!EVP_Digest("test",4,digest,&size,EVP_sha256(),nullptr) || size!=32) return 4;
    const unsigned char input[]="authenticated pack compression probe"; unsigned char packed[256],unpacked[256];
    uLongf n=sizeof(packed),m=sizeof(unpacked);
    if(compress(packed,&n,input,sizeof(input))!=Z_OK || uncompress(unpacked,&m,packed,n)!=Z_OK || m!=sizeof(input) || std::memcmp(input,unpacked,m)) return 5;
    std::cout<<OpenSSL_version(OPENSSL_VERSION)<<"; zlib "<<zlibVersion()<<"; TLS context, SHA-256 and compression round trip passed\n";
}
