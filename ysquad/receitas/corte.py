"""O corte do `cortar-fala` no tempo do corte: frases (os <title> do FCPXML), trechos e o tempo de
cada palavra da transcrição levado ao corte. Os índices de palavra são os do `indice.py` e do
`efeitos.json`.
"""
import fractions, json, xml.etree.ElementTree as ET


def tempo(s):
    """Tempo FCPXML ("302/25s", "6s") em segundos (fração exata)."""
    s = (s or "0s").rstrip("s")
    return fractions.Fraction(s) if s else fractions.Fraction(0)


def frases_do_corte(fcpxml):
    """[(inicio, fim, texto)] no tempo do corte, e os trechos [(inicio_corte, inicio_fonte, duracao)]."""
    raiz = ET.parse(fcpxml).getroot()
    trechos, frases = [], []
    for clipe in raiz.iter("asset-clip"):
        off, ini, dur = tempo(clipe.get("offset")), tempo(clipe.get("start")), tempo(clipe.get("duration"))
        trechos.append((off, ini, dur))
        for t in clipe.findall("title"):
            texto = "".join(t.find("text").itertext()).strip() if t.find("text") is not None else ""
            if texto:
                t0 = off + tempo(t.get("offset")) - ini
                frases.append([t0, t0 + tempo(t.get("duration")), texto])
    frases.sort()
    for a, b in zip(frases, frases[1:]):
        a[1] = min(a[1], b[0])
    return [tuple(f) for f in frases if f[1] > f[0]], trechos


def palavras_indexadas(transcript, trechos):
    """{índice da palavra na transcrição: (início, fim) no corte}; as que caíram fora dos trechos somem.
    O índice é o mesmo do `indice.py` e do `cortes.json` do cortar-fala."""
    saida = {}
    for i, p in enumerate(json.load(open(transcript, encoding="utf-8"))):
        a, b = fractions.Fraction(p["start"]), fractions.Fraction(p["end"])
        # o trecho que contém o meio da palavra; na emenda, o que mais se sobrepõe a ela
        meio = (a + b) / 2
        dentro = [t for t in trechos if t[1] <= meio < t[1] + t[2]]
        if not dentro:
            dentro = sorted((t for t in trechos if min(b, t[1] + t[2]) > max(a, t[1])), key=lambda t: min(b, t[1] + t[2]) - max(a, t[1]))[-1:]
        if dentro:
            off, ini, dur = dentro[0]
            saida[i] = (max(off, a + off - ini), min(off + dur, b + off - ini))
    return saida


def palavras_no_corte(transcript, trechos):
    return [t for _, t in sorted(palavras_indexadas(transcript, trechos).items())]
