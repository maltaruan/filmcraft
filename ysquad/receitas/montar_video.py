"""Receita do agente: corte do `cortar-fala` -> vídeo final, pelo FilmCraft sem janela (MCP).

Uso:
    python3 -I montar_video.py PASTA_DO_CORTE SAIDA_SEM_EXTENSAO
        [--formato 9x16|16x9|4x3] [--motion CLIPE.mov --motion-em 0.5]
        [--cor] [--sem-legenda | --legenda-viva] [--legenda-tamanho 72]
        [--musica TRILHA --musica-db -18] [--sem-voz] [--lufs -14] [--cli CAMINHO_DO_filmcraft-cli]

PASTA_DO_CORTE é a pasta de trabalho do `cortar-fala` (`<nome>.fcpxml` + `legenda.srt`).

- 9x16: o corte vertical encaixado em 1080x1920.
- 16x9 / 4x3: preenche o quadro com o foco acompanhando o rosto (`../rosto/acompanhar.py`,
  Vision do macOS), mapeado do tempo da fonte para o tempo de cada trecho do corte.
- --motion: clipe com transparência (ex.: HyperFrames `--format mov`) na V2. Vertical, encaixa
  no quadro; horizontal, entra a 100 % no terço de baixo à esquerda.
- --cor: Lumetri leve (exposição, contraste, saturação, altas luzes, sombras).
- A legenda vem dos <title> do FCPXML (o `.srt` só se o corte não tiver) e sai gravada na imagem.
- --legenda-viva: em vez da legenda fixa, a camada animada do `legenda_viva.py` (HyperFrames,
  palavra falada na caixa creme), renderizada em paralelo e posta na trilha de cima.
- efeitos.json na pasta do corte (opcional), escrito por quem leu a fala, com índices de palavra
  do `indice.py` (inclusivos):
    {"zoom": [{"de": 16, "ate": 18, "escala": 115, "entrada": "seco|suave"}],
     "desfoque": [{"de": 56, "ate": 58, "forca": 40, "sentido": "abre|fecha"}],
     "broll": [{"de": 61, "ate": 64, "arquivo": "/caminho/trecho.mp4", "inicio": 0.0, "zoom": 108}]}
  zoom = efeito Transform centrado no rosto, por cima do enquadramento: "seco" corta pra escala
  na primeira palavra e volta no fim da última; "suave" aproxima devagar até o fim e corta de volta.
  desfoque = Gaussian Blur: "abre" vai da força a zero (foco que chega), "fecha" de zero à força.
  broll = o trecho aprovado (pela get-brolls) cobre a fala da primeira à última palavra, numa
  trilha acima do vídeo, sem som, preenchendo o quadro; "zoom" aproxima devagar até a escala dada.
  Camadas, de baixo pra cima: vídeo, B-roll, motion, legenda viva.
- Voz (padrão, --sem-voz desliga): Essential Sound de diálogo com limpeza leve (ruído, sala,
  graves de manuseio, compressor, EQ "Balanced Voice"). --musica entra na A2 como música, abaixando
  sozinha sob a fala (ducking). A exportação normaliza o volume pra --lufs (-14, Instagram e YouTube).
- Exporta H.264 com o chip de vídeo do Mac (`hardwareEncoding: auto`), compondo na placa de vídeo
  (`gpuRendering: auto`; o que ela não faz cai sozinho no processador).
"""
import argparse, glob, json, os, re, subprocess, sys, time, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import legenda_viva  # noqa: E402
TPS = 254_016_000_000
TAMANHOS = {"9x16": (1080, 1920), "16x9": (1920, 1080), "4x3": (1440, 1080)}
# limpeza leve: o que a fala de quarto/escritório costuma pedir, sem deixar a voz "processada"
VOZ = {"repair.noise.on": True, "repair.noise.amount": 3.0, "repair.reverb.on": True, "repair.reverb.amount": 2.0,
       "repair.rumble.on": True, "repair.rumble.amount": 4.0, "clarity.dynamics.on": True, "clarity.dynamics.amount": 4.0,
       "clarity.eq.on": True, "clarity.eq.amount": 4.0, "clarity.eq_preset": "Balanced Voice"}
COR = {"exposure": 0.3, "contrast": 15, "saturation": 115, "highlights": -20, "shadows": 10}


class Mcp:
    def __init__(self, cli):
        self.p = subprocess.Popen([cli, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "montar_video", "version": "1"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        while True:
            m = json.loads(self.p.stdout.readline())
            if m.get("id") == self.n:
                return m.get("result", {})

    def run(self, cmd, params=None):
        r = self.rpc("tools/call", {"name": "command_run", "arguments": {"id": cmd, "params": params or {}}})
        if r.get("isError"):
            sys.exit(f"{cmd}: {r['content'][0].get('text', '')}")
        return json.loads(r["content"][0].get("text", "null"))

    def fechar(self):
        self.p.stdin.close()
        self.p.wait()


def video_do_fcpxml(path):
    """O arquivo de vídeo que o FCPXML do corte referencia (primeiro `src="file://..."`)."""
    m = re.search(r'src="file://([^"]+)"', open(path, encoding="utf-8").read())
    if not m:
        sys.exit(f"nenhum vídeo referenciado em {path}")
    return urllib.parse.unquote(m.group(1))


def focos_do_rosto(video, cli):
    """focusKeys no tempo da FONTE (o clipe inteiro numa sequência que começa nele)."""
    out = subprocess.run([sys.executable, "-I", os.path.join(AQUI, "..", "rosto", "acompanhar.py"), video, "--cli", cli],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def formato_da_fonte(fcpxml):
    m = re.search(r'<format [^>]*width="(\d+)" height="(\d+)"', open(fcpxml, encoding="utf-8").read())
    return (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)


def aplicar_efeitos(m, corte, xml, clipes, focos):
    """Aplica o efeitos.json do corte nos clipes da V1. Tempo do corte -> tempo da mídia de cada clipe."""
    caminho = os.path.join(corte, "efeitos.json")
    if not os.path.exists(caminho):
        return
    plano = json.load(open(caminho, encoding="utf-8"))
    _, trechos = legenda_viva.frases_do_corte(xml)
    pal = legenda_viva.palavras_indexadas(os.path.join(corte, "transcript.json"), trechos)
    fw, fh = formato_da_fonte(xml)
    um_quadro = TPS // 25

    def faixa(e):
        if e["de"] not in pal or e["ate"] not in pal:
            sys.exit(f"efeito {e}: palavra fora do corte")
        return float(pal[e["de"]][0]), float(pal[e["ate"]][1])

    def pedacos(t0, t1):
        """(clipe, mídia em t0, mídia em t1) de cada clipe que a faixa toca."""
        for c in clipes:
            ini, fim = c["start"] / TPS, (c["start"] + c["sourceOut"] - c["sourceIn"]) / TPS
            a, b = max(t0, ini), min(t1, fim)
            if b > a:
                yield c, c["sourceIn"] + round((a - ini) * TPS), c["sourceIn"] + round((b - ini) * TPS), c["sourceIn"]

    feitos = set()
    por_id = {c["clip"]: c for c in clipes}

    def kf(cid, efeito, param, t, v, interp):
        """Keyframe no tempo de mídia `t`: cria pelo tempo da linha do tempo (addKeyframe liga/desliga,
        então só uma vez por ponto) e acerta valor e interpolação pelo tempo de mídia."""
        c = por_id[cid]
        t = min(max(int(t), c["sourceIn"]), c["sourceOut"] - 1)  # o quadro depois do fim cai dentro do clipe
        if (cid, efeito, param, t) not in feitos:
            m.run("effects.addKeyframe", {"clip": cid, "effect": efeito, "param": param, "time": c["start"] + t - c["sourceIn"]})
            feitos.add((cid, efeito, param, t))
        m.run("effects.setKeyframe", {"clip": cid, "effect": efeito, "param": param, "mediaTime": t, "value": v})
        m.run("effects.setInterpolation", {"clip": cid, "effect": efeito, "param": param, "mediaTime": int(t), "interpolation": interp})

    com_transform, com_blur = set(), set()
    for z in plano.get("zoom", []):
        t0, t1 = faixa(z)
        for c, a, b, base in pedacos(t0, t1):
            cid = c["clip"]
            if cid not in com_transform:
                m.run("effects.apply", {"clips": [cid], "effect": "Transform"})
                src = c["sourceIn"] / TPS
                perto = min(focos, key=lambda k: abs(k["seconds"] - src)) if focos else {"focus": [0.5, 0.4]}
                ponto = [perto["focus"][0] * fw, perto["focus"][1] * fh]
                for prm in ("anchor", "position"):
                    m.run("effects.setParam", {"clip": cid, "effect": "transform", "param": prm, "value": ponto})
                kf(cid, "transform", "scale_height", base, 100.0, "hold")
                com_transform.add(cid)
            s = float(z.get("escala", 115))
            if z.get("entrada", "seco") == "suave":
                kf(cid, "transform", "scale_height", a, 100.0, "easeOut")
                kf(cid, "transform", "scale_height", b, s, "hold")
            else:
                kf(cid, "transform", "scale_height", a, s, "hold")
            kf(cid, "transform", "scale_height", b + um_quadro, 100.0, "hold")
    for d in plano.get("desfoque", []):
        t0, t1 = faixa(d)
        forte, zero = float(d.get("forca", 40)), 0.0
        ida, volta = (forte, zero) if d.get("sentido", "abre") == "abre" else (zero, forte)
        for c, a, b, base in pedacos(t0, t1):
            cid = c["clip"]
            if cid not in com_blur:
                m.run("effects.apply", {"clips": [cid], "effect": "Gaussian Blur"})
                m.run("effects.setParam", {"clip": cid, "effect": "gaussian_blur", "param": "repeat_edge", "value": True})
                kf(cid, "gaussian_blur", "blurriness", base, 0.0, "hold")
                com_blur.add(cid)
            kf(cid, "gaussian_blur", "blurriness", a, ida, "linear")
            kf(cid, "gaussian_blur", "blurriness", b, volta, "hold")
            kf(cid, "gaussian_blur", "blurriness", b + um_quadro, 0.0, "hold")
    trilha_broll = None
    for r in plano.get("broll", []):
        t0, t1 = faixa(r)
        item = m.run("file.import", {"paths": [os.path.abspath(r["arquivo"])]})["items"][0]
        ini = round(float(r.get("inicio", 0.0)) * TPS)
        bc = m.run("timeline.place", {"item": item, "track": trilha_broll or "new", "time": round(t0 * TPS), "sourceIn": ini,
                                      "duration": round((t1 - t0) * TPS), "audio": False})["clips"][0]
        trilha_broll = trilha_broll or "V2"
        m.run("clip.fillFrame", {"clips": [bc]})
        if r.get("zoom"):
            # o clipe como ficou (o encaixe arredonda pro quadro)
            c = next(x for tr in m.run("sequence.inspect")["video"] for x in tr["items"] if x["clip"] == bc)
            por_id[bc] = c
            m.run("effects.apply", {"clips": [bc], "effect": "Transform"})
            kf(bc, "transform", "scale_height", c["sourceIn"], 100.0, "linear")
            kf(bc, "transform", "scale_height", c["sourceOut"], float(r["zoom"]), "hold")
    print(f"efeitos: {len(plano.get('zoom', []))} zoom, {len(plano.get('desfoque', []))} desfoque, "
          f"{len(plano.get('broll', []))} B-roll", file=sys.stderr)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("corte")
    a.add_argument("saida")
    a.add_argument("--formato", choices=TAMANHOS, default="9x16")
    a.add_argument("--motion")
    a.add_argument("--motion-em", type=float, default=0.5)
    a.add_argument("--cor", action="store_true")
    a.add_argument("--sem-legenda", action="store_true")
    a.add_argument("--legenda-viva", action="store_true")
    a.add_argument("--musica")
    a.add_argument("--musica-db", type=float, default=-18.0, help="nível da música sem fala")
    a.add_argument("--sem-voz", action="store_true")
    a.add_argument("--lufs", type=float, default=-14.0)
    a.add_argument("--legenda-tamanho", type=float, default=72.0, help="16x9/4x3, px por 1080 linhas")
    a.add_argument("--cli", default=os.path.join(AQUI, "..", "..", "target", "release", "filmcraft-cli"))
    o = a.parse_args()
    cli = os.path.abspath(o.cli)
    xml = glob.glob(os.path.join(o.corte, "*.fcpxml"))
    if len(xml) != 1:
        sys.exit(f"esperava um .fcpxml em {o.corte}, achei {len(xml)}")
    w, h = TAMANHOS[o.formato]
    viva = o.legenda_viva and not o.sem_legenda
    if viva:
        # renderiza enquanto o FilmCraft monta; no reel, a altura que o corte escolheu (80 %)
        mov = os.path.abspath(o.saida) + "_legenda.mov"
        tam, centro = (90, 0.8) if h > w else (round(o.legenda_tamanho * h / 1080), 0.86)
        legenda = subprocess.Popen([sys.executable, "-I", os.path.join(AQUI, "legenda_viva.py"), o.corte, mov,
                                    "--largura", str(w), "--altura", str(h), "--tamanho", str(tam), "--centro", str(centro)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    m = Mcp(cli)
    imp = m.run("file.import", {"paths": [os.path.abspath(xml[0])]})
    for d in imp.get("documents", []):
        for nota in d.get("report", []):
            print("importação:", nota, file=sys.stderr)
    seq = m.run("sequence.inspect")
    clipes = seq["video"][0]["items"]
    print(f"corte: {len(clipes)} trechos, {seq['duration'] / TPS:.1f} s", file=sys.stderr)
    if (w, h) != (seq["settings"]["width"], seq["settings"]["height"]):
        m.run("sequence.settings", {"width": w, "height": h})

    tem_efeitos = os.path.exists(os.path.join(o.corte, "efeitos.json"))
    focos = focos_do_rosto(video_do_fcpxml(xml[0]), cli) if (h <= w or tem_efeitos) else []
    if h > w:
        m.run("clip.fillFrame", {"clips": [c["clip"] for c in clipes]})
    else:
        for c in clipes:
            si, so, st = c["sourceIn"] / TPS, c["sourceOut"] / TPS, c["start"] / TPS
            keys = [{"seconds": round(st + k["seconds"] - si, 3), "focus": k["focus"]} for k in focos if si <= k["seconds"] <= so]
            if keys:
                m.run("clip.fillFrame", {"clips": [c["clip"]], "focusKeys": keys})
            elif focos:
                perto = min(focos, key=lambda k: abs(k["seconds"] - (si + so) / 2))
                m.run("clip.fillFrame", {"clips": [c["clip"]], "focus": perto["focus"]})
            else:
                m.run("clip.fillFrame", {"clips": [c["clip"]]})

    aplicar_efeitos(m, o.corte, xml[0], clipes, focos)
    ids = [c["clip"] for c in clipes]
    if o.cor:
        m.run("effects.apply", {"clips": ids, "effect": "Lumetri Color"})
        for cid in ids:
            for k, v in COR.items():
                m.run("effects.setParam", {"clip": cid, "effect": "lumetri", "param": k, "value": v})
    if not o.sem_legenda and not viva:
        # os títulos do FCPXML já entram como trilha de legenda; o .srt só cobre corte sem eles
        trilhas = m.run("captions.list").get("tracks", [])
        trilha = trilhas[0]["id"] if trilhas else None
        srt = os.path.join(o.corte, "legenda.srt")
        if trilha is None and os.path.exists(srt):
            trilha = m.run("captions.import", {"path": srt})["track"]
        if trilha is not None and h < w:
            # o tamanho é por 1080 linhas: o do reel não cabe no quadro largo
            # e a altura que o corte escolheu pro reel cai no queixo: desce pra perto da borda
            m.run("captions.setStyle", {"track": trilha, "size": o.legenda_tamanho, "anchor": "bottom", "margin": 0.1})
    if o.motion:
        item = m.run("file.import", {"paths": [os.path.abspath(o.motion)]})["items"][0]
        mc = m.run("timeline.place", {"item": item, "track": "new", "seconds": o.motion_em})["clips"][0]
        if h > w:
            m.run("clip.fitToFrame", {"clips": [mc]})
            # a legenda do corte fica a 20% da borda de baixo: a faixa sobe pra não pisar nela
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "position", "value": [w / 2, h / 2 - 220.0]})
        else:
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "scale", "value": 100.0})
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "position", "value": [540.0, 240.0 * h / 1080]})
    falas = [c["clip"] for c in seq["audio"][0]["items"]]
    if not o.sem_voz:
        m.run("essentialSound.setType", {"clips": falas, "type": "dialogue"})
        m.run("essentialSound.set", {"clips": falas, "values": VOZ})
    if o.musica:
        item = m.run("file.import", {"paths": [os.path.abspath(o.musica)]})["items"][0]
        dur = round(seq["duration"])
        mus = m.run("timeline.place", {"item": item, "audioTrack": "new", "time": 0, "duration": dur, "video": False})["clips"]
        m.run("essentialSound.setType", {"clips": mus, "type": "music"})
        m.run("essentialSound.set", {"clips": mus, "values": {"volume.on": True, "volume.level_db": o.musica_db, "ducking.enabled": True,
                                                              "ducking.reduce_db": -12.0, "ducking.fade_s": 0.4}})
        duck = m.run("essentialSound.generateDucking", {"clips": mus})
        print(f"música: ducking {json.dumps(duck)[:200]}", file=sys.stderr)

    if viva:
        saida, erro = legenda.communicate()
        if legenda.returncode != 0:
            sys.exit(f"legenda viva falhou: {erro[-1500:]}")
        item = m.run("file.import", {"paths": [mov]})["items"][0]
        lc = m.run("timeline.place", {"item": item, "track": "new", "seconds": 0.0})["clips"][0]
        m.run("clip.fitToFrame", {"clips": [lc]})

    t = time.time()
    r = m.run("file.exportMedia", {"path": os.path.abspath(o.saida) + ".mp4", "format": "h264", "hardwareEncoding": "auto", "gpuRendering": "auto",
                                  "width": w, "height": h, "burnCaptions": not o.sem_legenda and not viva,
                                  "loudnessLufs": o.lufs, "wait": True})
    m.fechar()
    print(f"exportado em {time.time() - t:.1f} s: {json.dumps(r.get('result', r))}")


if __name__ == "__main__":
    main()
