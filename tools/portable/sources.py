#!/usr/bin/env python3
"""Fetch authenticated Ubuntu sources, verify their hashes, and preserve notices.

SPDX-License-Identifier: LGPL-3.0-or-later
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess


def checksums(dsc):
    in_block = False
    result = []
    for line in dsc.read_text().splitlines():
        if line == 'Checksums-Sha256:':
            in_block = True
        elif in_block:
            if not line.startswith(' '):
                break
            digest, size, filename = line.split()
            if Path(filename).name != filename:
                raise ValueError(f'Unsafe source filename: {filename}')
            result.append((digest, int(size), filename))
    if not result:
        raise ValueError(f'No SHA256 checksums in {dsc}')
    return result


def fetch(root, package, version):
    archives = root / 'archives'
    archives.mkdir(parents=True, exist_ok=True)
    # apt verifies signed source-index hashes; verify the .dsc payloads again
    # before extraction and on reuse (interrupted downloads must not be cached).
    filename_version = version.split(':')[-1]
    dsc = archives / f'{package}_{filename_version}.dsc'
    if not dsc.exists() or any(not (archives / f).exists() for _, _, f in checksums(dsc)):
        subprocess.run(['apt-get', 'source', '--download-only', f'{package}={version}'],
                       cwd=archives, check=True)
    for digest, size, filename in checksums(dsc):
        path = archives / filename
        if path.stat().st_size != size or hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != digest:
            raise ValueError(f'Incomplete/corrupt source: {path}; remove it and retry')
    source = root / package
    stamp = source / '.wkhtmltox-extracted'
    if not stamp.exists():
        if source.exists():
            raise ValueError(f'Incomplete source directory {source}; remove it and retry')
        subprocess.run(['dpkg-source', '-x', str(dsc), str(source)], check=True)
        stamp.write_text(version + '\n')
    elif stamp.read_text().strip() != version:
        raise ValueError(f'{source} contains another version; use a fresh work directory')
    return source


def preserve_notices(source, destination):
    for path in source.rglob('*'):
        name = path.name.lower()
        if path.is_file() and not path.is_symlink() and (
                name.startswith(('license', 'licence', 'copying', 'copyright')) or name == 'ftl.txt'):
            target = destination / source.name / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('specifications', nargs='+', help='source-package=version')
    parser.add_argument('--licenses', type=Path, required=True)
    args = parser.parse_args()
    for spec in dict.fromkeys(args.specifications):
        package, version = spec.split('=', 1)
        source = fetch(args.root.resolve(), package, version)
        preserve_notices(source, args.licenses)
    common = args.licenses / 'common-licenses'
    shutil.copytree('/usr/share/common-licenses', common, dirs_exist_ok=True, symlinks=False)


if __name__ == '__main__':
    main()
