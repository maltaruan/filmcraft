# ysquad/

Ferramentas do nosso fork que ficam fora do produto (o editor continua em Rust puro). Meta: editor
sólido pro uso da ySquad (reel, depois vídeo longo, ligado ao motion), não paridade com o Premiere.

- `receitas/montar_video.py PASTA_DO_CORTE SAIDA`: do corte da skill `cortar-fala` ao vídeo final,
  pelo FilmCraft sem janela, exportando pela placa de vídeo e pelo chip de vídeo do Mac. Formato
  9x16, 16x9 ou 4x3 (horizontal com o foco no rosto); legenda fixa ou `--legenda-viva ESTILO`
  (caixa, acende, pop, acumula, limpa; `--amostras-legenda PASTA` pra escolher); `efeitos.json` no
  corte (zoom no rosto, desfoque, B-roll, por índice de palavra); `--motion clipe.mov`; voz limpa,
  `--musica` com ducking e -14 LUFS; log da Sony convertido sozinho (ver `cor/`).
- `receitas/legenda_viva.py`: a camada de legenda animada (HyperFrames, ProRes 4444 com alfa).
- `cor/log_709.py`: S-Log2/S-Log3 da Sony para Rec.709 como LUT de entrada. Modo `neutro`
  (padrão): o tratamento à mão do Ruan medido (branco neutralizado, curva e saturação dele),
  exposição pela pele; modo `sony`: LUT oficial.
- `rosto/acompanhar.py VIDEO [--trechos a-b,...]`: `focusKeys` de `clip.fillFrame` acompanhando o
  rosto (Vision do macOS, `rosto/rosto.swift`).
- MCP registrado no escopo do usuário: `filmcraft-headless` (sem janela, `--demo`) e `filmcraft`
  (ponte pro app aberto, porta 9876).

## Estado (16/10/2026)

Pronto: reel completo por receita; cor do Lumetri inteira na placa (curvas, rodas, HSL, looks e
LUT de entrada como tabela 3D); CLI com Metal; conversão neutra do log validada a 3,7 níveis do
tratamento do Ruan no C0204.

Alvo de pele do modo neutro: 110 (17/10), média de dois vídeos tratados pelo Ruan (`discord.mov`
100, `naruto 2.mov` 123, cenas de mesmo brilho). A curva e a saturação continuam medidas só no par
discord/C0204: o bruto do naruto não está no disco.

Pendente: vídeo de celular. Legenda viva lenta (~24 s). Motion por cena
no `efeitos.json`. B-roll real e música testados só com material sintético.

Riscos: a escala de entrada das LUTs da Sony (código cheio x faixa de vídeo) não foi confirmada com
cartão cinza (afeta ~3% dos tons médios no modo `sony`). Push pelo SSH só via
`git@github.com:maltaruan/filmcraft.git`.
