# ysquad/

Ferramentas do nosso fork que ficam fora do produto (o editor continua em Rust puro). Meta: editor
sólido pro uso da ySquad (reel, depois vídeo longo), não paridade com o Premiere.

Divisão (17/10): o FilmCraft só monta (corte, cor, voz, música, B-roll, legenda fixa, exportação).
Criar, animar, posicionar e dimensionar motion é do Nolan (`~/motion-ysquad`): HyperFrames ou Remotion,
e o EffectCraft (`~/effectcraft`) só no que depende da filmagem (rastreio, recorte, efeito na imagem).
A cena chega pronta e a receita só a põe no tempo das palavras. O modo `metade` fica aqui: ele mexe no
vídeo do rosto, é montagem. O código do
produto (`crates/`, gráficos, modelos `.fcgt`) é do upstream e não é mexido aqui.

- `receitas/montar_video.py PASTA_DO_CORTE SAIDA`: do corte da skill `cortar-fala` ao vídeo final,
  pelo FilmCraft sem janela, exportando pela placa de vídeo e pelo chip de vídeo do Mac. Formato
  9x16, 16x9 ou 4x3 (horizontal com o foco no rosto); legenda fixa ou `--legenda-viva LEGENDA.mov`
  (pronta do HyperFrames, `~/motion-ysquad/receitas/legenda_viva.py`); `efeitos.json` no
  corte (zoom no rosto, desfoque, B-roll, cenas de motion prontas e o modo `metade`, por índice de
  palavra); voz limpa,
  `--musica` com ducking e -14 LUFS; log da Sony e vídeo de celular em HDR convertidos sozinhos
  (ver `cor/`).
- `receitas/corte.py`: o corte do `cortar-fala` no tempo do corte (frases, trechos e o tempo de cada
  palavra pelo índice do `indice.py`), usado pelos efeitos.
- `cor/log_709.py`: S-Log2/S-Log3 da Sony para Rec.709 como LUT de entrada. Modo `neutro`
  (padrão): o tratamento à mão do Ruan medido (branco neutralizado, calor, curva e saturação dele),
  exposição pela pele, com `--visual naruto` (padrão, quente) ou `discord`; modo `sony`: LUT oficial.
- `cor/hlg_709.py`: vídeo de celular em HDR (HLG, o padrão do iPhone) para Rec.709 como o celular
  mostra numa tela comum, como LUT de entrada; a receita lê o clipe como Rec.709 pro FilmCraft não
  converter o HLG antes. `--sem-celular` desliga.
- `rosto/acompanhar.py VIDEO [--trechos a-b,...]`: `focusKeys` de `clip.fillFrame` acompanhando o
  rosto (Vision do macOS, `rosto/rosto.swift`).
- MCP registrado no escopo do usuário: `filmcraft-headless` (sem janela, `--demo`) e `filmcraft`
  (ponte pro app aberto, porta 9876).

## Estado (16/10/2026)

Pronto: reel completo por receita; cor do Lumetri inteira na placa (curvas, rodas, HSL, looks e
LUT de entrada como tabela 3D); CLI com Metal; conversão neutra do log validada a 3,7 níveis do
tratamento do Ruan no C0204.

Cor (17/10): o padrão do Ruan é o `naruto 2.mov`, medido pixel a pixel sobre o bruto C0190
(`/Volumes/SSD /C0190.MP4`): 10 quadros alinhados, curva, calor (âmbar) e saturação dele. Tudo
automático (exposição e branco pela pele, 25 quadros) fica a 2,9 níveis do tratamento dele no C0190.
O visual do `discord.mov` (neutro, pele 100) fica como `--visual discord`.

Motion (17/10): chave `motion` do `efeitos.json` com cenas prontas (HyperFrames, Remotion ou
EffectCraft), ProRes 4444 com transparência no tamanho do vídeo final. A receita confere arquivo,
transparência e tamanho (se não bate, para e pede pra refazer a cena) e põe a cena a 100 %, sem
mexer, do `antes` ao `saida`. `"modo": "metade"` (9x16) desce o rosto pra metade de baixo durante a cena.
Camadas, de baixo pra cima: vídeo, B-roll, motion, legenda. Testado no `target/fixtures/corte_motion`:
a cena aparece no tempo das palavras, no pixel em que veio, com a legenda por cima (a fixa e a viva).

Legenda viva (17/10): saiu desta camada e mora em `~/motion-ysquad/receitas/legenda_viva.py` (HyperFrames). A receita recebe o `.mov` pronto em `--legenda-viva`,
confere como as cenas (transparência e tamanho) e põe a 100 % na trilha de cima.

Celular (17/10): o editor clareava o vídeo do iPhone (HDR) e estourava as paredes. A correção ficou
nesta camada, sem tocar no produto: `cor/hlg_709.py` refaz o jeito da Apple (tela de 100 cd/m²,
gama 0,846) e a receita aplica sozinha no vídeo principal e no B-roll. Medido no vídeo da câmera
frontal (`ec1beaea….MOV`): 0,67 nível do macOS no quadro, 2,1 no MP4 final (`target/fixtures/corte_celular`).

Legenda viva: ~26 s pra 52 s de fala desde 18/10 (quadros no HyperFrames, ProRes pelo chip de vídeo), no `~/motion-ysquad`.
Motion, B-roll real (incluindo B-roll de celular) e música testados só com material sintético.

Riscos: a escala de entrada das LUTs da Sony (código cheio x faixa de vídeo) não foi confirmada com
cartão cinza (afeta ~3% dos tons médios no modo `sony`). Push pelo SSH só via
`git@github.com:maltaruan/filmcraft.git`.
