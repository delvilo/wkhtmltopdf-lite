#!/usr/bin/env python3
"""Package both executables, full notices and matching rebuildable sources.

SPDX-License-Identifier: LGPL-3.0-or-later
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'static-build')
    parser.add_argument('--build', type=Path, default=ROOT / 'build/portable')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/packages')
    args = parser.parse_args()
    work, build, output = args.work.resolve(), args.build.resolve(), args.output.resolve()
    # An immutable application revision keeps source and binaries reviewable.
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT):
        parser.error('Commit application/build-script changes before creating release archives')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    cache = dict(line.split('=', 1) for line in (build / 'CMakeCache.txt').read_text().splitlines()
                 if '=' in line and not line.startswith(('//', '#')))
    if (Path(cache.get('CMAKE_HOME_DIRECTORY:INTERNAL', '/')) != ROOT or
            cache.get('WKHTMLTOX_PORTABLE:BOOL') != 'ON' or
            Path(cache.get('QT5_STATIC_PREFIX:PATH', '/')).resolve() != work / 'qt'):
        parser.error('Use this checkout and the selected work directory for the portable CMake build')
    recipe_hash = hashlib.sha256((ROOT / 'tools/portable/build-toolchain.sh').read_bytes()).hexdigest()
    if (work / 'toolchain-recipe.sha256').read_text().split()[0] != recipe_hash:
        parser.error('The toolchain was built with a different recipe; rebuild it before packaging')
    name = f'wkhtmltox-linux-x86_64-{revision[:12]}'
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('portable_sources', ROOT / 'tools/portable/sources.py')
    sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sources)
    # Fail rather than publishing binaries with missing/incomplete LGPL sources.
    source_trees, source_files = [], set()
    for line in (work / 'source-packages.txt').read_text().splitlines():
        package, version = line.split('=', 1)
        tree = work / 'sources' / package
        if (tree / '.wkhtmltox-extracted').read_text().strip() != version:
            raise RuntimeError(f'Missing matching expanded source tree: {package}={version}')
        source_trees.append(tree)
        dsc = work / 'sources/archives' / f'{package}_{version.split(":")[-1]}.dsc'
        source_files.add(dsc)
        for digest, size, filename in sources.checksums(dsc):
            path = dsc.parent / filename
            if path.stat().st_size != size or hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != digest:
                raise RuntimeError(f'Incomplete corresponding source: {path}')
            source_files.add(path)
    # Rebuild from this clean revision rather than labeling stale executables
    # with a newly committed application's source hash.
    subprocess.run(['cmake', '--build', str(build), '--parallel', '2'], check=True)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        stage = Path(temp) / name
        (stage / 'bin').mkdir(parents=True)
        for app in ('wkhtmltopdf', 'wkhtmltoimage'):
            shutil.copy2(build / 'bin' / app, stage / 'bin' / app)
            subprocess.run(['strip', '--strip-unneeded', str(stage / 'bin' / app)], check=True)
        subprocess.run(['python3', str(ROOT / 'tools/portable/check-runtime.py'),
                        *map(str, sorted((stage / 'bin').iterdir())),
                        '--output', str(stage / 'runtime-dependencies.json')], check=True)
        shutil.copytree(work / 'licenses', stage / 'licenses')
        for filename in ('LICENSE', 'COPYING.GPLv3', 'THIRD_PARTY_NOTICES.md'):
            shutil.copy2(ROOT / filename, stage / filename)
        shutil.copy2(ROOT / 'docs/portable-linux.md', stage / 'README.md')
        for filename in ('build-packages.tsv', 'source-packages.txt', 'toolchain-recipe.sha256'):
            shutil.copy2(work / filename, stage / filename)
        (stage / 'build-manifest.txt').write_text(
            f'Application: {revision}\nBuilder: Ubuntu 24.04 x86_64\n'
            f'Corresponding sources: {name}-sources.tar.xz\n')
        # Include expanded, actually built trees as well as original archives:
        # this also preserves local changes when relinking modified libraries.
        source_archive = output / f'{name}-sources.tar.xz'
        app_tar = Path(temp) / 'application.tar'
        subprocess.run(['git', 'archive', '--format=tar', f'--output={app_tar}', 'HEAD'], cwd=ROOT, check=True)
        with tarfile.open(source_archive, 'w:xz') as tar:
            with tarfile.open(app_tar) as app:
                for member in app:
                    data = app.extractfile(member) if member.isfile() else None
                    member.name = f'{name}-sources/application/{member.name}'
                    tar.addfile(member, data)
            for tree in source_trees:
                tar.add(tree.resolve(), arcname=f'{name}-sources/dependencies/{tree.name}')
            for path in sorted(source_files):
                tar.add(path, arcname=f'{name}-sources/dependencies/archives/{path.name}')
            for filename in ('build-packages.tsv', 'source-packages.txt', 'toolchain-recipe.sha256'):
                tar.add(work / filename, arcname=f'{name}-sources/{filename}')
        with tarfile.open(output / f'{name}.tar.xz', 'w:xz') as tar:
            tar.add(stage, arcname=name)
    archives = [output / f'{name}.tar.xz', source_archive]
    (output / f'{name}.sha256').write_text(''.join(
        f'{hashlib.file_digest(path.open("rb"), "sha256").hexdigest()}  {path.name}\n' for path in archives))
    print('\n'.join(map(str, archives)))


if __name__ == '__main__':
    main()
