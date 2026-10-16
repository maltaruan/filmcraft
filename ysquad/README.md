# ysquad/

Ferramentas do nosso fork que ficam fora do produto (o editor continua em Rust puro).

- `rosto/acompanhar.py VIDEO`: gera os `focusKeys` de `clip.fillFrame` acompanhando o rosto,
  com o detector de rosto do macOS (`rosto/rosto.swift`, Vision, local). Uso típico: vídeo vertical
  da câmera recortado para 16:9 ou 4:3 sem cortar a cabeça.
