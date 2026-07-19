#!/usr/bin/env python
"""Download only the required E. coli/ciprofloxacin assets from Zenodo.

The upstream ZIP is more than 5 GB. Zenodo supports HTTP range requests, so
this script reads the ZIP central directory and downloads four small entries
without downloading the entire archive.
"""

from __future__ import annotations

import argparse
import binascii
import struct
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path


ARCHIVE_URL = (
    "https://zenodo.org/api/records/16213507/files/"
    "models_and_ShapValues.zip/content"
)
ARCHIVE_SIZE = 5_170_575_152
TARGETS = {
    "ciprofloxacin_xgboost_kmer_3.pkl": "ecoli_ciprofloxacin_xgb.pkl",
    "ciprofloxacin_feature_names_filtered_xgboost_kmer_3_Escherichia.txt": (
        "feature_names.txt"
    ),
    "ciprofloxacin_xgboost_kmer_3_genus_metrics.csv": "upstream_genus_metrics.csv",
    "ciprofloxacin_xgboost_kmer_3_Escherichia_output.txt": (
        "upstream_escherichia_output.txt"
    ),
}


@dataclass(frozen=True)
class ZipEntry:
    name: str
    compression: int
    compressed_size: int
    uncompressed_size: int
    crc32: int
    local_header_offset: int


def fetch_range(start: int, end: int) -> bytes:
    request = urllib.request.Request(
        ARCHIVE_URL,
        headers={"Range": f"bytes={start}-{end}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206:
            raise RuntimeError(f"Zenodo did not honor range request: {response.status}")
        return response.read()


def central_directory() -> bytes:
    tail = fetch_range(ARCHIVE_SIZE - 131_072, ARCHIVE_SIZE - 1)
    locator_position = tail.rfind(b"PK\x06\x07")
    if locator_position < 0:
        raise RuntimeError("ZIP64 locator not found")
    zip64_offset = struct.unpack_from("<Q", tail, locator_position + 8)[0]
    record = fetch_range(zip64_offset, zip64_offset + 55)
    if record[:4] != b"PK\x06\x06":
        raise RuntimeError("ZIP64 end record not found")
    directory_size, directory_offset = struct.unpack_from("<QQ", record, 40)
    return fetch_range(directory_offset, directory_offset + directory_size - 1)


def zip64_values(
    extra: bytes,
    compressed_size: int,
    uncompressed_size: int,
    local_offset: int,
) -> tuple[int, int, int]:
    position = 0
    while position + 4 <= len(extra):
        field_id, field_size = struct.unpack_from("<HH", extra, position)
        payload = extra[position + 4 : position + 4 + field_size]
        if field_id == 1:
            value_position = 0
            if uncompressed_size == 0xFFFFFFFF:
                uncompressed_size = struct.unpack_from("<Q", payload, value_position)[0]
                value_position += 8
            if compressed_size == 0xFFFFFFFF:
                compressed_size = struct.unpack_from("<Q", payload, value_position)[0]
                value_position += 8
            if local_offset == 0xFFFFFFFF:
                local_offset = struct.unpack_from("<Q", payload, value_position)[0]
            return compressed_size, uncompressed_size, local_offset
        position += 4 + field_size
    return compressed_size, uncompressed_size, local_offset


def find_entries(directory: bytes) -> dict[str, ZipEntry]:
    entries: dict[str, ZipEntry] = {}
    position = 0
    while position + 46 <= len(directory):
        if directory[position : position + 4] != b"PK\x01\x02":
            break
        compression = struct.unpack_from("<H", directory, position + 10)[0]
        crc32, compressed_size, uncompressed_size = struct.unpack_from(
            "<III",
            directory,
            position + 16,
        )
        name_size, extra_size, comment_size = struct.unpack_from(
            "<HHH",
            directory,
            position + 28,
        )
        local_offset = struct.unpack_from("<I", directory, position + 42)[0]
        name_start = position + 46
        name = directory[name_start : name_start + name_size].decode(
            "utf-8",
            "replace",
        )
        extra = directory[
            name_start + name_size : name_start + name_size + extra_size
        ]
        compressed_size, uncompressed_size, local_offset = zip64_values(
            extra,
            compressed_size,
            uncompressed_size,
            local_offset,
        )
        basename = Path(name).name
        if basename in TARGETS:
            entries[basename] = ZipEntry(
                name=name,
                compression=compression,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                crc32=crc32,
                local_header_offset=local_offset,
            )
        position += 46 + name_size + extra_size + comment_size
    return entries


def extract_entry(entry: ZipEntry) -> bytes:
    header = fetch_range(entry.local_header_offset, entry.local_header_offset + 29)
    if header[:4] != b"PK\x03\x04":
        raise RuntimeError(f"Local ZIP header not found for {entry.name}")
    name_size, extra_size = struct.unpack_from("<HH", header, 26)
    data_start = entry.local_header_offset + 30 + name_size + extra_size
    compressed = fetch_range(
        data_start,
        data_start + entry.compressed_size - 1,
    )
    if entry.compression == 0:
        content = compressed
    elif entry.compression == 8:
        content = zlib.decompress(compressed, -zlib.MAX_WBITS)
    else:
        raise RuntimeError(
            f"Unsupported ZIP compression method {entry.compression} for {entry.name}"
        )
    if len(content) != entry.uncompressed_size:
        raise RuntimeError(f"Size verification failed for {entry.name}")
    if binascii.crc32(content) & 0xFFFFFFFF != entry.crc32:
        raise RuntimeError(f"CRC verification failed for {entry.name}")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download minimal E. coli/ciprofloxacin AMRpredictor assets"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/models/amrpredictor"),
    )
    args = parser.parse_args()

    entries = find_entries(central_directory())
    missing = sorted(set(TARGETS) - set(entries))
    if missing:
        raise RuntimeError(f"Required archive entries not found: {', '.join(missing)}")

    args.output.mkdir(parents=True, exist_ok=True)
    for basename, output_name in TARGETS.items():
        content = extract_entry(entries[basename])
        output_path = args.output / output_name
        output_path.write_bytes(content)
        print(f"wrote {output_path} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
