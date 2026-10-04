# -*- coding: utf-8 -*-
"""대사를 창 너비에 맞춰 다시 접는다.

  python tools/fit_lines.py --dry    검사만
  python tools/fit_lines.py          text/*.tsv 를 고친다

**창마다 한 줄 글자 수가 다르다.** 이걸 몰라서 두 번 사고를 냈다.

    사쿠라1 대사창   18자 x 3줄
    사쿠라1 전투창   17자 x 3줄
    사쿠라2          14자 x 3줄

대사창을 21자로 알고 있었다. 실기 사진에서

    오오가미　이치로，　분골쇄신의　각오로   (19자)

가 18자에서 접히고, 그 바람에 줄이 하나 밀려 마지막 줄이 화면 밖으로
나갔다. 얼굴 그림이 붙은 대사창은 글자 시작 위치가 오른쪽으로 밀려서
21자가 아니라 18자만 들어간다.

**가장 믿을 만한 근거는 원문이다.** 원문 한 줄의 최대 길이를 세어 보면

    sakura1_adv  최대 18자 (18자 2줄, 17자 3줄, 16자 13줄, 나머지는 15자 이하)
    sakura1_slg  최대 17자
    sakura2_adv  최대 15자

일본어 대본 자체가 그 폭에 맞춰 쓰여 있다. 창 너비를 재는 것보다 이게 낫다.

**줄 수는 원문을 넘으면 안 된다.** 사쿠라1 대사창은 원문이 4줄인 것도 있어서
「3줄 이하」만 보면 부족하다. 원문보다 줄이 늘면 화면 밖으로 밀린다.
이 규칙을 안 보고 18자 재조정을 하다가 140행이 원문보다 길어졌다.

띄어쓰기에서 다시 접기만 한다. 그래도 안 들어가면 손으로 줄여야 하므로
목록을 찍어 준다.
"""
import os, re, sys, io

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsvio

TEXT = os.path.join(os.path.dirname(HERE), "text")
TOK  = re.compile(r'<[^>]*>')
NL   = chr(92) + 'n'
MAXL = 3

# 파일 -> 한 줄 최대 글자 수
LIMITS = {
    'sakura1_adv.tsv': 18,
    'sakura1_slg.tsv': 17,
    'sakura2_adv.tsv': 14,
    'sakura2_evt.tsv': 14,
    'sakura2_slg.tsv': 14,
}

def width(s): return len(TOK.sub('', s))

def wrap(text, lim):
    """전각 공백에서 접는다. 토큰은 폭 0 이라 그대로 따라간다."""
    words = text.split('　')
    out, cur = [], ''
    for w in words:
        cand = w if not cur else cur + '　' + w
        if width(cand) <= lim or not cur:
            cur = cand
        else:
            out.append(cur); cur = w
    if cur: out.append(cur)
    return out

TOKEN = re.compile(r'<[0-9A-Fa-f]{4}>')

CHOICE_LIM = 15
def is_choice(fn, r):
    """사쿠라1 본편 선택지 — 메시지 id 가 0x4Exx.

    선택지는 **한 줄이 선택지 하나**다. 그래서
      - 줄 수는 원문과 **같아야** 하고 (합치거나 나누면 선택지가 섞인다),
      - 한 줄은 **15자** 까지다. 선택지 창은 대사창보다 좁다
        (원문 최대 15자. 18자를 넣었더니 창 양쪽으로 한 칸씩 삐져나왔다).
    자동 줄바꿈(run)이 선택지를 한 문장으로 합쳐 다시 접는 바람에
    「옷을 골라 준다．　옷을 갈아입은 / 아이리스를 상상한다．…」 처럼
    선택지가 뒤섞인 적이 있다. 그래서 run 은 선택지를 건드리지 않는다.
    """
    if fn != 'sakura1_adv.tsv': return False
    try: return 0x4E <= int(r.get('id') or '0', 16) >> 8 <= 0x4F
    except ValueError: return False

def glyphs(s):
    return len(TOKEN.sub('', s).replace(NL, ''))

def is_auto(fn, r):
    """사쿠라2 자동 넘김(<FFFA>) 대사.

    음성·연출 시간에 맞춰 글자를 한 자씩 찍는데, 찍을 수 있는 글자 수에 한도가
    있다. 원문보다 길면 마지막 글자를 못 찍고 <FFFA> 에 닿지 못해 **멈춘다**.
    (13장 사쿠라 편지: 원문 30자 / 한글 36자 → 35자에서 멈춤.
     10장 「무사시여……」: 원문 25자 / 한글 26자.)
    그래서 이 대사는 **글자 수(띄어쓰기 포함, 줄바꿈·제어코드 제외)가 원문 이하**.
    """
    return fn.startswith('sakura2') and '<FFFA>' in (r.get('ja') or '')

def check():
    """원문 줄 수·글자 수·제어코드 자리를 어긴 행이 있는지 본다.

    **제어코드가 맨 앞에 있으면 번역문에서도 맨 앞이어야 한다.**
    `<FFFC><000E>武蔵よ……` 를 `무사시여……<FFFC><000E>` 로 옮겨 놓은 행이
    하나 있었는데, 그 대사에서 사쿠라2 가 멈췄다 (이슈 #11).
    """
    bad = 0
    for fn, lim in LIMITS.items():
        p = os.path.join(TEXT, fn)
        if not os.path.exists(p): continue
        cols, rows = tsvio.read(p)
        over = long = tok = 0
        for r in rows:
            ja = r.get('ja') or ''; ko = r.get('ko') or ''
            if not ja or not ko: continue
            if is_choice(fn, r):
                if ko.count(NL) != ja.count(NL): over += 1
                if any(width(l) > CHOICE_LIM for l in ko.split(NL)): long += 1
            else:
                if ko.count(NL) > ja.count(NL): over += 1
                if any(width(l) > lim for l in ko.split(NL)): long += 1
            if is_auto(fn, r) and glyphs(ko) > glyphs(ja): long += 1
            if TOKEN.findall(ja) != TOKEN.findall(ko): tok += 1
            elif bool(TOKEN.match(ja)) != bool(TOKEN.match(ko)): tok += 1
        print(f"  {fn:<18} {lim}자  원문보다 줄 많음 {over:>4}   글자 초과 {long:>4}"
              f"   제어코드 어긋남 {tok:>4}")
        bad += over + long + tok
    return bad

def run(dry=False):
    for fn, lim in LIMITS.items():
        p = os.path.join(TEXT, fn)
        if not os.path.exists(p): continue
        cols, rows = tsvio.read(p)
        fixed, stuck = [], []
        for r in rows:
            ko = r.get('ko') or ''
            if not ko or is_choice(fn, r): continue
            ls = ko.split(NL)
            if all(width(l) <= lim for l in ls) and len(ls) <= MAXL: continue
            merged = '　'.join(l.strip('　') for l in ls if l)
            new = wrap(merged, lim)
            if len(new) <= MAXL and all(width(l) <= lim for l in new):
                r['ko'] = NL.join(new); fixed.append(r['key'])
            else:
                stuck.append((r['key'], len(new), max(width(l) for l in new), merged))
        print(f"  {fn:<18} {lim}자  다시 접어 해결 {len(fixed)}행,  못 맞춘 것 {len(stuck)}행")
        for k, n, w, s in stuck[:12]:
            print(f"      {k}  {n}줄 최장{w}자  {s[:46]}")
        if not dry and fixed:
            tsvio.write(p, cols, rows)

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if '--check' in sys.argv:
        sys.exit(1 if check() else 0)
    run('--dry' in sys.argv)
