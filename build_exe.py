"""Build a single portable Windows x64 executable; never bundle user state/configs."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import zipfile
from restore_helper import restore


ROOT = Path(__file__).resolve().parent
DIST = ROOT/'dist'
HELPER = ROOT/'traffic-helper'
restore()
subprocess.run([sys.executable,str(ROOT/'make_icon.py')],check=True)
CSC = Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(CSC), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                '/out:'+str(HELPER/'TrafficObserver.exe'),
                '/reference:System.Web.Extensions.dll',
                '/reference:'+str(HELPER/'Microsoft.Diagnostics.Tracing.TraceEvent.dll'),
                '/reference:'+str(HELPER/'Microsoft.Diagnostics.FastSerialization.dll'),
                str(HELPER/'TrafficObserver.cs')],check=True,cwd=HELPER)
subprocess.run([str(HELPER/'TrafficObserver.exe'),'--self-test'],check=True)
data = ['--add-data', str(ROOT/'panel.html')+':.',
        '--add-data', str(ROOT/'json-editor.js')+':.',
        '--add-data', str(ROOT/'json-editor.LICENSE.txt')+':.']
data += ['--add-data',str(ROOT/'assets/v2lens.ico')+':assets']
data += ['--add-data',str(ROOT/'licenses')+':licenses','--add-data',str(ROOT/'LICENSE')+':.',
         '--add-data',str(ROOT/'VERSION')+':.']
for file in HELPER.rglob('*'):
    if file.is_file() and file.suffix.lower() in ('.exe','.dll'):
        data += ['--add-data', str(file)+':'+str(Path('traffic-helper')/file.relative_to(HELPER).parent)]
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                '--name','V2Lens','--icon',str(ROOT/'assets/v2lens.ico'),'--uac-admin',
                '--distpath',str(DIST),
                '--workpath',str(ROOT/'build'),'--specpath',str(ROOT/'build'),
                '--hidden-import','webview.platforms.edgechromium',
                '--collect-all','webview',*data,str(ROOT/'viewer.py')],check=True,cwd=ROOT)
with zipfile.ZipFile(DIST/'V2Lens-portable.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in ['V2Lens.exe']:
        archive.write(DIST/name,name)
    for name in ['README.md','LICENSE','VERSION','CHANGELOG.md','json-editor.LICENSE.txt']:
        archive.write(ROOT/name,name)
    for file in (ROOT/'licenses').glob('*'):
        if file.is_file():archive.write(file,'licenses/'+file.name)
with (DIST/'SHA256SUMS.txt').open('w',encoding='utf-8',newline='\n') as checksums:
    for name in ['V2Lens.exe','V2Lens-portable.zip']:
        checksums.write(hashlib.sha256((DIST/name).read_bytes()).hexdigest()+'  '+name+'\n')
print('Portable EXE, ZIP and SHA-256 checksums ready in dist/')
