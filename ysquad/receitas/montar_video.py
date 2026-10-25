"""Receita do agente: corte do `cortar-fala` -> vídeo final, pelo FilmCraft sem janela (MCP).

Uso:
    python3 -I montar_video.py PASTA_DO_CORTE SAIDA_SEM_EXTENSAO
        [--formato 9x16|16x9|4x3]
        [--cor] [--sem-legenda | --legenda-viva LEGENDA.mov] [--legenda-tamanho 72]
        (--musica TRILHA [--musica-db -18 --musica-abaixa -4.5] | --sem-musica) [--sem-voz] [--lufs -14] [--sabor LC-709TypeA] [--sem-log] [--sem-celular] [--cli CAMINHO_DO_filmcraft-cli]

PASTA_DO_CORTE é a pasta de trabalho do `cortar-fala` (`<nome>.fcpxml` + `legenda.srt`).

- 9x16: o corte vertical encaixado em 1080x1920.
- 16x9 / 4x3: preenche o quadro com o foco acompanhando o rosto (`../rosto/acompanhar.py`,
  Vision do macOS), mapeado do tempo da fonte para o tempo de cada trecho do corte.
- Log da Sony (S-Log2 / S-Log3, lido do XML do vídeo de origem): `../cor/log_709.py --auto` gera a
  LUT de entrada do corte (modo neutro: o tratamento do Ruan medido, branco neutralizado, exposição
  pela pele; `--sabor` troca pela LUT oficial da Sony) e
  ela entra no Lumetri de cada trecho, na placa de vídeo. --sem-log desliga.
- Celular em HDR (HLG, o padrão do iPhone; vídeo principal e B-roll): `../cor/hlg_709.py` gera a LUT
  que refaz o jeito que o celular mostra o vídeo numa tela comum; o clipe é lido como Rec.709
  (`clip.interpretFootage`), pro FilmCraft não converter o HLG antes, e a LUT entra no Lumetri.
  Sem isso o editor clareia a imagem e estoura as paredes. --sem-celular desliga.
- --cor: Lumetri leve (exposição, contraste, saturação, altas luzes, sombras); em log fica de fora
  salvo se pedido, porque a conversão já entrega a imagem pronta.
- A legenda vem dos <title> do FCPXML (o `.srt` só se o corte não tiver) e sai gravada na imagem.
- --legenda-viva LEGENDA.mov: em vez da legenda fixa, a legenda animada pronta (HyperFrames,
  `~/motion-ysquad/receitas/legenda_viva.py`), conferida como as cenas de motion
  (transparência e tamanho do vídeo) e posta a 100 % na trilha de cima, do início do corte.
- efeitos.json na pasta do corte (opcional), escrito por quem leu a fala, com índices de palavra
  do `indice.py` (inclusivos):
    {"zoom": [{"de": 16, "ate": 18, "escala": 115, "entrada": "seco|suave"}],
     "desfoque": [{"de": 56, "ate": 58, "forca": 40, "sentido": "abre|fecha"}],
     "broll": [{"de": 61, "ate": 64, "arquivo": "/caminho/trecho.mp4", "inicio": 0.0, "zoom": 108}],
     "motion": [{"de": 12, "ate": 18, "arquivo": "/caminho/cena.mov", "antes": 0.1, "saida": 0.4, "modo": "metade", "inicio": 0.0}],
     "sobrepor": [{"de": 30, "ate": 31, "arquivo": "/caminho/filmburn.mp4", "inicio": 0.0, "antes": 0.1, "opacidade": 100}],
     "som": [{"em": 12, "arquivo": "/caminho/whoosh.wav", "db": -8, "antes": 0.15}]}
  zoom = efeito Transform centrado no rosto, por cima do enquadramento: "seco" corta pra escala
  na primeira palavra e volta no fim da última; "suave" aproxima devagar até o fim e corta de volta.
  desfoque = Gaussian Blur: "abre" vai da força a zero (foco que chega), "fecha" de zero à força.
  broll = o trecho aprovado (pela get-brolls) cobre a fala da primeira à última palavra, numa
  trilha acima do vídeo, sem som, preenchendo o quadro; "zoom" aproxima devagar até a escala dada.
  motion = cena de motion pronta do Nolan (`~/motion-ysquad/FILMCRAFT.md`): criada no HyperFrames ou
  no Remotion, ou no EffectCraft quando depende da filmagem (rastreio, recorte, efeito na imagem).
  ProRes 4444 com transparência, já no tamanho do vídeo final e no lugar. A receita não cria nem
  posiciona motion: só confere arquivo, transparência e tamanho (diferente do vídeo: para, sem
  encaixar nem redimensionar) e põe a cena a 100 %, sem som, de `antes` segundos antes da primeira
  palavra (0 a 0,1) até `saida` segundos depois da última; `inicio` atrasa a entrada e pula os
  mesmos segundos do arquivo (a cena entra mais tarde e continua em sincronia; o rosto fica até lá). Cenas em sequência numa trilha; uma que
  se sobrepõe abre outra. "modo": "metade" (só no 9x16) é montagem: durante a cena o rosto desce pra
  metade de baixo (Transform e Crop no vídeo, quadros-chave hold) e a cena ocupa a de cima.
  sobrepor = film burn, overlay ou transição do acervo de FX do Ruan (`~/motion-ysquad/acervo-fx/acervo.json`):
  fundo preto, sem transparência, entra em modo de mistura Tela (o preto some, a luz fica), preenchendo o
  quadro, sem som, de `antes` segundos antes da palavra `de`; sem `ate` dura o próprio arquivo (a partir de
  `inicio`), com `ate` vai até o fim da palavra. Uma trilha, abre outra se encostar.
  som = som de efeito do acervo, com o tempo do próprio arquivo, começando `antes` segundos antes da
  palavra `em` (whoosh chega antes do corte), `db` de ganho (padrão -8), em trilhas de áudio próprias.
  Camadas, de baixo pra cima: vídeo, B-roll, motion, sobrepor, legenda viva.
- Voz (padrão, --sem-voz desliga): Essential Sound de diálogo com limpeza leve (ruído, sala,
  graves de manuseio, compressor, EQ "Balanced Voice"). --musica entra na A2 como música, abaixando
  sozinha sob a fala (ducking); sem --musica a receita para (vídeo do Naruto saiu mudo assim, 21/10):
  vídeo sem trilha só com --sem-musica, pedido de propósito. A trilha também vem do efeitos.json
  ("musica": caminho, ou "sem"), escrita pelo plano do Nolan. A exportação normaliza o volume pra --lufs (-14, Instagram e YouTube).
- Exporta H.264 com o chip de vídeo do Mac (`hardwareEncoding: auto`), compondo na placa de vídeo
  (`gpuRendering: auto`; o que ela não faz cai sozinho no processador).
"""
import argparse, glob, json, os, re, subprocess, sys, time, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import corte as cortefala  # noqa: E402
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


def duracao_media(caminho):
    """Duração do arquivo em segundos (ffprobe)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", caminho], capture_output=True, text=True)
    return float(r.stdout.strip())


def trechos_da_fonte(clipes):
    """Os intervalos do vídeo de origem que o corte usa, em segundos (`a-b,c-d`)."""
    return ",".join(f"{c['sourceIn'] / TPS:.2f}-{c['sourceOut'] / TPS:.2f}" for c in clipes)


def focos_do_rosto(video, cli, trechos=None):
    """focusKeys no tempo da FONTE (o clipe inteiro numa sequência que começa nele)."""
    extra = ["--trechos", trechos] if trechos else []
    out = subprocess.run([sys.executable, "-I", os.path.join(AQUI, "..", "rosto", "acompanhar.py"), video, "--cli", cli, *extra],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def converter_log(video, corte, sabor, trechos=None):
    """A LUT de entrada do log da Sony (None se o vídeo não é log): gerada uma vez por corte e sabor."""
    cor = os.path.join(AQUI, "..", "cor", "log_709.py")
    d = json.loads(subprocess.run([sys.executable, "-I", cor, "--detectar", video], capture_output=True, text=True, check=True).stdout)
    if not d.get("curva"):
        return None
    cube = os.path.join(corte, f"log_709_{sabor or 'neutro'}.cube")
    if not os.path.exists(cube):
        extra = ["--intervalos", trechos] if trechos else []
        modo = ["--modo", "sony", "--sabor", sabor] if sabor else ["--modo", "neutro"]
        r = subprocess.run([sys.executable, "-I", cor, cube, "--auto", video, *modo, *extra], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"conversão do log falhou: {r.stderr[-1500:]}")
        print(f"log: {r.stdout.strip()}", file=sys.stderr)
    return cube


def converter_celular(m, video, item, clipes, pasta):
    """Celular em HLG: o clipe lido como Rec.709 e a LUT do `hlg_709.py` no Lumetri. True se converteu."""
    cor = os.path.join(AQUI, "..", "cor", "hlg_709.py")
    d = json.loads(subprocess.run([sys.executable, "-I", cor, "--detectar", video], capture_output=True, text=True, check=True).stdout)
    if not d.get("hlg"):
        return False
    cube = os.path.join(pasta, "hlg_709.cube")
    if not os.path.exists(cube):
        subprocess.run([sys.executable, "-I", cor, cube], capture_output=True, text=True, check=True)
    m.run("clip.interpretFootage", {"items": [item], "colorSpace": "rec709"})
    for cid in clipes:
        m.run("effects.apply", {"clips": [cid], "effect": "Lumetri Color"})
        m.run("lumetri.setInputLut", {"clip": cid, "path": cube})
    print(f"celular: {os.path.basename(video)} em HLG, convertido como o celular mostra", file=sys.stderr)
    return True


def formato_da_fonte(fcpxml):
    m = re.search(r'<format [^>]*width="(\d+)" height="(\d+)"', open(fcpxml, encoding="utf-8").read())
    return (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)


def cena_pronta(e, quadro):
    """Confere a cena pronta: existe, tem transparência (ProRes 4444) e o tamanho do vídeo."""
    arq = e.get("arquivo", "")
    if not os.path.isfile(arq):
        sys.exit(f"cena {arq or e}: arquivo não existe")
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,profile,pix_fmt,width,height",
                        "-of", "json", arq], capture_output=True, text=True)
    v = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    if v.get("codec_name") != "prores" or "4444" not in str(v.get("profile", "")) or not str(v.get("pix_fmt", "")).startswith("yuva"):
        sys.exit(f"cena {arq} não tem transparência (é {v.get('codec_name')} {v.get('profile')} {v.get('pix_fmt')}): "
                 "exporte em ProRes 4444 com alfa")
    if (v.get("width"), v.get("height")) != quadro:
        sys.exit(f"cena {arq} tem {v.get('width')}x{v.get('height')}, o vídeo é {quadro[0]}x{quadro[1]}: refaça a cena")
    return os.path.abspath(arq)


def parados(zooms, cortes, fim, limite=7.5):
    """Faixas [a, b] do vídeo com mais de `limite` segundos sem mudança de quadro. Conta como mudança
    cada movimento de câmera (o "vai" da emenda não: a mudança é o corte), cada corte (o seco também) e o fim."""
    marcas = sorted([0.0] + [t for t, z in zooms if " vai " not in z] + list(cortes) + [fim])
    return [(a, b) for a, b in zip(marcas, marcas[1:]) if b - a > limite]


def aplicar_efeitos(m, corte, xml, clipes, focos, quadro, celular=True, zoom_cortes=0.0):
    """Aplica o efeitos.json do corte nos clipes da V1. Tempo do corte -> tempo da mídia de cada clipe.
    zoom_cortes: trecho sim, trecho não nessa escala (centrado no rosto), pra o corte seco virar ritmo."""
    caminho = os.path.join(corte, "efeitos.json")
    if not os.path.exists(caminho) and not zoom_cortes:
        return
    plano = json.load(open(caminho, encoding="utf-8")) if os.path.exists(caminho) else {}
    _, trechos = cortefala.frases_do_corte(xml)
    pal = cortefala.palavras_indexadas(os.path.join(corte, "transcript.json"), trechos)
    fw, fh = formato_da_fonte(xml)
    um_quadro = TPS // 25

    def faixa(e):
        if e["de"] not in pal or e["ate"] not in pal:
            sys.exit(f"efeito {e}: palavra fora do corte")
        return float(pal[e["de"]][0]), float(pal[e["ate"]][1])

    # as cenas de motion são conferidas antes de mexer em qualquer coisa
    cenas = []
    for e in plano.get("motion", []):
        t0, t1 = faixa(e)
        antes, saida, modo = float(e.get("antes", 0.0)), float(e.get("saida", 0.0)), e.get("modo")
        if not 0.0 <= antes <= 0.1:
            sys.exit(f"motion {e}: antes vai de 0 a 0,1 s")
        if saida < 0:
            sys.exit(f"motion {e}: saida não pode ser negativa")
        if modo not in (None, "metade"):
            sys.exit(f"motion {e}: o único modo é metade (a cena não se mexe; metade mexe no vídeo do rosto)")
        if modo == "metade" and quadro[1] <= quadro[0]:
            sys.exit(f"motion {e}: o modo metade é do 9x16")
        inicio = float(e.get("inicio", 0.0))
        if inicio < 0 or max(t0 - antes, 0.0) + inicio >= t1 + saida:
            sys.exit(f"motion {e}: inicio fora da cena")
        cenas.append((max(t0 - antes, 0.0) + inicio, t1 + saida, modo, cena_pronta(e, quadro), inicio))

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

    com_transform, com_blur, metade = {}, set(), {}  # metade: clipe -> [[a, b, base]] no tempo de mídia

    def transform_no_rosto(c, base):
        """Transform centrado no rosto (âncora e posição no mesmo ponto: não move nada sozinho)."""
        cid = c["clip"]
        if cid not in com_transform:
            m.run("effects.apply", {"clips": [cid], "effect": "Transform"})
            src = c["sourceIn"] / TPS
            perto = min(focos, key=lambda k: abs(k["seconds"] - src)) if focos else {"focus": [0.5, 0.4]}
            ponto = [perto["focus"][0] * fw, perto["focus"][1] * fh]
            for prm in ("anchor", "position"):
                m.run("effects.setParam", {"clip": cid, "effect": "transform", "param": prm, "value": ponto})
            kf(cid, "transform", "scale_height", base, 100.0, "hold")
            com_transform[cid] = ponto
        return com_transform[cid]

    repouso = {}  # escala de cada clipe fora do zoom do plano (100, ou a do zoom alternado)
    if zoom_cortes:
        for k, c in enumerate(clipes):
            if k % 2:
                transform_no_rosto(c, c["sourceIn"])
                kf(c["clip"], "transform", "scale_height", c["sourceIn"], float(zoom_cortes), "hold")
                repouso[c["clip"]] = float(zoom_cortes)
    # câmera do plano (Cam Zoom do Rick Miura, ~/Downloads/Cam Zoom 3 Predef.prfpset): quem lê o roteiro
    # escolhe onde, em segundos do corte. Curva bezier e obturador a 360°; o repouso de cada clipe anda junto.
    #   soco  = "Vai e volta": chega ao `pico` (138 no preset; plano pode trocar) em cima da palavra (`em`), segura até `ate`, assenta em `depois` (100 <-> 105)
    #           ("solta": false segura até a emenda)
    #   passo = aproxima até `escala` em `dur` (0,534 s, o "Vai") e fica: enumeração, crescendo, fim
    #   emendas = números das emendas (J1 = 1ª) com "Vai" no fim do trecho (-> pico) e "Volta" no seguinte (pico -> 100)
    zooms = []  # [segundos na linha do tempo, o que acontece]: vira marcador e zooms.json (motion não cai em cima)
    camera, emendas = plano.get("camera", []), set(plano.get("emendas", []))
    pico = float(plano.get("pico", 138.0))
    if camera or emendas:
        eventos = sorted([(float(e["em"]) - (0.3 if e["tipo"] == "soco" else 0.2), e) for e in camera], key=lambda x: x[0])
        for k, c in enumerate(clipes):
            cid, ini, fim = c["clip"], c["sourceIn"], c["sourceOut"]
            t_ini = c["start"] / TPS
            t_fim = t_ini + (fim - ini) / TPS
            midia = lambda t: ini + round((t - t_ini) * TPS)
            transform_no_rosto(c, ini)
            m.run("effects.setParam", {"clip": cid, "effect": "transform", "param": "shutter_override", "value": True})
            m.run("effects.setParam", {"clip": cid, "effect": "transform", "param": "shutter_angle", "value": 360.0})
            nivel, livre = 100.0, t_ini
            if k in emendas:  # Volta: o trecho chega no pico, onde o anterior parou, e abre até 100
                kf(cid, "transform", "scale_height", ini, pico, "bezier")
                kf(cid, "transform", "scale_height", midia(t_ini + 1.084), 100.0, "hold")
                zooms.append([round(t_ini, 3), f"J{k}: volta {pico:g} -> 100"])
                livre = t_ini + 1.084
            for t0, e in eventos:
                if not t_ini <= float(e["em"]) < t_fim:
                    continue
                if t0 < livre - 1e-3:
                    sys.exit(f"câmera {e}: começa em {t0:.2f} s, mas o movimento anterior vai até {livre:.2f} s")
                if e["tipo"] == "soco":
                    ate = max(float(e.get("ate", e["em"])), t0 + 1.376)
                    novo = float(e.get("depois", 105.0 if nivel == 100.0 else 100.0))
                    passos = [(t0, nivel, "bezier"), (t0 + 0.5, pico, "bezier"), (ate, pico, "bezier" if e.get("solta", True) else "hold")]
                    if e.get("solta", True):
                        passos.append((ate + 0.626, novo, "hold"))
                    else:
                        novo = pico
                    descricao = f"soco {nivel:g} -> {pico:g} -> {novo:g} em \"{e.get('fala', '')}\""
                elif e["tipo"] == "passo":
                    novo = float(e["escala"])
                    passos = [(t0, nivel, "bezier"), (t0 + float(e.get("dur", 0.534)), novo, "hold")]
                    descricao = f"passo {nivel:g} -> {novo:g} em \"{e.get('fala', '')}\""
                else:
                    sys.exit(f"câmera {e}: tipo é soco ou passo")
                if passos[-1][0] > t_fim + 1e-3 or (k + 1 in emendas and passos[-1][0] > t_fim - 0.534):
                    sys.exit(f"câmera {e}: termina em {passos[-1][0]:.2f} s, depois do fim do trecho ou do Vai da emenda")
                for t, v, curva in passos:
                    kf(cid, "transform", "scale_height", midia(t), v, curva)
                zooms.append([round(float(e["em"]), 3), descricao])
                nivel, livre = novo, passos[-1][0]
            if k + 1 in emendas:  # Vai: aproxima até a emenda
                kf(cid, "transform", "scale_height", fim - round(0.534 * TPS), nivel, "bezier")
                kf(cid, "transform", "scale_height", fim, pico, "hold")
                zooms.append([round(t_fim - 0.534, 3), f"J{k + 1}: vai {nivel:g} -> {pico:g} até o corte"])
        zooms.sort()
        fim_seq = (clipes[-1]["start"] + clipes[-1]["sourceOut"] - clipes[-1]["sourceIn"]) / TPS
        longos = [f"{a:.1f}-{b:.1f}" for a, b in parados(zooms, [c["start"] / TPS for c in clipes[1:]], fim_seq)]
        print(f"câmera: {len(zooms)} movimentos" + (f" · mais de 7,5 s parado em {', '.join(longos)}" if longos else ""), file=sys.stderr)
    for z in plano.get("zoom", []):
        t0, t1 = faixa(z)
        for c, a, b, base in pedacos(t0, t1):
            cid = c["clip"]
            transform_no_rosto(c, base)
            s = float(z.get("escala", 115))
            if z.get("entrada", "seco") == "suave":
                kf(cid, "transform", "scale_height", a, repouso.get(cid, 100.0), "easeOut")
                kf(cid, "transform", "scale_height", b, s, "hold")
            else:
                kf(cid, "transform", "scale_height", a, s, "hold")
            kf(cid, "transform", "scale_height", b + um_quadro, repouso.get(cid, 100.0), "hold")
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
        if celular:
            converter_celular(m, os.path.abspath(r["arquivo"]), item, [bc], corte)
        if r.get("zoom"):
            # o clipe como ficou (o encaixe arredonda pro quadro)
            c = next(x for tr in m.run("sequence.inspect")["video"] for x in tr["items"] if x["clip"] == bc)
            por_id[bc] = c
            m.run("effects.apply", {"clips": [bc], "effect": "Transform"})
            kf(bc, "transform", "scale_height", c["sourceIn"], 100.0, "linear")
            kf(bc, "transform", "scale_height", c["sourceOut"], float(r["zoom"]), "hold")
    trilhas_motion = []  # [nome, fim da última cena]
    for t0, t1, modo, arquivo, inicio in sorted(cenas, key=lambda x: (x[0], x[1])):
        # a cena chega pronta: a 100 %, no centro do quadro, sem encaixe nem posição
        livre = next((tr for tr in trilhas_motion if tr[1] <= t0 + 1e-6), None)
        item = m.run("file.import", {"paths": [arquivo]})["items"][0]
        m.run("timeline.place", {"item": item, "track": livre[0] if livre else "new", "time": round(t0 * TPS),
                                 "sourceIn": round(inicio * TPS), "duration": round((t1 - t0) * TPS), "audio": False})
        if livre:
            livre[1] = t1
        else:
            trilhas_motion.append([f"V{len(m.run('sequence.inspect')['video'])}", t1])
        if modo == "metade":
            for c, a, b, base in pedacos(t0, t1):
                metade.setdefault(c["clip"], []).append([a, b, base])
    # montagem, não motion: o rosto (âncora do Transform) desce pra 3/4 da altura e a metade de cima do
    # vídeo é cortada; a cena ocupa a metade de cima. Só durante a cena: quadros-chave hold. Cenas metade
    # encostadas no mesmo clipe viram uma faixa só: o rosto devolvido no fim de uma (em b, o 1º quadro
    # depois dela) cairia no quadro que o desce na seguinte. Devolver em b + 1 deixava um quadro preto.
    for cid, faixas in metade.items():
        juntas = []
        for a, b, base in sorted(faixas):
            if juntas and a <= juntas[-1][1] + um_quadro:
                juntas[-1][1] = max(juntas[-1][1], b)
            else:
                juntas.append([a, b, base])
        ponto = transform_no_rosto(por_id[cid], juntas[0][2])
        kf(cid, "transform", "position", juntas[0][2], ponto, "hold")
        m.run("effects.apply", {"clips": [cid], "effect": "Crop"})
        kf(cid, "crop", "top", juntas[0][2], 0.0, "hold")
        for a, b, _ in juntas:
            kf(cid, "transform", "position", a, [ponto[0], 0.75 * fh], "hold")
            kf(cid, "transform", "position", b, ponto, "hold")
            kf(cid, "crop", "top", a, 50.0, "hold")
            kf(cid, "crop", "top", b, 0.0, "hold")
    trilhas_sob = []  # [nome, fim do último]
    for e in plano.get("sobrepor", []):
        if e["de"] not in pal or ("ate" in e and e["ate"] not in pal):
            sys.exit(f"sobrepor {e}: palavra fora do corte")
        if not os.path.exists(e["arquivo"]):
            sys.exit(f"sobrepor {e}: arquivo não existe")
        t0 = max(float(pal[e["de"]][0]) - float(e.get("antes", 0.0)), 0.0)
        ini = float(e.get("inicio", 0.0))
        dur = (float(pal[e["ate"]][1]) - t0) if "ate" in e else duracao_media(e["arquivo"]) - ini
        livre = next((tr for tr in trilhas_sob if tr[1] <= t0 + 1e-6), None)
        item = m.run("file.import", {"paths": [os.path.abspath(e["arquivo"])]})["items"][0]
        sc = m.run("timeline.place", {"item": item, "track": livre[0] if livre else "new", "time": round(t0 * TPS),
                                      "sourceIn": round(ini * TPS), "duration": round(dur * TPS), "audio": False})["clips"][0]
        if livre:
            livre[1] = t0 + dur
        else:
            trilhas_sob.append([f"V{len(m.run('sequence.inspect')['video'])}", t0 + dur])
        m.run("clip.fillFrame", {"clips": [sc]})
        m.run("effects.setParam", {"clip": sc, "effect": "opacity", "param": "blend", "value": "Screen"})
        if float(e.get("opacidade", 100)) != 100:
            m.run("effects.setParam", {"clip": sc, "effect": "opacity", "param": "opacity", "value": float(e["opacidade"])})
    trilhas_som = []  # [nome, fim do último]
    for e in sorted(plano.get("som", []), key=lambda e: e["em"]):
        if e["em"] not in pal:
            sys.exit(f"som {e}: palavra fora do corte")
        if not os.path.exists(e["arquivo"]):
            sys.exit(f"som {e}: arquivo não existe")
        t0 = max(float(pal[e["em"]][0]) - float(e.get("antes", 0.0)), 0.0)
        t1 = t0 + duracao_media(e["arquivo"])
        livre = next((tr for tr in trilhas_som if tr[1] <= t0 + 1e-6), None)
        item = m.run("file.import", {"paths": [os.path.abspath(e["arquivo"])]})["items"][0]
        sc = m.run("timeline.place", {"item": item, "audioTrack": livre[0] if livre else "new", "time": round(t0 * TPS), "video": False})["clips"]
        if livre:
            livre[1] = t1
        else:
            trilhas_som.append([f"A{len(m.run('sequence.inspect')['audio'])}", t1])
        m.run("essentialSound.setType", {"clips": sc, "type": "sfx"})
        m.run("essentialSound.set", {"clips": sc, "values": {"volume.on": True, "volume.level_db": float(e.get("db", -8.0))}})
    print(f"efeitos: {len(plano.get('zoom', []))} zoom, {len(plano.get('desfoque', []))} desfoque, "
          f"{len(plano.get('broll', []))} B-roll, {len(cenas)} motion em {len(trilhas_motion)} trilha(s), "
          f"{len(plano.get('sobrepor', []))} sobreposição(ões), {len(plano.get('som', []))} som(ns)", file=sys.stderr)
    return zooms


def main():
    a = argparse.ArgumentParser()
    a.add_argument("corte")
    a.add_argument("saida")
    a.add_argument("--formato", choices=TAMANHOS, default="9x16")
    a.add_argument("--cor", action="store_true")
    a.add_argument("--sem-legenda", action="store_true")
    a.add_argument("--legenda-viva", metavar="LEGENDA.mov", help="a legenda animada pronta (HyperFrames, ~/motion-ysquad/receitas/legenda_viva.py)")
    a.add_argument("--musica")
    a.add_argument("--sem-musica", action="store_true", help="vídeo sem trilha, de propósito; sem isso, --musica é obrigatória")
    a.add_argument("--musica-abaixa", type=float, default=-4.5,
                   help="quanto a música desce sob a fala (dB); -4,5 põe a trilha ~15 dB abaixo da voz, medido num reel de referência do Ruan (o -12 antigo deixava ~22, baixa demais)")
    a.add_argument("--musica-db", type=float, default=-18.0, help="nível da música sem fala")
    a.add_argument("--sem-voz", action="store_true")
    a.add_argument("--sabor", help="converter o log pela LUT oficial da Sony (LC-709, LC-709TypeA...) em vez do modo neutro")
    a.add_argument("--sem-log", action="store_true")
    a.add_argument("--sem-celular", action="store_true", help="não converter vídeo de celular em HLG")
    a.add_argument("--lufs", type=float, default=-14.0)
    a.add_argument("--legenda-tamanho", type=float, default=72.0, help="16x9/4x3, px por 1080 linhas")
    a.add_argument("--zoom-cortes", type=float, default=0.0, metavar="ESCALA", help="trecho sim, trecho não nessa escala (ex.: 108), centrado no rosto")
    a.add_argument("--microfade", type=int, default=0, metavar="QUADROS", help="fade de áudio de N quadros na entrada e na saída de cada trecho (ex.: 1)")
    a.add_argument("--igualar-voz", action="store_true", help="cada trecho de fala no mesmo volume (essentialSound.autoMatch)")
    a.add_argument("--revisao", action="store_true", help="marcador em cada emenda e projeto .fcproj salvo ao lado do MP4 (revisão da decupagem no app)")
    a.add_argument("--cli", default=os.path.join(AQUI, "..", "..", "target", "release", "filmcraft-cli"))
    o = a.parse_args()
    if not o.musica and not o.sem_musica:  # a trilha do plano (plano_efeitos.py escreve "musica" no efeitos.json)
        try:
            dita = json.load(open(os.path.join(o.corte, "efeitos.json"), encoding="utf-8")).get("musica")
        except (OSError, ValueError):
            dita = None
        if dita == "sem":
            o.sem_musica = True
        elif dita:
            o.musica = dita if os.path.isabs(dita) else os.path.join(o.corte, dita)
    if not o.musica and not o.sem_musica:
        a.error("falta a trilha: --musica TRILHA, \"musica\" no efeitos.json (linha Música: do plano) ou --sem-musica, se o vídeo é sem música de propósito")
    if o.musica and not os.path.isfile(o.musica):
        a.error(f"trilha não encontrada: {o.musica}")
    cli = os.path.abspath(o.cli)
    xml = glob.glob(os.path.join(o.corte, "*.fcpxml"))
    if len(xml) != 1:
        sys.exit(f"esperava um .fcpxml em {o.corte}, achei {len(xml)}")
    w, h = TAMANHOS[o.formato]
    viva = cena_pronta({"arquivo": o.legenda_viva}, (w, h)) if o.legenda_viva and not o.sem_legenda else None

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
    focos = focos_do_rosto(video_do_fcpxml(xml[0]), cli, trechos_da_fonte(clipes)) if (h <= w or tem_efeitos) else []
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

    zooms = aplicar_efeitos(m, o.corte, xml[0], clipes, focos, (w, h), not o.sem_celular, o.zoom_cortes) or []
    if zooms:  # onde a câmera mexe: a edição seguinte (tela dividida, motion) não cai em cima
        json.dump([{"segundos": t, "zoom": z} for t, z in zooms], open(os.path.abspath(o.saida) + ".zooms.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"zooms: {len(zooms)} · {os.path.abspath(o.saida)}.zooms.json", file=sys.stderr)
    ids = [c["clip"] for c in clipes]
    cube = None if o.sem_log else converter_log(video_do_fcpxml(xml[0]), o.corte, o.sabor, trechos_da_fonte(clipes))
    hlg = not cube and not o.sem_celular and converter_celular(m, video_do_fcpxml(xml[0]), clipes[0]["item"], ids, o.corte)
    if cube:
        for cid in ids:
            m.run("effects.apply", {"clips": [cid], "effect": "Lumetri Color"})
            m.run("lumetri.setInputLut", {"clip": cid, "path": cube})
    if o.cor:
        if not (cube or hlg):  # em log e no celular o Lumetri da conversão já está no clipe
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
    falas = [c["clip"] for c in seq["audio"][0]["items"]]
    if not o.sem_voz:
        m.run("essentialSound.setType", {"clips": falas, "type": "dialogue"})
        m.run("essentialSound.set", {"clips": falas, "values": VOZ})
    if o.igualar_voz:  # tomadas gravadas com energia diferente: cada trecho no mesmo volume
        m.run("essentialSound.autoMatch", {"clips": falas})
    if o.microfade:
        # fade de um lado só na entrada e na saída de cada trecho: o cruzado puxa áudio de fora da borda
        # (rabo de contagem); 1 quadro tira o estalo sem comer a voz, que começa ~0,08 s depois do corte
        for cid in falas:
            for lado in ("in", "out"):
                m.run("sequence.applyAudioTransition", {"clip": cid, "effect": "constant_power", "frames": o.microfade, "edge": lado})
    if o.musica:
        item = m.run("file.import", {"paths": [os.path.abspath(o.musica)]})["items"][0]
        dur = round(seq["duration"])
        mus = m.run("timeline.place", {"item": item, "audioTrack": "new", "time": 0, "duration": dur, "video": False})["clips"]
        m.run("essentialSound.setType", {"clips": mus, "type": "music"})
        m.run("essentialSound.set", {"clips": mus, "values": {"volume.on": True, "volume.level_db": o.musica_db, "ducking.enabled": True,
                                                              "ducking.reduce_db": o.musica_abaixa, "ducking.fade_s": 0.4,
                                                              # com --sem-voz a fala fica sem tipo: a música abaixa sob ela
                                                              # também (o resto que tem som, efeito, já é tipado)
                                                              "ducking.againstUntyped": True}})
        duck = m.run("essentialSound.generateDucking", {"clips": mus})
        print(f"música: ducking {json.dumps(duck)[:200]}", file=sys.stderr)

    if viva:
        # pronta (HyperFrames): a 100 %, sem som, na trilha de cima
        item = m.run("file.import", {"paths": [viva]})["items"][0]
        m.run("timeline.place", {"item": item, "track": "new", "seconds": 0.0, "audio": False})

    if o.revisao:
        # revisão da decupagem no app (25/10/2026): um marcador por emenda, com a fala dos dois lados, e o
        # projeto salvo ao lado do MP4; o Ruan pula de emenda em emenda em vez de assistir tudo
        palavras = []
        try:
            palavras = json.load(open(os.path.join(o.corte, "transcript.json"), encoding="utf-8"))
        except (OSError, ValueError):
            pass

        def fala(a, b):
            return " ".join(p["text"] for p in palavras if p["end"] > a and p["start"] < b)

        for k, c in enumerate(clipes[1:], 1):
            ant = clipes[k - 1]
            nome = f"J{k}: …{fala(ant['sourceOut'] / TPS - 1.5, ant['sourceOut'] / TPS)[-40:]} | {fala(c['sourceIn'] / TPS, c['sourceIn'] / TPS + 1.5)[:40]}…"
            m.run("markers.add", {"seconds": round(c["start"] / TPS, 3), "name": nome})
        for t, z in zooms:
            m.run("markers.add", {"seconds": t, "name": f"Z: {z}"})
        projeto = os.path.abspath(o.saida) + ".fcproj"
        m.run("file.saveAs", {"path": projeto})
        print(f"revisão: {len(clipes) - 1} emendas marcadas · projeto {projeto}", file=sys.stderr)

    t = time.time()
    r = m.run("file.exportMedia", {"path": os.path.abspath(o.saida) + ".mp4", "format": "h264", "hardwareEncoding": "auto", "gpuRendering": "auto",
                                  "width": w, "height": h, "burnCaptions": not o.sem_legenda and not viva,
                                  "loudnessLufs": o.lufs, "wait": True})
    m.fechar()
    print(f"exportado em {time.time() - t:.1f} s: {json.dumps(r.get('result', r))}")

if __name__ == "__main__":
    main()
