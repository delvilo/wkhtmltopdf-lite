#!/usr/bin/env python3
"""Reject Qt/ICU/JPEG runtime leaks and build-host paths in our Linux ELFs.

Run only on trusted binaries built from this repository (ldd loads the ELF).
SPDX-License-Identifier: LGPL-3.0-or-later
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

# ABI names shared by the Ubuntu 24.04 builder and Debian 13 runtime. Changes to
# this list must also update docs/portable-linux.md and the clean runtime test.
ALLOWED = set("""
ld-linux-x86-64.so.2 libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1
libresolv.so.2 libstdc++.so.6 libgcc_s.so.1 libfontconfig.so.1 libfreetype.so.6
libexpat.so.1 libpng16.so.16 libz.so.1 libbrotlidec.so.1 libbrotlicommon.so.1
libbz2.so.1.0 libssl.so.3 libcrypto.so.3 libpcre2-16.so.0 libpcre2-8.so.0
libzstd.so.1 liblzma.so.5
""".split())


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def inspect(binary):
    binary = Path(binary).resolve(strict=True)
    header = run("readelf", "-h", str(binary))
    if not re.search(r"Machine:\s+Advanced Micro Devices X86-64", header):
        raise ValueError(f"{binary}: only x86_64 is qualified for this package")
    dynamic = run("readelf", "-d", str(binary))
    if re.search(r"\((?:RPATH|RUNPATH)\)", dynamic):
        raise ValueError(f"{binary}: RPATH/RUNPATH must be absent")
    needed = sorted(set(re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic)))
    linked = run("ldd", str(binary))
    if "not found" in linked:
        raise ValueError(f"{binary}: missing runtime library:\n{linked}")
    dependencies = set(needed)
    for line in linked.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("linux-vdso"):
            continue
        dependencies.add(Path(fields[0]).name)
    unexpected = dependencies - ALLOWED
    if unexpected:
        raise ValueError(f"{binary}: unapproved shared dependencies: {sorted(unexpected)}")
    versions = run("readelf", "--version-info", str(binary))
    required = {}
    for family, maximum in (("GLIBC", (2, 39)), ("GLIBCXX", (3, 4, 33))):
        found = [tuple(map(int, v.split('.'))) for v in
                 re.findall(rf"Name: {family}_([0-9.]+)", versions)]
        if found:
            required[family] = '.'.join(map(str, max(found)))
            if max(found) > maximum:
                raise ValueError(f"{binary}: requires {family}_{required[family]}, above the runtime baseline")
    return {"binary": binary.name, "needed": needed,
            "dependencies": sorted(dependencies), "symbol_versions": required}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binaries", nargs='+')
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = [inspect(binary) for binary in args.binaries]
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Portable runtime check failed: {error}\n")
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
