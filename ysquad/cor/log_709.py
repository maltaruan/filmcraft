"""S-Log da Sony -> Rec.709: uma LUT de entrada por clipe, com a exposição corrigida em luz de cena.

Dois modos. `neutro` (padrão) é o tratamento do Ruan medido: branco neutralizado, o calor, a curva de
tom e a saturação que ele usa à mão no Resolve, sem visual de LUT (`--visual naruto`, o padrão, ou
`discord`). `sony` passa pela LUT oficial da Sony.

Uso:
    python3 -I log_709.py SAIDA.cube --curva slog3|slog2 --gama sgamut3|sgamut3cine|sgamut
        [--exposicao -2.5] [--ganhos 1,1,1] [--lut LUT_DA_SONY.cube] [--n 65]
    python3 -I log_709.py --detectar VIDEO.MP4      (lê curva e gama do XML que a Sony grava no MP4)
    python3 -I log_709.py SAIDA.cube --auto VIDEO.MP4 [--trecho CORTE.MP4] [--visual naruto|discord]
        (curva e gama do XML, exposição medida na pele: rosto pelo Vision, alvo a pele do visual)

O caminho, para cada cor da grade (o sinal do arquivo, 0 a 1):
  1. decodifica a curva da Sony (fórmulas publicadas) pra luz de cena, na gama da câmera;
  2. corrige a exposição (pontos de luz) e o branco (ganhos por canal) ali, em luz de cena, antes de
     qualquer compressão de realce: é onde S-Log exposto "à direita" precisa ser trazido de volta;
  3. converte a gama pra que a LUT oficial da Sony espera (S-Log3: S-Gamut3.Cine) e recodifica;
  4. aplica a LUT oficial da Sony (LC-709 por padrão), que é a transformação pra tela do fabricante.

A saída vai no Lumetri como Input LUT (`lumetri.setInputLut` com `path`), que roda na placa de vídeo.
Fontes: S-Log3 e S-Gamut3/.Cine, "Technical Summary for S-Gamut3.Cine/S-Log3 and S-Gamut3/S-Log3"
(Sony); S-Log2, Sony "S-Log2 Technical Paper", na forma da biblioteca colour-science.
"""
import argparse, json, math, os, re, statistics, subprocess, sys, tempfile

ROSTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rosto")

RESOLVE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
LUTS_SONY = {
    "slog3": os.path.join(RESOLVE, "Sony", "SLog3SGamut3.CineToLC-709.cube"),
    "slog2": os.path.join(RESOLVE, "Meus LUTS", "LUTS Log", "From_SLog2SGumut_To_LC-709_.cube"),
}
# os quatro sabores oficiais de cada perfil (a Sony publica os mesmos quatro)
SABORES = {
    "slog3": {k: os.path.join(RESOLVE, "Sony", f"SLog3SGamut3.CineTo{k}.cube") for k in ("LC-709", "LC-709TypeA", "Cine+709", "SLog2-709")},
    "slog2": {k: os.path.join(RESOLVE, "Meus LUTS", "LUTS Log", f"From_SLog2SGumut_To_{k}{'' if k == 'Cine+709' else '_'}.cube")
              for k in ("LC-709", "LC-709TypeA", "Cine+709", "SLog2-709")},
}
# a gama que cada LUT oficial espera na entrada
GAMA_DA_LUT = {"slog3": "sgamut3cine", "slog2": "sgamut"}


# Os tratamentos à mão do Ruan no Resolve, medidos. Em cada um: a curva de tom (log2 da luminância de
# cena Rec.709 -> valor de tela 0-255, gama 2.4; a exposição é resolvida depois, pela pele, então só
# a forma importa), a saturação, o calor (ganhos r,g,b em luz de cena depois do branco neutralizado,
# luminância mantida) e a luma da pele (Vision, janela central do rosto, mediana de 9 quadros).
VISUAIS = {
    # O padrão dele (17/10/2026): `naruto 2.mov`, bruto fora do disco, luz igual à dos brutos C0203-5.
    # Curva casando os tons dos três brutos com os do naruto, ancorada na pele (abaixo dela com
    # abaixo, acima com acima; o eixo é log2 da luminância sobre a da pele). Calor e saturação
    # ajustados pela cor da pele dele (162,115,82; os três brutos ficam a até 3 níveis); conferido
    # no fundo, que não entrou no ajuste: R/G 1,24-1,28 e B/G 0,78-0,81 contra 1,34 e 0,82 no naruto.
    "naruto": {
        "curva": [(-7.572, 2.7), (-5.062, 18.0), (-4.189, 27.9), (-3.559, 36.7), (-3.142, 44.2), (-2.801, 51.2),
                  (-2.273, 58.9), (-1.635, 67.9), (-0.838, 86.7), (0.0, 122.6), (0.197, 128.2), (0.435, 134.2),
                  (0.744, 141.1), (1.078, 150.8), (2.090, 184.1)],
        "saturacao": 0.95, "calor": (1.08, 1.0, 0.82), "pele": 122.6,
    },
    # 16/10/2026: 5 quadros do `discord.mov` alinhados ao bruto C0204 (S-Log2, correlação 0,996),
    # erro de 3,8 níveis. Acima de +2,08 quase não havia pixel: o ombro continua a inclinação medida.
    # Nas superfícies claras quase neutras ele deixava azul/vermelho em 0,986: branco neutro, sem calor.
    "discord": {
        "curva": [(-5.308, 0.0), (-4.385, 10.7), (-3.462, 23.0), (-2.538, 37.8), (-1.615, 54.0), (-0.692, 72.2),
                  (0.231, 95.5), (1.154, 122.3), (2.077, 151.2)],
        "saturacao": 1.11, "calor": (1.0, 1.0, 1.0), "pele": 99.7,
    },
}
VISUAL = "naruto"
# A pele do padrão vale também pro modo `sony`. O sony4k_60s dava 158, mas a origem não está confirmada.
PELE_ALVO = VISUAIS[VISUAL]["pele"]


def tom_ruan(lg, visual=VISUAL):
    """Valor de tela (0-1, gama 2.4) para log2 da luminância de cena; acima do último ponto, um ombro
    que segue a inclinação medida até o branco."""
    xs = VISUAIS[visual]["curva"]
    if lg <= xs[0][0]:
        return 0.0
    if lg >= xs[-1][0]:
        x1, y1 = xs[-1]
        inclin = (y1 - xs[-2][1]) / (x1 - xs[-2][0])
        k = inclin / (255.0 - y1)
        return (y1 + (255.0 - y1) * (1.0 - math.exp(-(lg - x1) * k))) / 255.0
    for (x0, y0), (x1, y1) in zip(xs, xs[1:]):
        if lg <= x1:
            return (y0 + (y1 - y0) * (lg - x0) / (x1 - x0)) / 255.0


# ---------- curvas (x = código / 1023, linear = refletância de cena, cinza 18 % = 0,18)
def slog3_dec(x):
    cv = x * 1023.0
    if cv >= 171.2102946929:
        return 10.0 ** ((cv - 420.0) / 261.5) * (0.18 + 0.01) - 0.01
    return (cv - 95.0) * 0.01125 / (171.2102946929 - 95.0)


def slog3_enc(lin):
    if lin >= 0.01125:
        cv = 420.0 + math.log10((lin + 0.01) / (0.18 + 0.01)) * 261.5
    else:
        cv = lin * (171.2102946929 - 95.0) / 0.01125 + 95.0
    return cv / 1023.0


def _slog1_enc(x):
    # S-Log1 em "IRE" (0 = código 64, 1 = código 940), refletância / 0,9
    x = x / 0.9
    return 0.432699 * math.log10(x + 0.037584) + 0.616596 + 0.03 if x >= 0 else x * 5.0 + 0.030001222851889303


def _slog1_dec(y):
    x = 10.0 ** ((y - 0.616596 - 0.03) / 0.432699) - 0.037584 if y >= 0.030001222851889303 else (y - 0.030001222851889303) / 5.0
    return x * 0.9


def slog2_enc(lin):
    y = _slog1_enc(lin * 155.0 / 219.0)
    return (y * 876.0 + 64.0) / 1023.0


def slog2_dec(x):
    y = (x * 1023.0 - 64.0) / 876.0
    return _slog1_dec(y) * 219.0 / 155.0


CURVAS = {"slog3": (slog3_dec, slog3_enc), "slog2": (slog2_dec, slog2_enc)}

# ---------- gamas (primárias xy, branco D65)
PRIMARIAS = {
    "sgamut": ((0.730, 0.280), (0.140, 0.855), (0.100, -0.050)),
    "sgamut3": ((0.730, 0.280), (0.140, 0.855), (0.100, -0.050)),
    "sgamut3cine": ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087)),
    "rec709": ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06)),
}
D65 = (0.3127, 0.3290)


def _inv(m):
    a, b, c = m
    det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    return [[(b[1] * c[2] - b[2] * c[1]) / det, (a[2] * c[1] - a[1] * c[2]) / det, (a[1] * b[2] - a[2] * b[1]) / det],
            [(b[2] * c[0] - b[0] * c[2]) / det, (a[0] * c[2] - a[2] * c[0]) / det, (a[2] * b[0] - a[0] * b[2]) / det],
            [(b[0] * c[1] - b[1] * c[0]) / det, (a[1] * c[0] - a[0] * c[1]) / det, (a[0] * b[1] - a[1] * b[0]) / det]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rgb_para_xyz(nome):
    xyz = lambda xy: (xy[0] / xy[1], 1.0, (1 - xy[0] - xy[1]) / xy[1])
    p = [xyz(c) for c in PRIMARIAS[nome]]
    m = [[p[j][i] for j in range(3)] for i in range(3)]
    s = [sum(_inv(m)[i][k] * xyz(D65)[k] for k in range(3)) for i in range(3)]
    return [[m[i][j] * s[j] for j in range(3)] for i in range(3)]


def matriz(de, para):
    return _mul(_inv(rgb_para_xyz(para)), rgb_para_xyz(de))


# ---------- .cube
def ler_cube(p):
    n, v = None, []
    for l in open(p, encoding="latin-1"):
        t = l.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == "LUT_3D_SIZE":
            n = int(t[1])
        elif re.match(r"^-?[0-9.]", t[0]) and len(t) >= 3:
            v.append((float(t[0]), float(t[1]), float(t[2])))
    assert n and len(v) == n ** 3, (p, n, len(v))
    return n, v


def amostrar(n, v, c):
    m = n - 1
    e = [min(max(x, 0.0), 1.0) * m for x in c]
    i0 = [min(int(x), m) for x in e]
    i1 = [min(i + 1, m) for i in i0]
    t = [e[k] - i0[k] for k in range(3)]
    at = lambda r, g, b: v[r + g * n + b * n * n]
    lerp = lambda a, b, k: tuple(a[q] + (b[q] - a[q]) * k for q in range(3))
    c00 = lerp(at(i0[0], i0[1], i0[2]), at(i1[0], i0[1], i0[2]), t[0])
    c10 = lerp(at(i0[0], i1[1], i0[2]), at(i1[0], i1[1], i0[2]), t[0])
    c01 = lerp(at(i0[0], i0[1], i1[2]), at(i1[0], i0[1], i1[2]), t[0])
    c11 = lerp(at(i0[0], i1[1], i1[2]), at(i1[0], i1[1], i1[2]), t[0])
    return lerp(lerp(c00, c10, t[1]), lerp(c01, c11, t[1]), t[2])


def conversao(curva, gama, exposicao=0.0, ganhos=(1.0, 1.0, 1.0), lut=None):
    """A função sinal -> Rec.709 de um pixel."""
    dec, _ = CURVAS[curva]
    _, enc = CURVAS[curva]
    alvo = GAMA_DA_LUT[curva]
    mt = None if PRIMARIAS[gama] == PRIMARIAS[alvo] else matriz(gama, alvo)
    n, v = ler_cube(lut or LUTS_SONY[curva])
    k = 2.0 ** exposicao
    def f(s):
        lin = [dec(s[q]) * k * ganhos[q] for q in range(3)]
        if mt:
            lin = [sum(mt[i][j] * lin[j] for j in range(3)) for i in range(3)]
        return amostrar(n, v, [enc(x) for x in lin])
    return f


def conversao_neutra(curva, gama, exposicao=0.0, ganhos=(1.0, 1.0, 1.0), visual=VISUAL):
    """Sinal -> Rec.709 sem LUT: luz de cena, exposição, matriz pra Rec.709, branco (ganhos em
    Rec.709 linear), o calor do visual, a curva de tom do Ruan na luminância (a cor segue como razão)
    e a saturação dele."""
    dec, _ = CURVAS[curva]
    mt = matriz(gama, "rec709")
    k = 2.0 ** exposicao
    vis = VISUAIS[visual]
    c = vis["calor"]
    norma = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    g = [ganhos[i] * c[i] / norma for i in range(3)]
    sat = vis["saturacao"]
    def f(s):
        lin = [dec(s[q]) * k for q in range(3)]
        v = [max(sum(mt[i][j] * lin[j] for j in range(3)) * g[i], 0.0) for i in range(3)]
        lum = 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        if lum <= 1e-7:
            return (0.0, 0.0, 0.0)
        tela = tom_ruan(math.log2(lum), visual) ** 2.4
        out = [x * tela / lum for x in v]
        l2 = 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
        out = [l2 + (x - l2) * sat for x in out]
        return tuple(min(max(x, 0.0), 1.0) ** (1 / 2.4) for x in out)
    return f


def escrever_cube(caminho, f, n, titulo):
    m = n - 1
    with open(caminho, "w") as o:
        o.write(f'TITLE "{titulo}"\nLUT_3D_SIZE {n}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    c = f((r / m, g / m, b / m))
                    o.write(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}\n")


def detectar(video):
    """Curva e gama do XML que a Sony grava no fim do MP4 (`CaptureGammaEquation`)."""
    with open(video, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - 4_000_000))
        t = fh.read().decode("latin-1")
    g = re.search(r'CaptureGammaEquation" value="([^"]+)"', t)
    p = re.search(r'CaptureColorPrimaries" value="([^"]+)"', t)
    curva = {"s-log3": "slog3", "s-log3-cine": "slog3", "s-log2": "slog2"}.get(g.group(1) if g else "", None)
    gama = {"s-gamut": "sgamut", "s-gamut3": "sgamut3", "s-gamut3-cine": "sgamut3cine"}.get(p.group(1) if p else "", None)
    return {"curva": curva, "gama": gama, "gamma_sony": g.group(1) if g else None, "primarias_sony": p.group(1) if p else None}


def amostras_de_pele(video, n=5, largura=960, intervalos=None):
    """Mediana do sinal (0 a 1) da pele em `n` quadros: uma janela no meio do maior rosto
    (entre os olhos e o bigode), achado pelo Vision (`../rosto/rosto.swift`)."""
    ffmpeg = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
    dur = float(subprocess.run(["/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe", "-v", "error",
                                "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip() or 0)
    exe = os.path.join(ROSTO, "rosto")
    if not os.path.exists(exe):
        subprocess.run(["swiftc", "-O", os.path.join(ROSTO, "rosto.swift"), "-o", exe], check=True)
    faixas = intervalos or [(0.0, dur)]
    total = sum(b - a for a, b in faixas)

    def instante(k):
        # o k-ésimo de n pontos espalhados pelo tempo somado dos intervalos
        alvo = total * (k + 0.5) / n
        for a, b in faixas:
            if alvo <= b - a:
                return a + alvo
            alvo -= b - a
        return faixas[-1][1]

    pele, neutros = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = instante(i)
            png, raw = os.path.join(tmp, f"{i}.png"), os.path.join(tmp, f"{i}.rgb")
            vf = f"scale={largura}:-2"
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", vf, png], check=True)
            dims = subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", vf,
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", raw], capture_output=True, text=True)
            out = subprocess.run([exe, png], capture_output=True, text=True).stdout.split("\t")
            b = open(raw, "rb").read()
            W = largura
            H = len(b) // (3 * W)
            rosto = None if len(out) < 4 else (float(out[1]), float(out[2]), float(out[3]))
            neutros.append((b, W, H, rosto))
            if not rosto:
                continue
            cx, cy, fh = rosto
            x0, x1 = int((cx - 0.18 * fh * H / W) * W), int((cx + 0.18 * fh * H / W) * W)
            y0, y1 = int((cy - 0.12 * fh) * H), int((cy + 0.08 * fh) * H)
            px = [tuple(b[(y * W + x) * 3 + q] for q in range(3)) for y in range(max(y0, 0), min(y1, H)) for x in range(max(x0, 0), min(x1, W))]
            if px:
                pele.append(tuple(statistics.median(p[q] for p in px) / 255.0 for q in range(3)))
    if not pele:
        return None
    return tuple(statistics.median(p[q] for p in pele) for q in range(3)), len(pele), neutros


def branco_auto(quadros, curva, gama):
    """Ganhos (Rec.709 linear) que deixam neutras as áreas claras e de pouca cor fora do rosto
    (paredes, estante): mediana por canal dessas áreas em cada quadro, mediana entre quadros."""
    dec, _ = CURVAS[curva]
    mt = matriz(gama, "rec709")
    tab = [dec(i / 255.0) for i in range(256)]
    estimativas = []
    for b, W, H, rosto in quadros:
        px = []
        for y in range(0, H, 4):
            for x in range(0, W, 4):
                if rosto:
                    cx, cy, fh = rosto
                    if abs(x / W - cx) < 0.45 * fh * H / W and -0.35 * fh < y / H - cy < 1.2 * fh:
                        continue  # rosto e pescoço
                k = (y * W + x) * 3
                s = b[k:k + 3]
                if max(s) > 247:
                    continue
                lin = [tab[s[0]], tab[s[1]], tab[s[2]]]
                v = [sum(mt[i][j] * lin[j] for j in range(3)) for i in range(3)]
                if min(v) <= 0:
                    continue
                px.append(v)
        if len(px) < 200:
            continue
        lums = sorted(0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2] for v in px)
        lo, hi = lums[len(lums) // 2], lums[int(len(lums) * 0.97)]
        cand = [v for v in px if lo <= 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2] <= hi and (max(v) - min(v)) / max(v) < 0.35]
        if len(cand) < 100:
            continue
        m = [statistics.median(v[q] for v in cand) for q in range(3)]
        estimativas.append((m[1] / m[0], m[1] / m[2]))
    if not estimativas:
        return (1.0, 1.0, 1.0)
    return (round(statistics.median(e[0] for e in estimativas), 4), 1.0, round(statistics.median(e[1] for e in estimativas), 4))


def exposicao_pela_pele(curva, gama, pele, lut=None, alvo=None, modo="sony", ganhos=(1, 1, 1), visual=VISUAL):
    """Pontos de luz (em luz de cena) que levam a pele medida ao alvo depois da conversão (padrão: a
    pele do visual no modo neutro, PELE_ALVO no sony)."""
    luma = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    if alvo is None:
        alvo = VISUAIS[visual]["pele"] if modo == "neutro" else PELE_ALVO
    conv = (lambda ev: conversao_neutra(curva, gama, ev, ganhos, visual)) if modo == "neutro" else (lambda ev: conversao(curva, gama, ev, ganhos, lut))
    lo, hi = -8.0, 4.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if luma(conv(mid)(pele)) * 255 > alvo:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 2)


def amostras_de_cor(video, trecho, pasta):
    """Um quadro e 4 s de vídeo por sabor oficial da Sony, cada um com a exposição resolvida pela
    pele, e uma folha com os quadros lado a lado (ordem de SABORES)."""
    ffmpeg = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
    d = detectar(video)
    if not d["curva"]:
        sys.exit(f"sem log no XML: {d}")
    r = amostras_de_pele(trecho)
    if not r:
        sys.exit("nenhum rosto no trecho")
    os.makedirs(pasta, exist_ok=True)
    quadros, saida = [], {}
    for sabor, lut in SABORES[d["curva"]].items():
        ev = exposicao_pela_pele(d["curva"], d["gama"], r[0], lut)
        cube = os.path.join(pasta, f"{sabor}.cube")
        escrever_cube(cube, conversao(d["curva"], d["gama"], ev, (1, 1, 1), lut), 33, f"{sabor} {ev:+.2f}")
        # a Sony grava YUV BT.709 em faixa cheia sem declarar a matriz: sem isto o ffmpeg usa BT.601
        pre = "scale=in_color_matrix=bt709:in_range=full:out_range=full,format=gbrp,"
        esc = cube.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        png, mp4 = os.path.join(pasta, f"{sabor}.png"), os.path.join(pasta, f"{sabor}.mp4")
        subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", "3", "-i", trecho, "-frames:v", "1",
                        "-vf", f"{pre}lut3d=file='{esc}',scale=-2:720", png], check=True)
        subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", trecho, "-t", "4", "-an", "-vf", f"{pre}lut3d=file='{esc}',scale=-2:1080",
                        "-c:v", "h264_videotoolbox", "-b:v", "12M", mp4], check=True)
        quadros.append(png)
        saida[sabor] = ev
    folha = os.path.join(pasta, "folha.png")
    subprocess.run([ffmpeg, "-loglevel", "error", "-y", *sum((["-i", q] for q in quadros), []),
                    "-filter_complex", f"hstack=inputs={len(quadros)}", folha], check=True)
    return {"folha": folha, "curva": d["curva"], "gama": d["gama"], "exposicao_por_sabor": saida}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("saida", nargs="?")
    a.add_argument("--detectar", metavar="VIDEO")
    a.add_argument("--auto", metavar="VIDEO", help="curva/gama do XML e exposição medida na pele")
    a.add_argument("--trecho", metavar="VIDEO", help="--auto: medir a pele neste vídeo (padrão: o próprio VIDEO)")
    a.add_argument("--intervalos", help="com --auto: medir a pele só nestes trechos do vídeo (a-b,c-d, segundos)")
    a.add_argument("--amostras", metavar="PASTA", help="com --auto: os quatro sabores da Sony lado a lado, pra escolher")
    a.add_argument("--sabor", help="modo sony: LC-709 (padrão), LC-709TypeA, Cine+709 ou SLog2-709")
    a.add_argument("--modo", choices=("neutro", "sony"), default="neutro")
    a.add_argument("--visual", choices=VISUAIS, default=VISUAL, help="modo neutro: qual tratamento do Ruan (naruto, o padrão; discord)")
    a.add_argument("--curva", choices=CURVAS)
    a.add_argument("--gama", choices=PRIMARIAS)
    a.add_argument("--exposicao", type=float, default=0.0, help="pontos de luz, em luz de cena")
    a.add_argument("--ganhos", default="1,1,1", help="r,g,b em luz de cena (branco)")
    a.add_argument("--lut", help="LUT oficial da Sony (padrão: LC-709 do perfil)")
    a.add_argument("--n", type=int, default=65)
    o = a.parse_args()
    if o.detectar:
        print(json.dumps(detectar(o.detectar)))
        return
    if o.auto and o.amostras:
        print(json.dumps(amostras_de_cor(o.auto, o.trecho or o.auto, o.amostras)))
        return
    medida = None
    if o.auto:
        d = detectar(o.auto)
        if not d["curva"] or not d["gama"]:
            sys.exit(f"sem curva/gama de log no XML da Sony: {d}")
        o.curva, o.gama = d["curva"], d["gama"]
        if o.sabor:
            o.lut = SABORES[o.curva][o.sabor]
        iv = [tuple(map(float, x.split("-"))) for x in o.intervalos.split(",")] if o.intervalos else None
        r = amostras_de_pele(o.trecho or o.auto, intervalos=iv)
        if r:
            if o.modo == "neutro":
                o.ganhos = ",".join(map(str, branco_auto(r[2], o.curva, o.gama)))
            g = tuple(float(x) for x in o.ganhos.split(","))
            medida = {"pele_sinal": [round(v, 4) for v in r[0]], "quadros_com_rosto": r[1], "ganhos_branco": g}
            o.exposicao = exposicao_pela_pele(o.curva, o.gama, r[0], o.lut, modo=o.modo, ganhos=g, visual=o.visual)
    if not (o.saida and o.curva and o.gama):
        a.error("SAIDA, --curva e --gama")
    ganhos = tuple(float(x) for x in o.ganhos.split(","))
    f = conversao_neutra(o.curva, o.gama, o.exposicao, ganhos, o.visual) if o.modo == "neutro" else conversao(o.curva, o.gama, o.exposicao, ganhos, o.lut)
    nome = f"neutro {o.visual}" if o.modo == "neutro" else o.modo
    escrever_cube(o.saida, f, o.n, f"{nome} {o.curva}/{o.gama} exp {o.exposicao:+.2f}")
    print(json.dumps({"saida": o.saida, "modo": o.modo, "visual": o.visual if o.modo == "neutro" else None, "curva": o.curva, "gama": o.gama, "exposicao": o.exposicao, "medida": medida}))


if __name__ == "__main__":
    main()
