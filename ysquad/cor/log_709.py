"""S-Log da Sony -> Rec.709: uma LUT de entrada por clipe, com a exposição corrigida em luz de cena.

Uso:
    python3 -I log_709.py SAIDA.cube --curva slog3|slog2 --gama sgamut3|sgamut3cine|sgamut
        [--exposicao -2.5] [--ganhos 1,1,1] [--lut LUT_DA_SONY.cube] [--n 65]
    python3 -I log_709.py --detectar VIDEO.MP4      (lê curva e gama do XML que a Sony grava no MP4)
    python3 -I log_709.py SAIDA.cube --auto VIDEO.MP4 [--trecho CORTE.MP4]
        (curva e gama do XML, exposição medida na pele: rosto pelo Vision, alvo PELE_ALVO)

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

# Luma (8 bits, Rec.709) da pele nos vídeos do Ruan já tratados: medido em 16/10/2026 no
# sony4k_60s (testa 187, bochechas 167 e 174, nariz 184). A exposição automática mira o meio.
PELE_ALVO = 177.0
ROSTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rosto")

RESOLVE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
LUTS_SONY = {
    "slog3": os.path.join(RESOLVE, "Sony", "SLog3SGamut3.CineToLC-709.cube"),
    "slog2": os.path.join(RESOLVE, "Meus LUTS", "LUTS Log", "From_SLog2SGumut_To_LC-709_.cube"),
}
# a gama que cada LUT oficial espera na entrada
GAMA_DA_LUT = {"slog3": "sgamut3cine", "slog2": "sgamut"}


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


def amostras_de_pele(video, n=5, largura=960):
    """Mediana do sinal (0 a 1) da pele em `n` quadros: uma janela no meio do maior rosto
    (entre os olhos e o bigode), achado pelo Vision (`../rosto/rosto.swift`)."""
    ffmpeg = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
    dur = float(subprocess.run(["/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe", "-v", "error",
                                "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip() or 0)
    exe = os.path.join(ROSTO, "rosto")
    if not os.path.exists(exe):
        subprocess.run(["swiftc", "-O", os.path.join(ROSTO, "rosto.swift"), "-o", exe], check=True)
    pele = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = dur * (i + 0.5) / n
            png, raw = os.path.join(tmp, f"{i}.png"), os.path.join(tmp, f"{i}.rgb")
            vf = f"scale={largura}:-2"
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", vf, png], check=True)
            dims = subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", vf,
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", raw], capture_output=True, text=True)
            out = subprocess.run([exe, png], capture_output=True, text=True).stdout.split("\t")
            if len(out) < 4:
                continue
            cx, cy, fh = float(out[1]), float(out[2]), float(out[3])
            b = open(raw, "rb").read()
            W = largura
            H = len(b) // (3 * W)
            x0, x1 = int((cx - 0.18 * fh * H / W) * W), int((cx + 0.18 * fh * H / W) * W)
            y0, y1 = int((cy - 0.12 * fh) * H), int((cy + 0.08 * fh) * H)
            px = [tuple(b[(y * W + x) * 3 + q] for q in range(3)) for y in range(max(y0, 0), min(y1, H)) for x in range(max(x0, 0), min(x1, W))]
            if px:
                pele.append(tuple(statistics.median(p[q] for p in px) / 255.0 for q in range(3)))
    if not pele:
        return None
    return tuple(statistics.median(p[q] for p in pele) for q in range(3)), len(pele)


def exposicao_pela_pele(curva, gama, pele, lut=None, alvo=PELE_ALVO):
    """Pontos de luz (em luz de cena) que levam a pele medida ao alvo depois da conversão."""
    luma = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    lo, hi = -8.0, 4.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if luma(conversao(curva, gama, mid, (1, 1, 1), lut)(pele)) * 255 > alvo:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 2)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("saida", nargs="?")
    a.add_argument("--detectar", metavar="VIDEO")
    a.add_argument("--auto", metavar="VIDEO", help="curva/gama do XML e exposição medida na pele")
    a.add_argument("--trecho", metavar="VIDEO", help="--auto: medir a pele neste vídeo (padrão: o próprio VIDEO)")
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
    medida = None
    if o.auto:
        d = detectar(o.auto)
        if not d["curva"] or not d["gama"]:
            sys.exit(f"sem curva/gama de log no XML da Sony: {d}")
        o.curva, o.gama = d["curva"], d["gama"]
        r = amostras_de_pele(o.trecho or o.auto)
        if r:
            medida = {"pele_sinal": [round(v, 4) for v in r[0]], "quadros_com_rosto": r[1]}
            o.exposicao = exposicao_pela_pele(o.curva, o.gama, r[0], o.lut)
    if not (o.saida and o.curva and o.gama):
        a.error("SAIDA, --curva e --gama")
    ganhos = tuple(float(x) for x in o.ganhos.split(","))
    f = conversao(o.curva, o.gama, o.exposicao, ganhos, o.lut)
    escrever_cube(o.saida, f, o.n, f"{o.curva}/{o.gama} exp {o.exposicao:+.2f}")
    print(json.dumps({"saida": o.saida, "curva": o.curva, "gama": o.gama, "exposicao": o.exposicao, "medida": medida}))


if __name__ == "__main__":
    main()
