# ysquad/

Ferramentas do nosso fork que ficam fora do produto (o editor continua em Rust puro).

- `rosto/acompanhar.py VIDEO`: gera os `focusKeys` de `clip.fillFrame` acompanhando o rosto,
  com o detector de rosto do macOS (`rosto/rosto.swift`, Vision, local). Uso típico: vídeo vertical
  da câmera recortado para 16:9 ou 4:3 sem cortar a cabeça.
- `receitas/montar_video.py PASTA_DO_CORTE SAIDA`: do corte da skill `cortar-fala` (`.fcpxml` +
  `legenda.srt`) ao vídeo final, pelo FilmCraft sem janela: formato 9x16, 16x9 ou 4x3 (horizontal
  com o foco acompanhando o rosto), `--cor`, `--motion clipe.mov` (transparência, ex. HyperFrames
  `--format mov`) na V2, legenda gravada na imagem, exportação pelo chip de vídeo do Mac.
