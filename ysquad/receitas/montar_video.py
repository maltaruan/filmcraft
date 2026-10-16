"""Receita do agente: corte do `cortar-fala` -> vídeo final, pelo FilmCraft sem janela (MCP).

Uso:
    python3 -I montar_video.py PASTA_DO_CORTE SAIDA_SEM_EXTENSAO
        [--formato 9x16|16x9|4x3] [--motion CLIPE.mov --motion-em 0.5]
        [--cor] [--sem-legenda | --legenda-viva] [--legenda-tamanho 72] [--cli CAMINHO_DO_filmcraft-cli]

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
- Exporta H.264 com o chip de vídeo do Mac (`hardwareEncoding: auto`).
"""
import argparse, glob, json, os, re, subprocess, sys, time, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
TPS = 254_016_000_000
TAMANHOS = {"9x16": (1080, 1920), "16x9": (1920, 1080), "4x3": (1440, 1080)}
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

    if h > w:
        m.run("clip.fillFrame", {"clips": [c["clip"] for c in clipes]})
    else:
        focos = focos_do_rosto(video_do_fcpxml(xml[0]), cli)
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
        m.run("sequence.addTracks", {"video": 1, "audio": 0})
        mc = m.run("timeline.place", {"item": item, "track": "V2", "seconds": o.motion_em})["clips"][0]
        if h > w:
            m.run("clip.fitToFrame", {"clips": [mc]})
            # a legenda do corte fica a 20% da borda de baixo: a faixa sobe pra não pisar nela
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "position", "value": [w / 2, h / 2 - 220.0]})
        else:
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "scale", "value": 100.0})
            m.run("effects.setParam", {"clip": mc, "effect": "motion", "param": "position", "value": [540.0, 240.0 * h / 1080]})
    if viva:
        saida, erro = legenda.communicate()
        if legenda.returncode != 0:
            sys.exit(f"legenda viva falhou: {erro[-1500:]}")
        item = m.run("file.import", {"paths": [mov]})["items"][0]
        m.run("sequence.addTracks", {"video": 1, "audio": 0})
        trilha = "V3" if o.motion else "V2"
        lc = m.run("timeline.place", {"item": item, "track": trilha, "seconds": 0.0})["clips"][0]
        m.run("clip.fitToFrame", {"clips": [lc]})

    t = time.time()
    r = m.run("file.exportMedia", {"path": os.path.abspath(o.saida) + ".mp4", "format": "h264", "hardwareEncoding": "auto",
                                  "width": w, "height": h, "burnCaptions": not o.sem_legenda and not viva, "wait": True})
    m.fechar()
    print(f"exportado em {time.time() - t:.1f} s: {json.dumps(r.get('result', r))}")


if __name__ == "__main__":
    main()
