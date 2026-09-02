# -*- coding: utf-8 -*-
"""사쿠라1 대사 음성이 원본과 똑같이 걸리는지 본다.

  python tools/check_voice.py

`tbl.bin` 은 메시지마다 **본문 앞 4바이트**에 [음성 번호][립싱크 오프셋]을
둔다. 번역문을 되넣을 때 본문만 이어 붙이면 그 자리에 앞 메시지의 꼬리가
들어가고, 게임은 그걸 음성 번호로 읽는다. v3.3 까지 사쿠라1 대사 음성이
통째로 안 나온 이유다 (이슈 #5 #8 #9 #10).

여기서는 엔진(`0x8a7f9e8`)과 **똑같은 계산**으로 원본과 패치본을 풀어
메시지마다 음성 번호와 립싱크 문자열을 대조한다.

    본문   = buf + (W + off + 2)*2
    음성   = BE16(본문 - 4)     0 이면 음성 없음, 0xFFFF 면 0 으로
    립싱크 = buf + (U + BE16(본문 - 2))*2
"""
import os, sys, io, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pfs import entries as pfs_entries
from build_iso import walk_iso, SRC_ISO, SECTOR

ROOT  = os.path.dirname(HERE)
BUILT = os.path.join(ROOT, "build", "patched", "ADVMACRO.PFS")


def resolve(a):
    """엔진과 같은 방식으로 {메시지 번호: (음성번호, 립싱크문자열)} 를 만든다."""
    W = struct.unpack_from('>H', a, 0)[0]
    n = W // 2
    U = struct.unpack_from('>H', a, 2)[0]
    out = {}
    for k in range(n):
        _, off = struct.unpack_from('>HH', a, 4 + k*4)
        x = struct.unpack_from('>H', a, (W + off) * 2)[0]
        y = struct.unpack_from('>H', a, (W + off + 1) * 2)[0]
        lp = (U + y) * 2
        out[k] = (0 if x == 0xFFFF else x,
                  a[lp:a.find(b'\x00', lp)] if x else b'')
    return out


def check():
    if not os.path.exists(BUILT):
        print("build/patched/ADVMACRO.PFS 가 없습니다 — reinsert.py 를 먼저 돌리세요")
        return 1
    with open(SRC_ISO, 'rb') as f:
        t = walk_iso(f)
        p = [x for x in t if x.upper().endswith('/ADVMACRO.PFS')][0]
        _, lba, sz = t[p]
        f.seek(lba * SECTOR)
        A = f.read(sz)
    B = open(BUILT, 'rb').read()
    EA = {n: (o, s) for n, o, s in pfs_entries(A)}
    EB = {n: (o, s) for n, o, s in pfs_entries(B)}

    tot = voiced = bad = 0
    worst = []
    for name in sorted(EA):
        if 'tbl' not in name: continue
        oa, za = EA[name]; ob, zb = EB[name]
        ra = resolve(A[oa:oa+za]); rb = resolve(B[ob:ob+zb])
        n = 0
        for k in ra:
            tot += 1
            if ra[k][0]: voiced += 1
            if ra[k] != rb.get(k): bad += 1; n += 1
        if n: worst.append((n, name))

    print(f"\n사쿠라1 본편 메시지 {tot:,}")
    print(f"  음성이 붙은 메시지 {voiced:,} ({voiced*100/max(tot,1):.1f}%)")
    print(f"  원본과 음성·립싱크가 어긋난 메시지 {bad:,}")
    for n, name in sorted(worst, reverse=True)[:8]:
        print(f"    ✘ {name}  {n:,}개")
    return bad


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(1 if check() else 0)
