"""Vídeo de celular em HDR (HLG, o padrão do iPhone) -> Rec.709 como o celular mostra.

O iPhone grava em HLG. O app de fotos, o QuickTime e o TikTok mostram esse vídeo numa tela comum
do jeito que a recomendação BT.2100 manda para uma tela de 100 cd/m²; os editores (FilmCraft,
Premiere, Resolve) o tratam como HDR de 1000 cd/m² e reduzem pra tela comum, e a cor muda
(no clipe de teste, 36 níveis mais claro na média e as paredes estouradas).

Esta LUT de entrada refaz o caminho da Apple, para cada cor da grade (o sinal do arquivo, 0 a 1):
  1. decodifica o HLG (BT.2100) pra luz de cena, na gama BT.2020;
  2. aplica o OOTF da BT.2100 para uma tela de 100 cd/m²: o pico do HLG vira o branco da tela,
     gama do sistema pela fórmula estendida da BT.2390, 1,2 × 1,111^log2(100/1000) ≈ 0,846;
  3. converte BT.2020 -> BT.709, corta o que sai da tela e codifica na curva sRGB.
Medido contra o AVFoundation (o motor de vídeo do macOS) no vídeo da câmera frontal: 0,67 nível
de erro médio. A receita lê o clipe como Rec.709 (`clip.interpretFootage`), para o FilmCraft não
converter o HLG antes, e põe a LUT no Lumetri como Input LUT, como a do log da Sony.

Uso:
    python3 -I hlg_709.py --detectar VIDEO.MOV     ({"hlg": true|false}, pelo ffprobe)
    python3 -I hlg_709.py SAIDA.cube [--n 65]
"""
import argparse, json, math, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from log_709 import escrever_cube  # noqa: E402

TELA_NITS = 100.0
GAMA_SISTEMA = 1.2 * 1.111 ** math.log2(TELA_NITS / 1000.0)
LUMA_2020 = (0.2627, 0.6780, 0.0593)
# BT.2020 -> BT.709, luz linear (BT.2087)
M_2020_709 = ((1.6605, -0.5876, -0.0728), (-0.1246, 1.1329, -0.0083), (-0.0182, -0.1006, 1.1187))
A, B, C = 0.17883277, 0.28466892, 0.55991073


def hlg_dec(e):
    """Inverso do OETF do HLG (BT.2100): sinal 0..1 -> luz de cena 0..1."""
    return e * e / 3.0 if e <= 0.5 else (math.exp((e - C) / A) + B) / 12.0


def srgb_enc(x):
    x = min(max(x, 0.0), 1.0)
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def conversao(s):
    e = [hlg_dec(min(max(v, 0.0), 1.0)) for v in s]
    ys = sum(l * v for l, v in zip(LUMA_2020, e))
    g = ys ** (GAMA_SISTEMA - 1.0) if ys > 0 else 0.0
    d = [v * g for v in e]
    return [srgb_enc(sum(m * v for m, v in zip(linha, d))) for linha in M_2020_709]


def detectar(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer",
                        "-of", "json", video], capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    return {"hlg": s.get("color_transfer") == "arib-std-b67"}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("saida", nargs="?")
    a.add_argument("--detectar", metavar="VIDEO")
    a.add_argument("--n", type=int, default=65)
    o = a.parse_args()
    if o.detectar:
        print(json.dumps(detectar(o.detectar)))
        return
    if not o.saida:
        a.error("informe SAIDA.cube ou --detectar VIDEO")
    escrever_cube(o.saida, conversao, o.n, f"HLG -> Rec.709 (tela de {TELA_NITS:.0f} cd/m2, gama {GAMA_SISTEMA:.3f})")
    print(f"{o.saida}: gama do sistema {GAMA_SISTEMA:.3f}")


if __name__ == "__main__":
    main()
