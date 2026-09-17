# -*- coding: utf-8 -*-
"""
번역된 TSV 를 게임 파일에 되넣는다.

  python reinsert.py --check    용량 점검만 (원문 그대로 재구축해 여유를 잰다)
  python reinsert.py            build/ 에 패치된 파일들을 만든다

번역문은 길이가 달라지므로 제자리 덮어쓰기가 아니라 **구조를 다시 만든다**.
오프셋 테이블을 새로 계산하고, 컨테이너(PFS)와 압축(.CMP)까지 다시 만든 뒤
원래 배정 공간에 들어가는지 확인한다.

  사쿠라1 tbl : u16BE 테이블워드수 | u16BE ? | n×{u16BE id, u16BE 오프셋(워드)} | 텍스트
                오프셋이 u16(워드) 이므로 텍스트 블록은 최대 128 KiB
  사쿠라2 SK  : u32LE 헤더 [2]=인덱스 [3]=텍스트 [4]=전체크기, 인덱스는 16비트 단위
  사쿠라2 MES : u32BE count | count×u32BE 절대오프셋 | 엔트리(4B 헤더+텍스트)
                뒤에 립싱크 블록이 붙어 있어 **원래 위치를 유지**해야 한다
"""
import os, sys, csv, struct, collections, io

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from encode import s1_encode, s2_encode, EncodeError
from pfs import entries as pfs_entries
from text_dump import parse_tbl, parse_mes
from sk_text import parse as parse_sk
from cmp import decompress
from cmp_compress import compress

ROOT  = r"D:\psp\사쿠라대전1_2"
SRC   = os.path.join(ROOT, "extract", "PSP_GAME", "USRDIR")
TEXT  = os.path.join(ROOT, "text")
BUILD = os.path.join(ROOT, "build", "patched")

# ---------------------------------------------------------------- 번역문 적재
def load_text():
    """key -> 넣을 문자열. ko 가 비어 있으면 원문 ja 를 그대로 쓴다."""
    out, n_ko = {}, 0
    for fn in ("sakura1_adv.tsv", "sakura1_slg.tsv", "sakura2_adv.tsv", "sakura2_evt.tsv"):
        p = os.path.join(TEXT, fn)
        if not os.path.exists(p): continue
        with open(p, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
                ko = (r.get('ko') or '').strip()
                if ko: n_ko += 1
                out[r['key']] = (ko or r['ja']).replace('\\n', '\n').replace('\\t', '\t')
    return out, n_ko

# ---------------------------------------------------------------- 사쿠라 1
def build_tbl(orig, keyfmt, texts, cap=None):
    """사쿠라1 tbl.bin 재구축.

    구조 (모두 빅엔디안, 오프셋은 **워드** 단위)

        +0x00  u16  W = 메시지 수 x 2
        +0x02  u16  U = 립싱크 블록 시작 (워드)
        +0x04       [u16 id][u16 off] x n
                    메시지마다  [u16 음성번호][u16 립싱크오프셋][본문 ... 00]
                                off 는 **본문**을 가리킨다 (앞 4바이트 뒤)
                    립싱크 블록

    엔진(0x8a7f9e8)이 하는 일 — 역어셈블로 확인:

        본문   = buf + (W + off + 2)*2
        음성   = BE16(본문 - 4)     0 이면 음성 없음, 0xFFFF 면 0으로
        립싱크 = buf + (U + BE16(본문 - 2))*2

    **본문 앞 4바이트를 반드시 살려야 한다.** 예전에는 본문만 이어 붙이고
    off 를 그 앞으로 잡아서, 그 4바이트 자리에 **앞 메시지의 꼬리**가
    들어갔다. 그래서 사쿠라1 대사 음성이 통째로 안 나왔다
    (이슈 #5 #8 #9 #10). 0100tbl.bin 을 세어 보면 634개 중 170개가
    음성 번호를 갖고 있고, 그 수는 1장 립싱크 블록의 비어 있지 않은
    레코드 수와 정확히 같다.

    **립싱크 블록은 옮겨도 된다.** 자리를 머리표의 U 에서 읽기 때문이다.
    (예전에는 그걸 몰라서 블록을 원래 절대 위치에 못박고 앞을 0으로 채웠다.)
    한국어가 길어져 본문 구역이 넘치면 블록을 뒤로 밀고 U 를 고쳐 쓴다.

    같은 문장은 **앞 4바이트까지 같을 때만** 합친다. 음성 번호가 다르면
    같은 문장이라도 따로 둬야 한다.
    """
    W = struct.unpack_from('>H', orig, 0)[0]
    n = W // 2
    U0 = struct.unpack_from('>H', orig, 2)[0]
    ids = [struct.unpack_from('>HH', orig, 4 + k*4)[0] for k in range(n)]
    o_offs = [struct.unpack_from('>HH', orig, 4 + k*4)[1] for k in range(n)]
    base = 4 + n*4

    # 메시지마다 본문 앞 4바이트(음성 번호, 립싱크 오프셋)를 원본에서 떠 온다.
    # 0번 메시지는 그 4바이트가 엔트리표 마지막 칸과 겹친다 (원본이 0으로 비워 둔다).
    pre = []
    for o in o_offs:
        p = base + o*2 - 4
        pre.append(bytes(orig[p:p+4]) if p >= 0 else b'\x00'*4)

    # 립싱크 블록. 뒤에 붙은 NUL 채움은 덜어낸다 (마지막 레코드의 끝 표시는 남긴다).
    # 58개 멤버를 합치면 48 KB 라, 한국어가 길어진 만큼을 여기서 되찾는다.
    blk = orig[U0*2:]
    blk = blk[:min(len(blk), len(blk.rstrip(bytes(1))) + 2)]

    blob, pos, offs = bytearray(), {}, []
    for k in range(n):
        t = texts.get(keyfmt(k))
        key = (pre[k], t)
        if key not in pos:
            if len(blob) % 2: blob += b'\x00'
            blob += pre[k]
            pos[key] = len(blob)             # 오프셋은 **본문**을 가리킨다
            blob += (s1_encode(t) if t is not None else b'') + b'\x00'
        offs.append(pos[key])
    if len(blob) % 2: blob += b'\x00'

    for o in offs:
        if o // 2 > 0xFFFF:
            raise EncodeError("본문 구역이 u16 워드 오프셋 한계(128 KiB)를 넘음")

    out = bytearray(struct.pack('>HH', W, 0))
    for i, o in zip(ids, offs):
        out += struct.pack('>HH', i, o // 2)
    assert len(out) == base
    out += blob
    if len(out) % 2: out += b'\x00'
    U = len(out) // 2
    if U > 0xFFFF:
        raise EncodeError("립싱크 블록 위치가 u16 워드 한계를 넘음")
    struct.pack_into('>H', out, 2, U)        # 블록이 옮겨간 자리를 머리표에 적는다
    out += blk

    if cap is not None and len(out) > cap:
        raise EncodeError(f"{len(out):,}B 가 배정 공간 {cap:,}B 를 넘음")
    return bytes(out)

def build_pfs(src_path, member_filter, keyprefix, texts, report):
    """PFS 안의 텍스트 멤버만 갈아 끼운다. **멤버는 원래 자리에 그대로 둔다.**

    예전에는 컨테이너를 처음부터 다시 쌓았다. 원본에 빈틈이 없는 파일
    (ADVMACRO/ADVMISC)에서는 결과가 원본과 같아서 눈치채지 못했는데,
    빈틈이 있는 SLGMAP.PFS 에서는 **멤버 325개가 전부 다른 섹터로 옮겨간다**.
    머리표를 다시 써 주니 논리적으로는 맞지만, 실기에서는 이런 이동이
    그대로 검은 화면이 된다. 자리를 안 건드리는 쪽이 맞다.

    원본 바이트열을 바탕에 두고 바뀐 멤버만 제자리에 덮어쓴다.
    바꿀 것이 없으면 결과는 원본과 바이트까지 같다.
    """
    d = open(src_path, 'rb').read()
    out = bytearray(d)
    mem = pfs_entries(d)
    offs = sorted(o for _, o, _ in mem)
    for i, (name, off, sz) in enumerate(mem):
        if not member_filter(name.lower()): continue
        stem = os.path.splitext(name)[0]
        nxt = next((o for o in offs if o > off), len(d))
        body = build_tbl(d[off:off+sz], lambda k, s=stem: f"{keyprefix}:{s}:{k}",
                         texts, cap=nxt - off)
        out[off:off+len(body)] = body
        if len(body) < sz:                    # 짧아졌으면 남은 원본 바이트를 지운다
            out[off+len(body):off+sz] = b'\x00' * (sz - len(body))
        struct.pack_into('>I', out, 0x10 + i*24 + 20, len(body))
    report(os.path.basename(src_path), len(d), len(out))
    return bytes(out)

# ---------------------------------------------------------------- 사쿠라 2 SK
def build_sk(raw, stem, texts, report):
    dec, *_ = decompress(raw)
    r = parse_sk(dec)
    if r is None: return raw
    tbl, txt, _ = r
    # parse_sk 는 범위를 벗어난 엔트리를 걸러내므로, 인덱스 테이블을 직접 읽는다
    n = (txt - tbl)//4
    blob, pos, offs = bytearray(), {}, []
    for i in range(n):
        t = texts.get(f"S2A:{stem}:{i}")
        if t is None: t = ''
        if t not in pos:
            pos[t] = len(blob)
            blob += s2_encode(t) + b'\xff\xff'
        offs.append(pos[t] // 2)
    out = bytearray(dec[:tbl])
    for o in offs: out += struct.pack('<I', o)
    assert len(out) == txt
    out += blob
    struct.pack_into('<I', out, 16, len(out))          # 헤더[4] = 전체 크기
    # 압축을 푼 크기가 원본의 0x800 올림을 넘으면 안 된다.
    # SK1007 이 12,262B -> 12,438B 로 0x3000 을 넘었을 때만 10장 「무사시여……」
    # 장면에서 진행이 멈췄다 (83개 중 이 파일만 경계를 넘었고, 이 파일만 멈췄다).
    # 게임이 이 크기 단위로 버퍼를 잡는 것으로 보인다.
    cap = -(-len(dec) // 0x800) * 0x800
    if len(out) > cap:
        raise EncodeError(f"{stem}.CMP: 압축 푼 크기 {len(out):,}B 가 원본 {len(dec):,}B 의 "
                          f"0x800 올림({cap:,}B)을 넘음 — 번역을 {len(out)-cap}B 줄이세요")
    enc = compress(bytes(out))
    report(stem + '.CMP', len(raw), len(enc))
    return enc

# ---------------------------------------------------------------- 사쿠라 2 MES
def build_mes(d, stem, texts, report):
    n = struct.unpack_from('>I', d, 0)[0]
    if n == 0 or 4 + n*4 > len(d):
        return d                              # 메시지가 없는 파일은 그대로
    offs = list(struct.unpack_from(f'>{n}I', d, 4))
    ent = parse_mes(d)
    # 립싱크 블록: 마지막 메시지의 0xFFFF 뒤부터 파일 끝까지
    last = max(offs)
    j = last + 4
    while j + 1 < len(d) and not (d[j] == 0xFF and d[j+1] == 0xFF): j += 2
    tail_at = j + 2
    tail = d[tail_at:]

    base = 4 + n*4
    blobs = [hdr + s2_encode(texts.get(f"S2:{stem}:{i}", '')) + b'\xff\xff'
             for i, hdr, _ in ent]

    # 립싱크 블록은 **원래 절대 위치를 반드시 지킨다**. 게임이 그 위치를 알고 있을 수
    # 있어서다. 메시지 오프셋 표는 절대값이라 메시지가 이어 붙어 있을 필요가 없으므로,
    #   1) 립싱크 앞 빈 자리에 들어가는 메시지를 먼저 채우고
    #   2) 넘치는 메시지는 립싱크 **뒤에** 둔다
    # 한 개가 안 들어간다고 멈추지 않고 계속 훑어 앞 공간을 최대한 쓴다.
    new_offs = [0]*n
    gap, cur, spill = bytearray(), base, []
    for k, b in enumerate(blobs):
        if cur + len(b) <= tail_at:
            new_offs[k] = cur; gap += b; cur += len(b)
        else:
            spill.append(k)

    out = bytearray(struct.pack('>I', n) + b'\x00'*(n*4) + bytes(gap))
    out = bytearray(out.ljust(tail_at, b'\x00')) + bytearray(tail)
    for k in spill:
        new_offs[k] = len(out); out += blobs[k]
    for k, o in enumerate(new_offs):
        struct.pack_into('>I', out, 4 + k*4, o)

    report(stem + '.MES', len(d), len(out),
           '' if not spill else f'{len(spill)}개 메시지를 립싱크 뒤로')
    return bytes(out)

# ---------------------------------------------------------------- main
def main(check_only):
    texts, n_ko = load_text()
    print(f"번역문 적재: {len(texts)}행 (ko 채워진 행 {n_ko})")
    if not check_only: os.makedirs(BUILD, exist_ok=True)

    rows = []
    def rep(name, old, new, note=''):
        rows.append((name, old, new, note))

    jobs = [
        ("ADVMACRO.PFS", os.path.join(SRC, r"SAKURA1\SAKURA1\ADVMACRO.PFS"),
         lambda: build_pfs(os.path.join(SRC, r"SAKURA1\SAKURA1\ADVMACRO.PFS"),
                           lambda s: s.endswith('tbl.bin'), 'S1A', texts, rep)),
        ("SLGMAP.PFS", os.path.join(SRC, r"SAKURA1\SAKURA2\SLGMAP.PFS"),
         lambda: build_pfs(os.path.join(SRC, r"SAKURA1\SAKURA2\SLGMAP.PFS"),
                           lambda s: s.endswith('mes.bin'), 'S1S', texts, rep)),
    ]
    for name, path, fn in jobs:
        if not os.path.exists(path):
            print(f"  건너뜀 {name} (원본 없음 — iso_extract.py 로 추출 필요)"); continue
        data = fn()
        if not check_only: open(os.path.join(BUILD, name), 'wb').write(data)

    skdir = os.path.join(SRC, "SAKURA2", "SAKURA1")
    for fn in sorted(os.listdir(skdir)) if os.path.isdir(skdir) else []:
        if not (fn.startswith('SK') and fn.upper().endswith('.CMP')): continue
        raw = open(os.path.join(skdir, fn), 'rb').read()
        data = build_sk(raw, os.path.splitext(fn)[0], texts, rep)
        if not check_only: open(os.path.join(BUILD, fn), 'wb').write(data)

    mesdir = os.path.join(SRC, "SAKURA2", "SAKURA2")
    for fn in sorted(os.listdir(mesdir)) if os.path.isdir(mesdir) else []:
        if not fn.upper().endswith('.MES'): continue
        d = open(os.path.join(mesdir, fn), 'rb').read()
        data = build_mes(d, os.path.splitext(fn)[0], texts, rep)
        if not check_only: open(os.path.join(BUILD, fn), 'wb').write(data)

    grew = [r for r in rows if r[2] > r[1]]
    warn = [r for r in rows if r[3]]
    print(f"\n재구축 {len(rows)}개 파일")
    print(f"  원본보다 커진 파일 {len(grew)}개")
    for name, old, new, note in sorted(grew, key=lambda r: r[1]-r[2])[:8]:
        print(f"    {name:<18} {old:8d} -> {new:8d}  (+{new-old})")
    if warn:
        print(f"  경고 {len(warn)}개")
        for name, old, new, note in warn[:8]: print(f"    {name}: {note}")
    if not check_only: print(f"\n-> {BUILD}")

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main('--check' in sys.argv)
