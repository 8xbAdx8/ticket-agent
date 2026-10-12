"""一次性只读 Word 97-2003 正文抽取，选装 olefile；不转换原文件。"""
import struct
import sys
from pathlib import Path
import olefile


def extract(path):
    with olefile.OleFileIO(path) as ole:
        word = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", word, 10)[0]
        table = ole.openstream("1Table" if flags & 0x200 else "0Table").read()
        # FibRgFcLcb97.fcClx / lcbClx: Word 97 FIB fixed offsets.
        offset, length = struct.unpack_from("<II", word, 0x1A2)
        clx = table[offset:offset + length]
        pos = 0
        while clx[pos] == 1:
            pos += 3 + struct.unpack_from("<H", clx, pos + 1)[0]
        if clx[pos] != 2:
            raise ValueError("不支持此 Word piece table")
        size = struct.unpack_from("<I", clx, pos + 1)[0]
        plc = clx[pos + 5:pos + 5 + size]
        n = (size - 4) // 12
        cps = struct.unpack_from(f"<{n+1}I", plc)
        parts = []
        for i in range(n):
            fc = struct.unpack_from("<I", plc, 4*(n+1) + 8*i + 2)[0]
            count = cps[i+1] - cps[i]
            compressed = bool(fc & 0x40000000)
            start = (fc & 0x3fffffff) // (2 if compressed else 1)
            raw = word[start:start + count*(1 if compressed else 2)]
            parts.append(raw.decode("cp1252" if compressed else "utf-16le", errors="replace"))
        return "".join(parts).replace("\r", "\n").replace("\x07", "\t")


if __name__ == "__main__":
    print(extract(Path(sys.argv[1])))
