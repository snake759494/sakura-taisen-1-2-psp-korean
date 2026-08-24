# -*- coding: utf-8 -*-
"""
.SPR 다시 쓰기 — 이미지 한 장을 갈아 끼운다.

바꾼 이미지는 spr_compress 로 **다시 압축**해 넣는다. fmt 상위 니블을 0 으로
두면 날것으로도 읽히지만(spr.py 머리말), 그러면 파일이 4~5배로 불어
ISO 의 배정 공간을 넘는다. 다시 압축하면 원본 대비 101% 쯤에서 그친다.

컨테이너는 청크표에 각 청크의 절대 오프셋과 크기가 들어 있으므로,
바뀐 이미지 청크만 새로 만들고 표를 다시 계산하면 된다.
다른 청크(애니메이션·히트박스)는 바이트 그대로 옮긴다.
"""
import os, sys, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spr, spr_compress

ALIGN = 16

def raw_px(body, ent, db):
    """엔트리 -> 압축을 푼 픽셀 바이트열 (bpp 상관없이)"""
    w, h, fmt, q, eo, es = ent
    need = w*h*spr.BPP[fmt & 0x0F]//8
    raw = body[db+eo: db+eo+es]
    return spr.lzss(raw, need)[0] if (fmt >> 4) else raw[:need]

def unpack_px(body, ent, db):
    """엔트리 -> (h, w) 팔레트 인덱스 배열 (4/8bpp 만)"""
    w, h, fmt, q, eo, es = ent
    bpp = spr.BPP[fmt & 0x0F]
    a = np.frombuffer(raw_px(body, ent, db), np.uint8)
    if bpp == 8:
        return a[:w*h].reshape(h, w).copy()
    if bpp == 4:                     # 하위 니블이 왼쪽 픽셀
        o = np.empty(w*h, np.uint8)
        o[0::2], o[1::2] = a & 0xF, a >> 4
        return o[:w*h].reshape(h, w).copy()
    raise ValueError(f"{bpp}bpp 는 인덱스 이미지가 아니다")

def unpack16(body, ent, db):
    """16bpp 이미지 -> (h, w) u16 배열 (빅엔디안 ABGR1555 값 그대로)"""
    w, h, fmt, q, eo, es = ent
    a = np.frombuffer(raw_px(body, ent, db), dtype='>u2')
    return a[:w*h].reshape(h, w).copy()

def rgb1555(v):
    """ABGR1555 -> (r, g, b) 0~31"""
    return (v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F)

def mk1555(r, g, b, a=1):
    return (a << 15) | (int(b) << 10) | (int(g) << 5) | int(r)

def pack_px(img, bpp):
    if bpp == 8: return img.astype(np.uint8).tobytes()
    if bpp == 16: return img.astype('>u2').tobytes()
    if bpp == 4:
        f = img.astype(np.uint8).reshape(-1)
        return ((f[1::2] << 4) | (f[0::2] & 0xF)).astype(np.uint8).tobytes()
    raise ValueError(bpp)

def rebuild(d, changes):
    """changes = {이미지번호: (h,w) 인덱스배열}. 새 .SPR 바이트열을 돌려준다.

    **원본 배치를 그대로 지킨다.**

    예전에는 청크를 처음부터 다시 쌓았다. 그러면 첫 청크가 0x100 에서
    0x30 으로 당겨진다. 그런데 이 게임에 든 .SPR 416개가 **예외 없이**
    첫 청크를 0x100 에 두고, 뒤 청크는 정렬 없이 붙여 쓴다. 지켜야 하는
    규칙이다 — 에뮬레이터는 넘어가지만 **실기에서는 그림이 안 나오고
    검은 화면에서 멈춘다** (PSP GE 는 텍스처·팔레트 주소 정렬을 탄다).

    그래서 원본 바이트열을 바탕으로 두고 **바뀐 그림만 제자리에 덮어쓴다**.
    새로 압축한 것이 원래 자리보다 크면 그것만 데이터 구역 끝에 붙인다.
    changes 가 비면 결과는 원본과 바이트까지 같다 (아래 자체 검사).
    """
    ch = spr.chunks(d)
    if not ch: raise ValueError("SPR 이 아니다")

    # 이미지 청크 찾기 — 장수·엔트리가 모두 말이 되는 청크
    img_i = None
    for k, (off, size, idx, body) in enumerate(ch):
        cnt, ents, db = spr.entries(body)
        if cnt and any(e[5] for e in ents):      # size 가 실제로 있는 것
            img_i = k; break
    if img_i is None: raise ValueError("이미지 청크를 못 찾음")

    off, size, idx, body = ch[img_i]
    cnt, ents, db = spr.entries(body)
    for i in changes:
        if not (0 <= i < cnt): raise ValueError(f"이미지 번호 {i} 없음 (장수 {cnt})")

    # 원본은 엔트리 데이터를 정렬 없이 빈틈없이 붙여 쓴다(412개 청크에서 확인).
    # 그러니 자리에 들어가면 제자리에, 안 들어가면 구역을 통째로 다시 쌓는다.
    enc, spill = {}, False
    for i in sorted(changes):
        w, h, fmt, q, eo, es = ents[i]
        raw = pack_px(changes[i], spr.BPP[fmt & 0x0F])
        # 원래 압축돼 있던 것은 다시 압축한다. 날것으로 두면 4~5배로 불어난다.
        enc[i] = spr_compress.compress(raw) if (fmt >> 4) else raw
        if len(enc[i]) > es: spill = True

    new = list(ents)
    if not spill:                                # 전부 원래 자리에 들어간다
        blob = bytearray(body[db:])
        for i, data in enc.items():
            w, h, fmt, q, eo, es = ents[i]
            blob[eo:eo+es] = data + b'\x00'*(es - len(data))
            new[i] = (w, h, fmt, q, eo, len(data))
    else:                                        # 구역을 원본처럼 빈틈없이 다시 쌓는다
        blob = bytearray()
        for i, (w, h, fmt, q, eo, es) in enumerate(ents):
            data = enc.get(i, bytes(body[db+eo: db+eo+es]))
            new[i] = (w, h, fmt, q, len(blob), len(data))
            blob += data
        keep = len(body) - db                    # 원본 데이터 구역 길이
        if len(blob) < keep: blob += bytes(keep - len(blob))   # 청크 크기까지 그대로

    nb = bytearray(body[:db])
    for i, t in enumerate(new):
        struct.pack_into('>4H2I', nb, 0x10 + i*0x10, *t)
    nb += blob
    bodies = [bytes(nb) if k == img_i else c[3] for k, c in enumerate(ch)]

    # 청크 자리는 원본 그대로. 커져서 다음 청크를 침범할 때만 그 뒤를 민다.
    places = [c[0] for c in ch]
    order = sorted(range(len(ch)), key=lambda k: places[k])
    for a, b2 in zip(order, order[1:]):
        need = places[a] + len(bodies[a])
        if places[b2] < need: places[b2] = need

    out = bytearray(d)                           # 원본을 바탕으로
    for k in range(len(ch)):
        struct.pack_into('>4I', out, 0x10 + k*16, places[k], len(bodies[k]), ch[k][2], 0)
    for k in order:
        at, b2 = places[k], bodies[k]
        if at + len(b2) > len(out): out += b'\x00' * (at + len(b2) - len(out))
        out[at:at+len(b2)] = b2
    return bytes(out)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    from build_iso import walk_iso, SRC_ISO, SECTOR

    def pics(x):
        """이미지 청크의 압축 푼 픽셀들"""
        for o, s2, i2, b in spr.chunks(x):
            c, e, db = spr.entries(b)
            if c and any(t[5] for t in e):
                return [raw_px(b, t, db) for t in e if t[5]]
        return []

    f = open(SRC_ISO, 'rb'); table = walk_iso(f)
    n = ok = skip = 0
    for p2 in sorted(table):
        if not p2.upper().endswith('.SPR'): continue
        _, lba, sz = table[p2]; f.seek(lba*SECTOR); d = f.read(sz)
        if not spr.chunks(d): continue
        try:
            nd = rebuild(d, {})
        except Exception as e:
            skip += 1; continue
        n += 1
        if nd == d: ok += 1
        else: print(f"  다름: {p2}  {len(d)} -> {len(nd)}")
    print(f"안 바꾸고 다시 쓰기 = 원본과 바이트 동일: {ok}/{n} (건너뜀 {skip})")
