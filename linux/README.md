# Linux x86_64 SDK import (v1)

Controlled dependency publishing only. Normal game builds must never run this
importer or obtain sources from upstream. They consume the immutable internal
release and verify its archive hashes.

No suitable Linux OpenSSL/zlib archives existed in the releases audited on
2026-11-17. The existing macOS ARM64 SDKs (including UNVALIDATED candidates) are
not Linux inputs. Reuse the existing pinned FFmpeg Linux artifact unchanged.

OpenSSL 3.5.9 is the current 3.5 LTS patch, supported through 2030-04-08:
https://openssl-library.org/source/ and https://openssl-library.org/policies/releasestrat/
The 3.3.2 placeholder is no longer supported. zlib 1.4 is the current official
release (2026-11-04), including security corrections since 1.3.2:
https://zlib.net/ . Source SHA-256 values in sources.json were checked against
those official HTTPS sources; no signature-verification claim is made.

Build on Ubuntu 22.04 x86_64 with GCC 11, GNU binutils, GNU make, Perl, Python 3,
and development libc headers. These are build tools, not application payloads.

```
python3 linux/build_sdk.py --work build/linux-sdk --import-sources --jobs 12
# Offline repeat: put the exact source tarballs in a fresh work directory, omit --import-sources.
```

Use a fresh artifact destination; never replace published assets. The script
checks source hashes and produces deterministic tar metadata, headers, shared
libraries with their original relative SONAME links, LICENSE.txt and detailed
provenance.json. Build flags target generic x86-64, not the build machine's CPU.
OpenSSL disables dynamic modules, legacy provider and engines; the default/base
provider is built into libcrypto, so no external provider directory is required.
No FIPS claim is made. System trust discovery uses /etc/ssl; this does not modify
certificates. Shared libraries have $ORIGIN DT_RPATH and no build-tree paths.

The baseline is native Ubuntu 22.04 (GLIBC <= 2.35, GLIBCXX <= 3.4.30), compatible
with the release workflow's selected Steam Linux Runtime 4.0 target. ELF machine,
required symbol versions, SONAMEs and closure are checked before packaging.
This does not claim execution inside Steam Runtime itself.

application-sources.json records the already-pinned application sources,
upstream Git origins, exact commits, licenses and archive hashes. archive_sources.py
recreates their deterministic git archives from reviewed local checkouts; it
performs no network access. Each source archive contains its upstream license.

The release manifest records actual GCC/ld/make/Perl versions, configuration,
source digests, recipe digest and each library's SONAME/DT_NEEDED/symbol baseline.
Only these SDK/source archives and manifests are published, not Steamworks,
glibc, desktop drivers or toolchains. The internal Steamworks acquisition path
is independent and unchanged.
