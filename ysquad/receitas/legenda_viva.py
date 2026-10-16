"""Legenda viva: a camada de legenda animada do corte, renderizada pelo HyperFrames com transparência.

Uso:
    python3 -I legenda_viva.py PASTA_DO_CORTE SAIDA.mov [--estilo caixa|acende|pop|acumula|limpa]
        [--largura 1080 --altura 1920] [--tamanho 90] [--centro 0.8] [--so-dados]
    python3 -I legenda_viva.py PASTA_DO_CORTE PASTA_DAS_AMOSTRAS --amostras   (um vídeo e um quadro por estilo)

Lê o corte do `cortar-fala`: as frases são os <title> do FCPXML (texto já corrigido, tempo no
corte) e o tempo de cada palavra vem do `transcript.json` (tempo da fonte), levado ao corte pelos
trechos do FCPXML. A frase entra inteira; a palavra falada ganha a caixa creme com texto grafite
(`legenda-viva` do frame.md do motion-ysquad); a frase sai quando a próxima entra ou acaba a fala.

Sai um .mov ProRes 4444 com alfa do tamanho do quadro, pra ir numa trilha de cima no FilmCraft.
Fonte e GSAP vêm do `~/motion-ysquad` (fora deste repositório).
"""
import argparse, fractions, glob, html, json, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET

MOTION = os.path.expanduser("~/motion-ysquad/.claude/skills/talking-head-recut/assets")
FPS = 25


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


def montar_linhas(frases, palavras):
    """Cada frase com o tempo de cada palavra. Usa a transcrição quando a contagem bate; senão reparte
    a duração da frase pelo tamanho das palavras (correções como "a IA" mudam a contagem)."""
    linhas = []
    for t0, t1, texto in frases:
        tokens = texto.split()
        dentro = [w for w in palavras if t0 <= (w[0] + w[1]) / 2 < t1]
        if len(dentro) == len(tokens):
            tempos = [(max(t0, a), min(t1, b)) for a, b in dentro]
        else:
            pesos = [len(x) + 1 for x in tokens]
            total, acc, tempos = sum(pesos), t0, []
            for p in pesos:
                fim = acc + (t1 - t0) * p / total
                tempos.append((acc, fim))
                acc = fim
        linhas.append({"t0": float(t0), "t1": float(t1),
                       "palavras": [{"txt": tk, "t0": float(a), "t1": float(b)} for tk, (a, b) in zip(tokens, tempos)]})
    return linhas


ESTILOS = {
    # a frase entra inteira; a palavra falada ganha a caixa creme com texto grafite (frame.md legenda-viva)
    "caixa": "frase inteira, palavra falada na caixa creme",
    # a frase entra apagada e cada palavra acende quando é dita, e fica acesa
    "acende": "frase apagada, cada palavra acende ao ser dita",
    # uma palavra por vez, grande, entrando com quique
    "pop": "uma palavra por vez, grande, com quique",
    # as palavras aparecem conforme são ditas; a falada em negrito, as anteriores no fino
    # (repertório da animar-fala: "negrito que passa adiante")
    "acumula": "palavras aparecem ao serem ditas, a falada em negrito",
    # a frase fixa, sem animação
    "limpa": "frase fixa, sem animação",
}

PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8" />
<style>
@font-face{font-family:"Inter";src:url("fonts/Inter-400-latin.woff2") format("woff2");font-weight:400;font-display:block}
@font-face{font-family:"Inter";src:url("fonts/Inter-700-latin.woff2") format("woff2");font-weight:700;font-display:block}
*{box-sizing:border-box}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent}
#stage{position:relative;width:__W__px;height:__H__px;overflow:hidden;background:transparent}
.linha{position:absolute;left:6%;right:6%;top:__TOP__px;transform:translateY(-50%);display:flex;flex-wrap:wrap;
  justify-content:center;align-items:center;gap:__GAP__px __GAPX__px;opacity:0}
.p{position:relative;font-family:"Inter";font-weight:700;font-size:__SIZE__px;line-height:1.15;color:#EAE2CF;
  padding:__PADY__px __PADX__px;border-radius:__RAD__px;text-transform:uppercase;white-space:nowrap;text-shadow:__SOMBRA__}
.p .fundo{position:absolute;inset:0;background:#EAE2CF;border-radius:inherit;opacity:0;transform:scale(.86);z-index:-1}
.p span{position:relative}
.pop .linha{display:block}
.pop .p{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:__SIZEPOP__px;opacity:0}
.acumula .p{opacity:0}
</style></head>
<body>
<div id="stage" class="__ESTILO__" data-composition-id="legenda" data-start="0" data-duration="__DUR__" data-fps="__FPS__" data-width="__W__" data-height="__H__">
__LINHAS__
<script src="vendor/gsap.min.js"></script>
<script>
(function(){
  const L = __DADOS__, E = "__ESTILO__", SOMBRA = "__SOMBRA__";
  const tl = gsap.timeline({paused:true});
  L.forEach((l, i) => {
    const el = '#l' + i;
    const corte = i + 1 < L.length && L[i + 1].t0 - l.t1 < 0.05;
    const prox = (j) => j + 1 < l.palavras.length ? l.palavras[j + 1].t0 : l.t1;
    if (E === "limpa") {
      tl.set(el, {opacity:1}, l.t0);
    } else if (E === "pop") {
      tl.set(el, {opacity:1}, l.t0);
    } else {
      tl.fromTo(el, {opacity:0, y:18}, {opacity:1, y:0, duration:0.12, ease:'power2.out'}, l.t0);
    }
    l.palavras.forEach((p, j) => {
      const w = el + 'p' + j, fim = prox(j), ultima = j + 1 === l.palavras.length;
      if (E === "caixa") {
        tl.to(w + ' .fundo', {opacity:1, scale:1, duration:0.08, ease:'back.out(2)'}, p.t0);
        tl.to(w, {color:'#2E2E2E', textShadow:'none', duration:0.06}, p.t0);
        if (!ultima) {
          tl.to(w + ' .fundo', {opacity:0, scale:.86, duration:0.06}, fim);
          tl.to(w, {color:'#EAE2CF', textShadow:SOMBRA, duration:0.06}, fim);
        }
      } else if (E === "acende") {
        tl.fromTo(w, {opacity:0.38}, {opacity:1, duration:0.07}, p.t0);
        if (j === 0) tl.set(l.palavras.map((_, k) => el + 'p' + k).join(','), {opacity:0.38}, l.t0);
      } else if (E === "pop") {
        tl.fromTo(w, {opacity:1, scale:0.6}, {opacity:1, scale:1, duration:0.14, ease:'back.out(2.6)', immediateRender:false}, p.t0);
        if (!ultima) tl.set(w, {opacity:0}, fim);
      } else if (E === "acumula") {
        tl.fromTo(w, {opacity:0, y:10}, {opacity:1, y:0, duration:0.08, ease:'power2.out'}, p.t0);
        tl.set(w, {fontWeight:700}, p.t0);
        if (!ultima) tl.set(w, {fontWeight:400}, fim);
      }
    });
    tl.to(el, {opacity:0, duration: corte ? 0.001 : 0.1}, corte ? l.t1 - 0.001 : l.t1);
  });
  window.__timelines = window.__timelines || {};
  window.__timelines["legenda"] = tl;
})();
</script>
</div>
</body></html>
"""


def pagina(linhas, w, h, tamanho, centro, dur, estilo="caixa"):
    s = tamanho
    sombra = f"0 0 {round(s*.12)}px rgba(20,20,20,.85),0 {round(s*.04)}px {round(s*.2)}px rgba(20,20,20,.6)"
    blocos = []
    for i, l in enumerate(linhas):
        ps = "".join(f'<div class="p" id="l{i}p{j}"><div class="fundo"></div><span>{html.escape(p["txt"])}</span></div>'
                     for j, p in enumerate(l["palavras"]))
        blocos.append(f'<div class="linha" id="l{i}">{ps}</div>')
    troca = {"__W__": w, "__H__": h, "__TOP__": round(h * centro), "__SIZE__": s, "__SIZEPOP__": round(s * 1.45),
             "__GAP__": round(s * .1), "__GAPX__": round(s * .08), "__PADY__": round(s * .02), "__PADX__": round(s * .14),
             "__RAD__": round(s * .14), "__DUR__": f"{dur:.3f}", "__FPS__": FPS, "__LINHAS__": "\n".join(blocos),
             "__DADOS__": json.dumps(linhas), "__SOMBRA__": sombra, "__ESTILO__": estilo}
    out = PAGINA
    for k, v in troca.items():
        out = out.replace(k, str(v))
    return out


def renderizar(linhas, w, h, tamanho, centro, dur, estilo, saida, hyperframes):
    """Escreve o projeto HyperFrames ao lado da saída e renderiza o .mov com alfa."""
    proj = os.path.splitext(os.path.abspath(saida))[0] + "_hf"
    shutil.rmtree(proj, ignore_errors=True)
    os.makedirs(os.path.join(proj, "fonts"))
    os.makedirs(os.path.join(proj, "vendor"))
    for fonte in ("Inter-400-latin.woff2", "Inter-700-latin.woff2"):
        shutil.copy(os.path.join(MOTION, "fonts", fonte), os.path.join(proj, "fonts"))
    shutil.copy(os.path.join(MOTION, "vendor", "gsap.min.js"), os.path.join(proj, "vendor"))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina(linhas, w, h, tamanho, centro, dur, estilo))
    r = subprocess.run([hyperframes, "render", proj, "--format", "mov", "-o", os.path.abspath(saida), "--quiet"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(saida):
        sys.exit(f"hyperframes falhou:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


def amostras(corte, linhas, w, h, tamanho, centro, pasta, hyperframes, de=None, ate=None):
    """Um vídeo curto por estilo, com a legenda sobre o próprio vídeo do corte, e uma folha com um
    quadro de cada. Usa as frases entre `de` e `ate` (padrão: as primeiras ~6 s do corte)."""
    os.makedirs(pasta, exist_ok=True)
    de = linhas[0]["t0"] if de is None else de
    ate = de + 6.0 if ate is None else ate
    janela = [l for l in linhas if l["t0"] >= de and l["t1"] <= ate + 0.01]
    if not janela:
        sys.exit("nenhuma frase inteira nessa janela")
    t0, t1 = janela[0]["t0"], janela[-1]["t1"]
    rel = [{"t0": l["t0"] - t0, "t1": l["t1"] - t0, "palavras": [dict(p, t0=p["t0"] - t0, t1=p["t1"] - t0) for p in l["palavras"]]}
           for l in janela]
    # o vídeo do corte (sem legenda) no mesmo trecho: o .mp4 mais novo que a receita gerou sem legenda,
    # ou o FCPXML renderizado pelo FilmCraft fica pra receita; aqui basta um fundo do vídeo de origem
    fundo = os.path.join(pasta, "fundo.mp4")
    if not os.path.exists(fundo):
        sys.exit(f"falta {fundo}: um trecho do corte sem legenda, {w}x{h}, começando em {t0:.2f} s do corte "
                 "(a receita montar_video.py --amostras gera)")
    quadros = []
    meio = rel[0]["palavras"][min(1, len(rel[0]["palavras"]) - 1)]["t0"] + 0.05
    for estilo in ESTILOS:
        mov = os.path.join(pasta, f"{estilo}.mov")
        renderizar(rel, w, h, tamanho, centro, t1 - t0, estilo, mov, hyperframes)
        mp4 = os.path.join(pasta, f"{estilo}.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", fundo, "-i", mov, "-filter_complex", "[0][1]overlay=format=auto",
                        "-t", f"{t1 - t0:.3f}", "-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac", mp4], check=True)
        png = os.path.join(pasta, f"{estilo}.png")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{meio:.3f}", "-i", mp4, "-frames:v", "1",
                        "-vf", "scale=-1:640", png], check=True)
        quadros.append(png)
        shutil.rmtree(os.path.splitext(mov)[0] + "_hf", ignore_errors=True)
        os.remove(mov)
    folha = os.path.join(pasta, "folha.png")
    entradas = sum((["-i", q] for q in quadros), [])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *entradas, "-filter_complex", f"hstack=inputs={len(quadros)}", folha], check=True)
    return folha


def main():
    a = argparse.ArgumentParser()
    a.add_argument("corte")
    a.add_argument("saida", help="o .mov da legenda, ou a pasta das amostras com --amostras")
    a.add_argument("--estilo", choices=ESTILOS, default="caixa")
    a.add_argument("--largura", type=int, default=1080)
    a.add_argument("--altura", type=int, default=1920)
    a.add_argument("--tamanho", type=int, default=90, help="px no quadro de saída")
    a.add_argument("--centro", type=float, default=0.8, help="altura do centro da legenda, fração do quadro")
    a.add_argument("--amostras", action="store_true", help="um vídeo curto e um quadro por estilo, na pasta `saida`")
    a.add_argument("--de", type=float, help="amostras: início da janela, em segundos do corte")
    a.add_argument("--so-dados", action="store_true", help="só imprime as linhas com tempo, sem renderizar")
    a.add_argument("--hyperframes", default=os.environ.get("HYPERFRAMES", "hyperframes"))
    o = a.parse_args()

    xml = glob.glob(os.path.join(o.corte, "*.fcpxml"))
    if len(xml) != 1:
        sys.exit(f"esperava um .fcpxml em {o.corte}, achei {len(xml)}")
    frases, trechos = frases_do_corte(xml[0])
    if not frases:
        sys.exit("o corte não tem <title> de legenda")
    linhas = montar_linhas(frases, palavras_no_corte(os.path.join(o.corte, "transcript.json"), trechos))
    if o.so_dados:
        print(json.dumps(linhas, ensure_ascii=False, indent=1))
        return
    if o.amostras:
        folha = amostras(o.corte, linhas, o.largura, o.altura, o.tamanho, o.centro, o.saida, o.hyperframes, de=o.de)
        print(json.dumps({"folha": folha, "estilos": list(ESTILOS)}))
        return
    dur = float(max(off + d for off, _, d in trechos))
    renderizar(linhas, o.largura, o.altura, o.tamanho, o.centro, dur, o.estilo, o.saida, o.hyperframes)
    print(json.dumps({"saida": os.path.abspath(o.saida), "linhas": len(linhas), "duracao": round(dur, 3), "estilo": o.estilo}))


if __name__ == "__main__":
    main()
