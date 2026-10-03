"""Valida assets sin acceder a redes, workflows ni credenciales."""
import hashlib
import json
import struct
from pathlib import Path

root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / '05_Claude/manifest.json').read_text())
assets = manifest['assets']
logo = manifest['logo']
assert hashlib.sha256((root / logo['file']).read_bytes()).hexdigest() == logo['sha256'], 'El original del logo fue alterado'
assert len(assets) == 19, 'Se requieren 19 imágenes'
assert len({a['id'] for a in assets}) == 19, 'IDs duplicados'
assert len({a['file'] for a in assets}) == 19, 'Rutas duplicadas'
counts = {}
for a in assets:
    p = (root / a['file']).resolve()
    assert p.is_relative_to(root.resolve()), 'Ruta fuera del paquete'
    data = p.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f'No es PNG: {p.name}'
    size = struct.unpack('>II', data[16:24])
    expected = (1080, 1920 if a['type'] in ('story', 'reel_cover') else 1350)
    assert size == expected == (a['width'], a['height']), f'Tamaño incorrecto: {p.name}'
    assert hashlib.sha256(data).hexdigest() == a['sha256'], f'Hash incorrecto: {p.name}'
    counts[a['type']] = counts.get(a['type'], 0) + 1
assert counts == {'feed': 7, 'story': 7, 'reel_cover': 3, 'commercial_extra': 2}, counts
assert len(list(root.glob('0[1-4]_*/*.png'))) == 19, 'Archivos extra o faltantes'
print('OK: 19 PNG individuales, tamaños exactos, IDs únicos y hashes válidos.')
