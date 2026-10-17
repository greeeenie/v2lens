"""Restore only the pinned ETW runtime files used by the Windows helper."""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    ('microsoft.diagnostics.tracing.traceevent','2.0.77','0055b65a090d4e7b179bd32fc9365bdcc1f70f7f3d081685f93b2067436c0850',{
        **{'lib/net45/'+name:'traffic-helper/'+name for name in [
            'Microsoft.Diagnostics.Tracing.TraceEvent.dll','Microsoft.Diagnostics.FastSerialization.dll','OSExtensions.dll']},
        **{'build/native/amd64/'+name:'traffic-helper/amd64/'+name for name in [
            'KernelTraceControl.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll']}
    }),
    ('system.runtime.compilerservices.unsafe','4.5.2','f1e5175c658ed8b2fbb804cc6727b6882a503844e7da309c8d4846e9ca11e4ef',{
        'lib/netstandard2.0/System.Runtime.CompilerServices.Unsafe.dll':'traffic-helper/System.Runtime.CompilerServices.Unsafe.dll',
        'LICENSE.TXT':'licenses/Unsafe-LICENSE.txt',
        'THIRD-PARTY-NOTICES.TXT':'licenses/Unsafe-NOTICES.txt'
    })
]


def restore():
    cache=ROOT/'.cache/nuget'
    cache.mkdir(parents=True,exist_ok=True)
    for name,version,digest,files in PACKAGES:
        filename=f'{name}.{version}.nupkg'
        package=cache/filename
        if not package.exists():
            data=urllib.request.urlopen(f'https://api.nuget.org/v3-flatcontainer/{name}/{version}/{filename}',timeout=60).read()
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError(f'Checksum mismatch: {filename}')
            package.write_bytes(data)
        data=package.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError(f'Checksum mismatch: {filename}')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for source,target in files.items():
                target=target.replace('traffic-helper/','native/traffic-observer/').replace('licenses/','src/v2lens/resources/licenses/')
                destination=ROOT/target
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(archive.read(source))


if __name__=='__main__':restore()
