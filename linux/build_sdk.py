#!/usr/bin/env python3
"""Controlled upstream import + offline SDK builder. Never invoked by game builds."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def run(cmd, cwd=None, env=None):
    print('+', ' '.join(map(str, cmd)), flush=True)
    try:
        return subprocess.check_output(list(map(str, cmd)), cwd=cwd, env=env, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as error:
        print(error.output, flush=True)
        raise

def archive(root, output):
    with output.open('wb') as f, gzip.GzipFile(fileobj=f, filename='', mtime=0) as gz, tarfile.open(fileobj=gz, mode='w') as tar:
        for path in [root] + sorted(root.rglob('*')):
            info = tar.gettarinfo(str(path), arcname=path.relative_to(root.parent).as_posix())
            info.uid = info.gid = 0; info.uname = info.gname = 'root'; info.mtime = 0
            if info.isfile():
                with path.open('rb') as data: tar.addfile(info, data)
            else: tar.addfile(info)

def validate(root):
    records=[]
    for p in sorted((root/'lib').glob('*.so*')):
        if p.is_symlink():
            assert not os.path.isabs(os.readlink(p)) and p.resolve().parent == (root/'lib').resolve()
            continue
        header=run(['readelf','-h',p]); assert 'ELF64' in header and 'Advanced Micro Devices X86-64' in header
        dynamic=run(['readelf','-d',p]); needed=re.findall(r'Shared library: \[([^]]+)\]',dynamic)
        soname=re.findall(r'Library soname: \[([^]]+)\]',dynamic); assert len(soname)==1 and (root/'lib'/soname[0]).is_file()
        assert all(n in {'libc.so.6','libdl.so.2','libpthread.so.0','libcrypto.so.3'} for n in needed), needed
        versions=re.findall(r'GLIBC_([\d.]+)',run(['objdump','-T',p]))
        assert all(tuple(map(int,v.split('.'))) <= (2,35) for v in versions), versions
        env=os.environ.copy();env.pop('LD_PRELOAD',None);env['LD_LIBRARY_PATH']=str(root/'lib')
        closure=run(['ldd',p],env=env);assert 'not found' not in closure
        if 'libcrypto.so.3' in needed: assert str(root/'lib/libcrypto.so.3') in closure
        records.append(dict(file=p.name,soname=soname[0],needed=needed,sha256=digest(p),glibc=sorted(set(versions))))
    assert records
    return records

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--import-sources',action='store_true');ap.add_argument('--jobs',type=int,default=os.cpu_count());args=ap.parse_args()
    assert platform.machine()=='x86_64'
    os_release=Path('/etc/os-release').read_text();assert 'VERSION_ID="22.04"' in os_release, 'Build on the documented Ubuntu 22.04 baseline'
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True);out=work/'artifacts';out.mkdir(exist_ok=True)
    lock=json.loads((HERE/'sources.json').read_text());records=[]
    toolchain={name:run(cmd).splitlines()[0] for name,cmd in {'cc':['cc','--version'],'make':['make','--version'],'perl':['perl','-e','print $^V'],'ld':['ld','--version']}.items()}
    for name in ('openssl','zlib'):
        item=lock[name];source_archive=work/(name+'-'+item['version']+'.tar.gz')
        if not source_archive.exists():
            assert args.import_sources, 'Supply verified upstream archive or explicitly --import-sources'
            with urllib.request.urlopen(item['url']) as response, source_archive.open('wb') as f: shutil.copyfileobj(response,f)
        assert digest(source_archive)==item['sha256'], 'Official source checksum mismatch: '+name
        src=work/'source'/name;build=work/'compile'/name;stage=work/'stage'/name
        for directory in (src,build,stage):
            if directory.exists(): shutil.rmtree(directory)
            directory.mkdir(parents=True)
        with tarfile.open(source_archive) as tar:
            for m in tar.getmembers():
                assert not m.name.startswith('/') and '..' not in Path(m.name).parts and not m.islnk() and not m.issym()
            tar.extractall(src)
        source=next(src.iterdir())
        env={k:v for k,v in os.environ.items() if k not in ('CFLAGS','CPPFLAGS','CXXFLAGS','LDFLAGS','LD_LIBRARY_PATH','LD_PRELOAD','CPATH','LIBRARY_PATH','OPENSSL_CONF','OPENSSL_MODULES')}
        env.update(SOURCE_DATE_EPOCH='0',LC_ALL='C',TZ='UTC',LD_RUN_PATH='$ORIGIN',CFLAGS='-O2 -fPIC -march=x86-64 -mtune=generic -ffile-prefix-map='+str(work)+'=/usr/src/hoo-dependencies')
        if name=='openssl':
            assert 'MAJOR=3' in (source/'VERSION.dat').read_text()
            configuration=['linux-x86_64','shared','no-module','no-legacy','no-engine','no-tests','--prefix=/usr','--libdir=lib','--openssldir=/etc/ssl','-Wl,--disable-new-dtags']
            print(run(['perl',source/'Configure']+configuration,cwd=build,env=env))
        else:
            configuration=['--shared','--prefix=/usr','--libdir=/usr/lib']
            env['LDFLAGS']='-Wl,--disable-new-dtags'
            # zlib configure supports out-of-source builds through the absolute script path.
            print(run([source/'configure']+configuration,cwd=build,env=env))
        print(run(['make','-j',str(args.jobs)],cwd=build,env=env))
        if name=='zlib': print(run(['make','test'],cwd=build,env=env))
        env['DESTDIR']=str(stage)
        print(run(['make','DESTDIR='+str(stage),'install_sw' if name=='openssl' else 'install'],cwd=build,env=env))
        root=work/(name+'-'+item['version']+'-linux-x86_64')
        if root.exists():shutil.rmtree(root)
        shutil.copytree(stage/'usr/include',root/'include',symlinks=True);(root/'lib').mkdir()
        for p in (stage/'usr/lib').glob('*.so*'):
            if p.is_symlink(): (root/'lib'/p.name).symlink_to(os.readlink(p))
            else:shutil.copy2(p,root/'lib'/p.name)
        license_file=source/item['licenseFile'];assert license_file.is_file(), str(license_file)
        shutil.copy2(license_file,root/'LICENSE.txt')
        info=dict(schema=1,name=name,version=item['version'],architecture='x86_64',os='linux',source=item,toolchain=toolchain,configuration=configuration,baseline=dict(os='Ubuntu 22.04',glibc='2.35',glibcxx='3.4.30'),providers='default/base built into libcrypto; no dynamically loaded modules, legacy or engines' if name=='openssl' else None,libraries=validate(root),recipeSha256=digest(__file__))
        (root/'provenance.json').write_text(json.dumps(info,indent=2,sort_keys=True)+'\n')
        target=out/(root.name+'-v1.tar.gz');assert not target.exists(), 'Never overwrite a published candidate; use a fresh artifact directory'
        archive(root,target);records.append(dict(name=name,file=target.name,archiveRoot=root.name,sha256=digest(target),size=target.stat().st_size,provenance=info))
    (out/'manifest.json').write_text(json.dumps(records,indent=2,sort_keys=True)+'\n')
    (out/'SHA256SUMS').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in records))

if __name__=='__main__':main()
