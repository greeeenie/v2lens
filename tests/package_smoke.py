"""Check a built package without changing a real v2rayN installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
executable=ROOT/'dist/V2Lens.exe'
names=list(CArchiveReader(str(executable)).toc)
for name in names:
    assert not any(part in name.lower() for part in ['guindb','guiconfigs','snapshot.json','preferences.json','traffic.json','editor.json']),name
assert any(name.endswith('panel.html') for name in names)
assert any(name.endswith('TrafficObserver.exe') for name in names)
with zipfile.ZipFile(ROOT/'dist/V2Lens-portable.zip') as archive:
    assert {'V2Lens.exe','README.md','LICENSE','VERSION'}.issubset(archive.namelist())
    assert archive.read('V2Lens.exe')==executable.read_bytes()
for line in (ROOT/'dist/SHA256SUMS.txt').read_text().splitlines():
    digest,name=line.split('  ',1)
    assert hashlib.sha256((ROOT/'dist'/name).read_bytes()).hexdigest()==digest
with tempfile.TemporaryDirectory(prefix='V2Lens portable smoke ') as directory:
    fixture=Path(directory)
    (fixture/'v2rayN.exe').touch()
    report=fixture/'report.json'
    subprocess.run([str(executable),'--v2ray-dir',str(fixture),'--diagnose',str(report)],check=True,timeout=30)
    result=json.loads(report.read_text())
    assert Path(result['client']).resolve()==fixture.resolve()
    assert result['panel'] and result['editor'] and result['traffic_helper']
print('PASS: portable resources, isolated client discovery, archive contents and SHA-256')
