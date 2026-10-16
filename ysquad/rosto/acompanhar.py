"""Foco que acompanha o rosto: gera os `focusKeys` de `clip.fillFrame` para um vídeo.

Uso:
    python3 -I acompanhar.py VIDEO [--cada 2] [--cli CAMINHO_DO_filmcraft-cli]

Abre o vídeo no FilmCraft sem janela (MCP), tira um quadro inteiro a cada `--cada` segundos,
acha o maior rosto com o Vision do macOS (`rosto.swift`, compilado na primeira vez), suaviza
com a mediana de 3 vizinhos e imprime a lista em JSON, pronta para
`clip.fillFrame {"clips": [id], "focusKeys": [...]}` (segundos contados do início do clipe
numa sequência que começa nele). Quadros sem rosto ficam de fora.
"""
import argparse, base64, json, os, statistics, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))


def detector():
    exe = os.path.join(AQUI, "rosto")
    if not os.path.exists(exe):
        subprocess.run(["swiftc", "-O", os.path.join(AQUI, "rosto.swift"), "-o", exe], check=True)
    return exe


class Mcp:
    def __init__(self, cli):
        self.p = subprocess.Popen([cli, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "acompanhar", "version": "1"}})
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

    def frame(self, seconds, path):
        r = self.rpc("tools/call", {"name": "render_frame", "arguments": {"seconds": seconds, "max_side": 640}})
        img = [c for c in r.get("content", []) if c.get("type") == "image"]
        if img:
            with open(path, "wb") as f:
                f.write(base64.b64decode(img[0]["data"]))
            return True
        return False


def main():
    a = argparse.ArgumentParser()
    a.add_argument("video")
    a.add_argument("--cada", type=float, default=2.0)
    a.add_argument("--cli", default=os.path.join(AQUI, "..", "..", "target", "release", "filmcraft-cli"))
    o = a.parse_args()
    m = Mcp(o.cli)
    item = m.run("file.import", {"paths": [os.path.abspath(o.video)]})["items"][0]
    m.run("file.newSequenceFromClip", {"items": [item]})
    dur = m.run("sequence.inspect")["video"][0]["items"][0]["duration"] / 254_016_000_000
    tmp = tempfile.mkdtemp(prefix="rosto-")
    ts, t = [], 0.0
    while t < dur:
        ts.append(round(t, 3))
        t += max(o.cada, 0.2)
    feitos = [(t, os.path.join(tmp, f"{i:05d}.png")) for i, t in enumerate(ts)]
    feitos = [(t, p) for t, p in feitos if m.frame(t, p)]
    m.p.stdin.close()
    linhas = subprocess.run([detector(), *[p for _, p in feitos]], capture_output=True, text=True).stdout.splitlines()
    raw = {}
    for (t, _), linha in zip(feitos, linhas):
        f = linha.split("\t")
        if len(f) >= 4:
            raw[t] = (float(f[1]), float(f[2]))
    tt = sorted(raw)
    keys = []
    for i, t in enumerate(tt):
        win = [raw[x] for x in tt[max(0, i - 1):i + 2]]
        keys.append({"seconds": t, "focus": [round(statistics.median(v[0] for v in win), 4), round(statistics.median(v[1] for v in win), 4)]})
    print(f"rosto em {len(raw)} de {len(feitos)} quadros", file=sys.stderr)
    print(json.dumps(keys))


if __name__ == "__main__":
    main()
