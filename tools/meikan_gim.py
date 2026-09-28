# -*- coding: utf-8 -*-
"""필살기 이름 세로 배너(SLGSIDE/MEIKAN/*.GIM) 30장을 한글로 바꾼다.

  python tools/meikan_gim.py --png [이름...]   미리보기만
  python tools/meikan_gim.py                   build/patched/MEIKAN 에 저장

132x230 INDEX8 스위즐 GIM. 인물 그림 위에 세로쓰기 붓글씨.
파일 이름 = 인물_기술 (K1/K2=필살기, HG=합체기, NG=장거리, TE=?, BS=적).

프랑스어(IRI)·러시아어(MAR)·이탈리아어(ORI)·독일어(REN) 배너 20장은
일본어가 아니므로 손대지 않는다.

번역은 게임 안 퀴즈(SK1303)에서 쓴 표기를 따른다 — 앵화방신, 앵화무상,
백화제방, 귀신굉천살, 방마성진, 설화파문십궤, 로패오단, 연작·비룡의 춤.
퀴즈에 없는 것은 같은 방식(한자 음차)으로 옮겼다.

원문을 지우는 자동 검출은 세 번 실패했다 — 배너마다 색조·잉크·질감이
다르고 주사선 디더까지 깔려 있어 초상화와 글자를 기계로 못 가른다.
그래서 **원문 열 위에 배너 색조의 세로 리본을 깔고 그 위에 쓴다.**
리본이 원문을 완전히 덮으므로 잔재가 없고, 30장이 균일하게 나온다.
열 위치는 원본 배치(오른쪽 열이 위, 왼쪽 열이 아래)를 따른다.
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import place_gim as PG
from build_iso import walk_iso, SRC_ISO, SECTOR

FONT  = os.path.join(ROOT, "NanumSquareNeo-cBd.ttf")
BUILD = os.path.join(ROOT, "build", "patched", "MEIKAN")

# 오른쪽 열부터. (원문, [열 문자열...])
KO = {
 'KAN_HG': ("純情一路",             ["순정일로"],                   'dark'),
 'KAN_K1': ("三進転掌",             ["삼진전장"],                   'dark'),
 'KAN_K2': ("三十六掌",             ["삼십육장"],                   'dark'),
 'KAN_NG': ("征遠鎮",               ["정원진"],                     'dark'),
 'KAN_TE': ("鷺牌五段",             ["로패오단"],                   'dark'),
 'KAS_BS': ("紅蓮火輪双",           ["홍련화륜쌍"],                 'dark'),
 'KON_BS': ("鬼神轟天殺",           ["귀신굉천살"],                 'dark'),
 'KOR_HG': ("我愛你",               ["워아이니"],                   'dark'),
 'KOR_K1': ("雀牌ロボ",             ["작패로봇"],                   'dark'),
 'KOR_K2': ("聖獣ロボ・改",         ["성수로봇·개"],                'dark'),
 'KOR_NG': ("超絶 猛火赤龍咬翔",    ["초절", "맹화적룡교상"],       'dark'),
 'KOR_TE': ("球電ロボ",             ["구전로봇"],                   'dark'),
 'MOK_BS': ("皓矢念臨演舞",         ["호시염림연무"],               'dark'),
 'OGA_K1': ("狼虎滅却 天地一矢",    ["낭호멸각", "천지일시"],       'dark'),
 'OGA_K2': ("狼虎滅却 天狼転化",    ["낭호멸각", "천랑전화"],       'dark'),
 'OGA_TE': ("狼虎滅却 三刃成虎",    ["낭호멸각", "삼인성호"],       'dark'),
 'ONI_K2': ("破邪剣征 桜花放神",    ["파사검정", "앵화방신"],       'light'),
 'ONI_TE': ("諸力諸来 放魔星辰",    ["제력제래", "방마성진"],       'light'),
 'SAK_HG': ("二人はさくら色",       ["두 사람은", "벚꽃빛"],        'light'),
 'SAK_K1': ("破邪剣征 桜花霧翔",    ["파사검정", "앵화무상"],       'light'),
 'SAK_K2': ("破邪剣征 桜花爛漫",    ["파사검정", "앵화란만"],       'light'),
 'SAK_NG': ("破邪剣征 桜花天舞",    ["파사검정", "앵화천무"],       'light'),
 'SAK_TE': ("破邪剣征 百花斉放",    ["파사검정", "백화제방"],       'light'),
 'SUI_BS': ("雪花波紋十軌",         ["설화파문십궤"],               'light'),
 'SUM_HG': ("二人の愛は永遠に",     ["두 사람의", "사랑은 영원히"], 'light'),
 'SUM_K1': ("神崎風塵流 連雀の舞",  ["칸자키 풍진류", "연작의 춤"], 'light'),
 'SUM_K2': ("神崎風塵流 不死鳥の舞",["칸자키 풍진류", "불사조의 춤"],'light'),
 'SUM_NG': ("神崎風塵流 紫仙燕子花",["칸자키 풍진류", "자선연자화"],'light'),
 'SUM_TE': ("神崎風塵流 飛竜の舞",  ["칸자키 풍진류", "비룡의 춤"], 'light'),
 'TSU_BS': ("九印曼荼羅",           ["구인만다라"],                 'dark'),
}


def load(nm):
    f = open(SRC_ISO, 'rb'); t = walk_iso(f)
    p = [x for x in t if os.path.basename(x) == nm + '.GIM' and '/MEIKAN/' in x][0]
    _, lba, sz = t[p]; f.seek(lba*SECTOR); d = bytearray(f.read(sz)); f.close()
    return d, sz

def dominant(rgb):
    """배너 색조 — 중간톤 픽셀의 중앙값"""
    half = rgb[::4, ::4].reshape(-1, 3).astype(np.float32)
    lum = half.sum(1)
    mid = half[(lum > np.percentile(lum, 25)) & (lum < np.percentile(lum, 75))]
    return np.median(mid, axis=0) if len(mid) else np.array([128., 80., 80.])

def draw_ribbon_col(rgb, cx, ytop, ybot, text, style, tint, hw_min=0):
    """세로 리본 + 세로쓰기. (ytop, ybot) 중 None 인 쪽은 글자 수에 맞춘다."""
    h, w = rgb.shape[:2]
    chars = [c for c in text if c != ' ']
    n = len(chars)
    had_top, had_bot = ytop is not None, ybot is not None
    avail = (ybot if had_bot else h-14) - (ytop if had_top else 14)
    ch = min(52, max(18, avail//n))
    total = ch*n
    # 양쪽을 다 준 경우(한 열짜리)는 **줄이지 않는다** — 줄이면 원문 아래
    # 글자가 리본 밖으로 삐져나온다 (征遠鎮 의 鎮 이 그랬다).
    if not had_top: ytop = ybot - total - 6
    if not had_bot: ybot = ytop + total + 12
    hw = max(ch//2 + 4, hw_min)          # 원문 열을 다 덮어야 잔재가 안 남는다
    x0, x1 = max(3, cx-hw), min(w-3, cx+hw)
    y0, y1 = max(4, ytop-6), min(h-4, ybot+2)
    if style == 'dark':
        fill = tint*0.35 + np.array([255.,255.,255.])*0.65
        core_c, edge_c = np.array([15.,10.,10.]), tint*0.55
    else:
        fill = tint*0.42
        core_c, edge_c = np.array([245.,242.,238.]), tint*0.3
    # 리본 (둥근 모서리)
    S = 4
    rb = Image.new('L', ((x1-x0)*S, (y1-y0)*S), 0)
    ImageDraw.Draw(rb).rounded_rectangle([0, 0, (x1-x0)*S-1, (y1-y0)*S-1], radius=8*S, fill=255)
    ra = np.asarray(rb.resize((x1-x0, y1-y0), Image.LANCZOS)).astype(np.float32)/255
    reg = rgb[y0:y1, x0:x1].astype(np.float32)
    reg = reg*(1-ra[...,None]) + fill[None,None,:]*ra[...,None]
    rgb[y0:y1, x0:x1] = np.clip(reg, 0, 255).astype(np.uint8)
    # 글자
    f4 = ImageFont.truetype(FONT, ch*S)
    m = Image.new('L', ((x1-x0)*S, (y1-y0)*S), 0); dr = ImageDraw.Draw(m)
    ys = ytop - y0 + ( (ybot-ytop) - total )//2
    for i, c in enumerate(chars):
        b = dr.textbbox((0, 0), c, font=f4)
        dr.text(((x1-x0)*S//2 - (b[2]+b[0])//2,
                 (ys + i*ch)*S + ch*S//2 - (b[3]+b[1])//2), c, font=f4, fill=255)
    a = np.asarray(m.resize((x1-x0, y1-y0), Image.LANCZOS)).astype(np.float32)/255
    ring = np.asarray(Image.fromarray((a*255).astype('uint8'))
                      .filter(ImageFilter.MaxFilter(3))).astype(np.float32)/255
    reg = rgb[y0:y1, x0:x1].astype(np.float32)
    reg = reg*(1-ring[...,None]) + edge_c[None,None,:]*ring[...,None]
    reg = reg*(1-a[...,None]) + core_c[None,None,:]*a[...,None]
    rgb[y0:y1, x0:x1] = np.clip(reg, 0, 255).astype(np.uint8)
    return ch

# 원문 열 자리는 50장이 거의 같다 — 한 열이면 가운데, 두 열이면 오른쪽 98 /
# 왼쪽 42. 획 에너지로 재 봤지만 배너마다 몇 px 씩 흔들려 원문이 삐져나왔다.
# 고정값 + 넉넉한 반폭이 훨씬 안정적이다.
CX1, CX2R, CX2L = 66, 98, 42
HW1, HW2 = 48, 36


# ---------------------------------------------------------------- v3.6 방식
# v3.5 까지는 원문 열 위에 **리본을 통째로 깔았다.** 그 바람에 인물 그림이
# 가려지고, 원본의 **투명 주사선과 글자 테두리(= 전투 화면이 비쳐 보이는
# 연출)** 까지 불투명하게 칠해졌다. 필살기를 쓸 때마다 이 배너가 뜨므로
# "필살기 연출이 이상하다" 는 제보로 돌아왔다.
#
# 지금은 원문 열의 좁은 폭(±24px) 안에서 **획만** 골라 주변 그림으로 메우고,
# 한글은 리본 없이 글자+테두리만 얹는다. 주사선 행의 투명 픽셀과 배너 바깥
# 투명 영역은 손대지 않는다. 팔레트 매핑도 불투명 항목에만 한다.
def box_blur(a, r):
    k = 2*r+1
    p = np.pad(a, r, mode='edge').astype(np.float32)
    c = p.cumsum(0); c = np.vstack([np.zeros((1, c.shape[1])), c]); v = (c[k:] - c[:-k]) / k
    c = v.cumsum(1); c = np.hstack([np.zeros((c.shape[0], 1)), c]); return (c[:, k:] - c[:, :-k]) / k


def dil(m, n):
    return np.asarray(Image.fromarray(m.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(n))) > 0


def inpaint(rgb, hole, src, rounds=300):
    out = rgb.astype(np.float32).copy()
    known = src & ~hole
    out[~known] = 0
    w = known.astype(np.float32)
    acc = out * w[..., None]
    for _ in range(rounds):
        a2 = sum(np.roll(np.roll(acc, dy, 0), dx, 1) for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)))
        w2 = sum(np.roll(np.roll(w, dy, 0), dx, 1) for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)))
        fill = hole & (w2 > 0)
        acc[fill] = a2[fill] / w2[fill][:, None]
        w = np.where(fill, 1.0, w)
        acc = np.where(fill[..., None], acc, acc)
    return np.clip(acc, 0, 255)


def glyph_col(rgb, opaque, scan, cx, y0, y1, hw):
    """원문 한 열의 획 마스크."""
    h, w = rgb.shape[:2]
    lum = rgb.astype(np.float32) @ np.array([.299, .587, .114])
    det = np.abs(lum - box_blur(lum, 4))
    m = np.zeros((h, w), bool)
    xa, xb = max(0, cx-hw), min(w, cx+hw)
    ya, yb = max(0, y0), min(h, y1)
    reg = np.zeros((h, w), bool); reg[ya:yb, xa:xb] = True
    # 획: 세밀한 명암 차 + 주사선이 아닌 투명(글자 테두리)
    m |= reg & opaque & (det > 18)
    m |= reg & ~opaque & ~scan
    m = dil(m, 5)
    # 덩어리로 닫기: 행마다 밀도가 있는 곳만
    m = np.asarray(Image.fromarray(m.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(5))
                   .filter(ImageFilter.MinFilter(3))) > 0
    return m & reg


def draw_col(rgb, alpha_keep, cx, ytop, ybot, text, style, ch_max=34):
    h, w = rgb.shape[:2]
    chars = [c for c in text if c != ' ']
    n = len(chars)
    ch = int(min(ch_max, max(16, (ybot - ytop) // n)))
    total = ch*n
    ys = ytop + ((ybot - ytop) - total)//2
    Sc = 4
    f4 = ImageFont.truetype(FONT, ch*Sc)
    m = Image.new('L', (w*Sc, h*Sc), 0); dr = ImageDraw.Draw(m)
    for i, c in enumerate(chars):
        b = dr.textbbox((0, 0), c, font=f4)
        dr.text((cx*Sc - (b[2]+b[0])//2, (ys + i*ch)*Sc + ch*Sc//2 - (b[3]+b[1])//2), c, font=f4, fill=255)
    a = np.asarray(m.resize((w, h), Image.LANCZOS)).astype(np.float32)/255
    ring = np.asarray(Image.fromarray((a*255).astype('uint8')).filter(ImageFilter.MaxFilter(5))).astype(np.float32)/255
    if style == 'dark':
        core, edge = np.array([25., 12., 12.]), np.array([250., 246., 240.])
    else:
        core, edge = np.array([250., 246., 240.]), np.array([30., 16., 20.])
    out = rgb.astype(np.float32)
    out = out*(1-ring[..., None]) + edge*ring[..., None]
    out = out*(1-a[..., None]) + core*a[..., None]
    return np.clip(out, 0, 255).astype(np.uint8), (ring > 0.05)


def process(nm):
    ja, cols_ko, style = KO[nm]
    d, sz = load(nm)
    (po, w, h, order), palo = PG.gim_image(bytes(d))
    pitch = (w+15)//16*16; hh = (h+7)//8*8
    buf = np.frombuffer(bytes(d[po:po+pitch*hh]), np.uint8)
    img = (PG.unswz(buf, pitch, hh) if order else buf.reshape(hh, pitch)).copy()
    pal = np.frombuffer(bytes(d[palo:palo+1024]), np.uint8).reshape(256, 4)
    idx = img[:h, :w].copy()
    rgba = pal[idx]
    rgb = rgba[..., :3].astype(np.uint8).copy()
    opaque = rgba[..., 3] > 0
    # 주사선 행: 안쪽 폭의 30% 이상이 투명한 행
    inner = ~opaque[:, 12:w-12]
    scanrow = inner.mean(1) > 0.30
    scan = np.zeros_like(opaque); scan[scanrow] = ~opaque[scanrow]
    # 배너 바깥(둥근 모서리) 투명도 주사선처럼 보존
    outside = ~opaque & ~dil(opaque & ~scan, 3)
    scan |= outside

    if len(cols_ko) == 1:
        cols = [(CX1, 8, h-6, 26, cols_ko[0])]
    else:
        cols = [(CX2R, 8, h-6, 24, cols_ko[0]), (CX2L, 8, h-6, 24, cols_ko[1])]
    hole = np.zeros((h, w), bool)
    for cx, y0, y1, hw, _ in cols:
        hole |= glyph_col(rgb, opaque, scan, cx, y0, y1, hw)
    src = opaque & ~scan
    rgb2 = inpaint(rgb, hole, src).astype(np.uint8)
    rgb2[~hole] = rgb[~hole]
    newtext = np.zeros((h, w), bool)
    if len(cols_ko) == 1:
        rgb2, t = draw_col(rgb2, None, CX1, 10, h-8, cols_ko[0], style); newtext |= t
    else:
        rgb2, t = draw_col(rgb2, None, CX2R, 10, h//2 + 60, cols_ko[0], style, 30); newtext |= t
        rgb2, t = draw_col(rgb2, None, CX2L, h//2 - 60, h-8, cols_ko[1], style, 30); newtext |= t
    changed = (hole | newtext) & ~scan
    # 팔레트 매핑 (불투명 항목만)
    P = pal[:, :3].astype(np.int32); okp = pal[:, 3] > 0
    flat = rgb2[changed].astype(np.int32)
    dif = ((flat[:, None, :] - P[None, :, :])**2).sum(2); dif[:, ~okp] = 1 << 30
    idx2 = idx.copy(); idx2[changed] = dif.argmin(1).astype(np.uint8)
    img[:h, :w] = idx2
    d[po:po+pitch*hh] = (PG.swz(img) if order else img.reshape(-1)).tobytes()
    assert len(d) == sz
    return bytes(d), Image.fromarray(pal[idx], 'RGBA'), Image.fromarray(pal[idx2], 'RGBA'), hole



def run(make_png=False, only=None):
    os.makedirs(BUILD, exist_ok=True)
    prev = []
    for nm in KO:
        if only and nm not in only: continue
        d, a, b, _ = process(nm)
        print(f"  {nm}: {KO[nm][0]} -> {' / '.join(KO[nm][1])}")
        if make_png: prev.append((a, b)); continue
        open(os.path.join(BUILD, nm + '.GIM'), 'wb').write(d)
    if make_png and prev:
        cols_n = 8; rows_n = (len(prev)*2 + cols_n - 1)//cols_n
        sh = Image.new('RGBA', (cols_n*136, rows_n*234), (255, 0, 255, 255))
        for k, im in enumerate([x for p in prev for x in p]):
            sh.alpha_composite(im, ((k % cols_n)*136, (k//cols_n)*234))
        os.makedirs(os.path.join(ROOT, 'test_render'), exist_ok=True)
        q = os.path.join(ROOT, 'test_render', '_meikan_ko.png'); sh.save(q); print('  ->', q)

if __name__ == '__main__':
    sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    only = [a for a in sys.argv[1:] if not a.startswith('--')] or None
    run('--png' in sys.argv, only)
