"""Legenda viva: a camada de legenda animada do corte, renderizada pelo HyperFrames com transparência.

Uso:
    python3 -I legenda_viva.py PASTA_DO_CORTE SAIDA.mov [--largura 1080 --altura 1920]
        [--tamanho 90] [--centro 0.8] [--so-dados]

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


def palavras_no_corte(transcript, trechos):
    """Palavras da transcrição com tempo levado ao corte; as que caíram fora dos trechos somem."""
    saida = []
    for p in json.load(open(transcript, encoding="utf-8")):
        meio = fractions.Fraction(p["start"] + p["end"]) / 2
        for off, ini, dur in trechos:
            if ini <= meio < ini + dur:
                d = off - ini
                saida.append((max(off, fractions.Fraction(p["start"]) + d), min(off + dur, fractions.Fraction(p["end"]) + d)))
                break
    return saida


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


PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8" />
<style>
@font-face{font-family:"Inter";src:url("fonts/Inter-700-latin.woff2") format("woff2");font-weight:700;font-display:block}
*{box-sizing:border-box}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent}
#stage{position:relative;width:__W__px;height:__H__px;overflow:hidden;background:transparent}
.linha{position:absolute;left:6%;right:6%;top:__TOP__px;transform:translateY(-50%);display:flex;flex-wrap:wrap;
  justify-content:center;align-items:center;gap:__GAP__px __GAPX__px;opacity:0}
.p{position:relative;font-family:"Inter";font-weight:700;font-size:__SIZE__px;line-height:1.15;color:#EAE2CF;
  padding:__PADY__px __PADX__px;border-radius:__RAD__px;text-transform:uppercase;white-space:nowrap;
  text-shadow:0 0 __SH__px rgba(20,20,20,.85),0 __SHY__px __SH2__px rgba(20,20,20,.6)}
.p .fundo{position:absolute;inset:0;background:#EAE2CF;border-radius:inherit;opacity:0;transform:scale(.86);z-index:-1}
.p span{position:relative}
</style></head>
<body>
<div id="stage" data-composition-id="legenda" data-start="0" data-duration="__DUR__" data-fps="__FPS__" data-width="__W__" data-height="__H__">
__LINHAS__
<script src="vendor/gsap.min.js"></script>
<script>
(function(){
  const L = __DADOS__;
  const tl = gsap.timeline({paused:true});
  L.forEach((l, i) => {
    const el = '#l' + i;
    const corte = i + 1 < L.length && L[i + 1].t0 - l.t1 < 0.05;
    tl.fromTo(el, {opacity:0, y:18}, {opacity:1, y:0, duration:0.12, ease:'power2.out'}, l.t0);
    l.palavras.forEach((p, j) => {
      const w = el + 'p' + j;
      tl.to(w + ' .fundo', {opacity:1, scale:1, duration:0.08, ease:'back.out(2)'}, p.t0);
      tl.to(w, {color:'#2E2E2E', textShadow:'none', duration:0.06}, p.t0);
      const fim = j + 1 < l.palavras.length ? l.palavras[j + 1].t0 : l.t1;
      if (j + 1 < l.palavras.length) {
        tl.to(w + ' .fundo', {opacity:0, scale:.86, duration:0.06}, fim);
        tl.to(w, {color:'#EAE2CF', textShadow:'__SOMBRA__', duration:0.06}, fim);
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


def pagina(linhas, w, h, tamanho, centro, dur):
    s = tamanho
    sombra = f"0 0 {round(s*.12)}px rgba(20,20,20,.85),0 {round(s*.04)}px {round(s*.2)}px rgba(20,20,20,.6)"
    blocos = []
    for i, l in enumerate(linhas):
        ps = "".join(f'<div class="p" id="l{i}p{j}"><div class="fundo"></div><span>{html.escape(p["txt"])}</span></div>'
                     for j, p in enumerate(l["palavras"]))
        blocos.append(f'<div class="linha" id="l{i}">{ps}</div>')
    troca = {"__W__": w, "__H__": h, "__TOP__": round(h * centro), "__SIZE__": s, "__GAP__": round(s * .1),
             "__GAPX__": round(s * .08), "__PADY__": round(s * .02), "__PADX__": round(s * .14), "__RAD__": round(s * .14),
             "__SH__": round(s * .12), "__SHY__": round(s * .04), "__SH2__": round(s * .2), "__DUR__": f"{dur:.3f}",
             "__FPS__": FPS, "__LINHAS__": "\n".join(blocos), "__DADOS__": json.dumps(linhas), "__SOMBRA__": sombra}
    out = PAGINA
    for k, v in troca.items():
        out = out.replace(k, str(v))
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("corte")
    a.add_argument("saida")
    a.add_argument("--largura", type=int, default=1080)
    a.add_argument("--altura", type=int, default=1920)
    a.add_argument("--tamanho", type=int, default=90, help="px no quadro de saída")
    a.add_argument("--centro", type=float, default=0.8, help="altura do centro da legenda, fração do quadro")
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
    dur = float(max(off + d for off, _, d in trechos))

    proj = os.path.splitext(os.path.abspath(o.saida))[0] + "_hf"
    shutil.rmtree(proj, ignore_errors=True)
    os.makedirs(os.path.join(proj, "fonts"))
    os.makedirs(os.path.join(proj, "vendor"))
    shutil.copy(os.path.join(MOTION, "fonts", "Inter-700-latin.woff2"), os.path.join(proj, "fonts"))
    shutil.copy(os.path.join(MOTION, "vendor", "gsap.min.js"), os.path.join(proj, "vendor"))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina(linhas, o.largura, o.altura, o.tamanho, o.centro, dur))
    r = subprocess.run([o.hyperframes, "render", proj, "--format", "mov", "-o", os.path.abspath(o.saida), "--quiet"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(o.saida):
        sys.exit(f"hyperframes falhou:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    print(json.dumps({"saida": os.path.abspath(o.saida), "linhas": len(linhas), "duracao": round(dur, 3)}))


if __name__ == "__main__":
    main()
