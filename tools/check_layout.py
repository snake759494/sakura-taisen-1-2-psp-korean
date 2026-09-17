# -*- coding: utf-8 -*-
"""패치한 파일이 **원본과 같은 배치**인지 본다.

  python tools/check_layout.py

내용이 맞아도 배치가 틀리면 실기에서 죽는다. 실제로 그랬다.

  - .SPR 416개가 **예외 없이** 첫 청크를 0x100 에 둔다. 그런데 spr_write 가
    청크를 처음부터 다시 쌓아서 0x30 으로 당겨졌다. 에뮬레이터는 그냥
    돌아가지만 실기에서는 컷신 뒤 검은 화면에서 멈춘다.
  - .PFS 는 멤버를 섹터 단위로 다시 깔았다. 빈틈이 있는 SLGMAP.PFS 에서
    멤버 325개가 통째로 다른 섹터로 옮겨갔다.

둘 다 "게임이 머리표를 읽으니 괜찮겠지" 하고 넘어갔던 것이다. 안 괜찮았다.
그래서 **바꾼 파일은 원본과 같은 자리·같은 크기**를 지키는지 매번 확인한다.

검사 항목
  1. 파일 크기        원본과 같은가 (커지면 섹터 배정 초과, 작아지면 왜?)
  2. .SPR             청크 오프셋·크기, 그림 수, 각 그림의 w/h/fmt/팔레트뱅크,
                      압축을 푼 픽셀 길이
  3. .PFS             멤버 이름·오프셋·크기
  4. .CMP             압축을 푼 길이
"""
import os, sys, io, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spr, spr_write
from pfs import entries as pfs_entries
from cmp import decompress
from build_iso import walk_iso, SRC_ISO, SECTOR, collect


def spr_shape(d):
    """(청크자리들, 그림 정보들) — 배치와 내용을 한 번에 비교할 수 있는 형태"""
    ch = spr.chunks(d)
    if not ch: return None
    places = [(o, s, i) for o, s, i, _ in ch]
    pics = None
    for o, s, i, b in ch:
        cnt, e, db = spr.entries(b)
        if cnt and any(t[5] for t in e):
            pics = [(t[0], t[1], t[2], t[3], len(spr_write.raw_px(b, t, db))) for t in e]
            break
    return places, pics


def pfs_shape(d):
    try: return [(n, o, s) for n, o, s in pfs_entries(d)]
    except Exception: return None


def check():
    f = open(SRC_ISO, 'rb')
    table = walk_iso(f)
    rep = collect(table, 'normal')
    bad, grew, shrank = [], [], []
    for iso_path in sorted(rep):
        new_path = rep[iso_path]
        _, lba, sz = table[iso_path]
        f.seek(lba*SECTOR); a = f.read(sz)
        b = open(new_path, 'rb').read()
        name = iso_path.rsplit('/', 1)[-1]
        u = name.upper()

        if len(b) > len(a): grew.append((iso_path, len(a), len(b)))
        elif len(b) < len(a): shrank.append((iso_path, len(a), len(b)))

        if u.endswith('.SPR'):
            sa, sb = spr_shape(a), spr_shape(b)
            if sa and sb:
                if sa[0] != sb[0]:
                    bad.append((iso_path, f"청크 자리 {sa[0]} -> {sb[0]}"))
                elif sa[1] and sb[1]:
                    if len(sa[1]) != len(sb[1]):
                        bad.append((iso_path, f"그림 수 {len(sa[1])} -> {len(sb[1])}"))
                    else:
                        for k, (x, y) in enumerate(zip(sa[1], sb[1])):
                            if x != y:
                                bad.append((iso_path, f"#{k} {x} -> {y}")); break
        elif u.endswith('.PFS'):
            pa, pb = pfs_shape(a), pfs_shape(b)
            if pa and pb:
                if len(pa) != len(pb):
                    bad.append((iso_path, f"멤버 수 {len(pa)} -> {len(pb)}"))
                else:
                    mv = [x[0] for x, y in zip(pa, pb) if x[0] != y[0] or x[1] != y[1]]
                    if mv: bad.append((iso_path, f"자리가 바뀐 멤버 {len(mv)}개: {mv[:4]}"))
        elif u.endswith('.CMP'):
            try:
                la, lb = len(decompress(a)[0]), len(decompress(b)[0])
                # 사쿠라2 본편 SK####.CMP 는 원본의 0x800 올림까지만 커질 수 있다
                # (SK1007 이 0x3000 을 넘자 10장에서 진행이 멈췄다). 나머지는 같아야 한다.
                cap = -(-la // 0x800) * 0x800 if (u.startswith('SK') or u.endswith('LOW.CMP')) else la
                if lb > cap: bad.append((iso_path, f"압축 푼 길이 {la:,} -> {lb:,} (상한 {cap:,})"))
            except Exception as e:
                bad.append((iso_path, f"압축 풀기 실패: {e}"))
    f.close()

    print(f"\n검사한 교체 파일 {len(rep)}개")
    print(f"  크기 커진 파일 {len(grew)}개, 작아진 파일 {len(shrank)}개")
    for p, o, n in grew[:6]:  print(f"    + {p.rsplit('/',1)[-1]:<18} {o:>9,} -> {n:>9,}")
    print(f"  배치·구조가 어긋난 파일 {len(bad)}개")
    for p, why in bad[:20]:   print(f"    ✘ {p}  {why}")
    return len(bad)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(1 if check() else 0)
