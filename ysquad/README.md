# ysquad/

Ferramentas do nosso fork que ficam fora do produto (o editor continua em Rust puro). Meta: editor
sólido pro uso da ySquad (reel, depois vídeo longo), não paridade com o Premiere.

Divisão (17/10): o FilmCraft só monta (corte, cor, voz, música, B-roll, legenda, exportação). Criar,
animar, posicionar e dimensionar cena de motion é do EffectCraft (`~/effectcraft`, fork
maltaruan/effectcraft): a cena chega pronta e a receita só a põe no tempo das palavras. O código do
produto (`crates/`, gráficos, modelos `.fcgt`) é do upstream e não é mexido aqui.

- `receitas/montar_video.py PASTA_DO_CORTE SAIDA`: do corte da skill `cortar-fala` ao vídeo final,
  pelo FilmCraft sem janela, exportando pela placa de vídeo e pelo chip de vídeo do Mac. Formato
  9x16, 16x9 ou 4x3 (horizontal com o foco no rosto); legenda fixa ou `--legenda-viva ESTILO`
  (caixa, acende, pop, acumula, limpa; `--amostras-legenda PASTA` pra escolher); `efeitos.json` no
  corte (zoom no rosto, desfoque, B-roll e cenas de motion prontas do EffectCraft, por índice de
  palavra); voz limpa,
  `--musica` com ducking e -14 LUFS; log da Sony convertido sozinho (ver `cor/`).
- `receitas/legenda_viva.py`: a camada de legenda animada (HyperFrames, ProRes 4444 com alfa).
- `cor/log_709.py`: S-Log2/S-Log3 da Sony para Rec.709 como LUT de entrada. Modo `neutro`
  (padrão): o tratamento à mão do Ruan medido (branco neutralizado, calor, curva e saturação dele),
  exposição pela pele, com `--visual naruto` (padrão, quente) ou `discord`; modo `sony`: LUT oficial.
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

Motion (17/10): chave `motion` do `efeitos.json` com cenas prontas do EffectCraft, ProRes 4444 com
transparência no tamanho do vídeo final. A receita confere arquivo, transparência e tamanho (se não
bate, para e pede pra refazer no EffectCraft) e põe a cena a 100 %, sem mexer, do `antes` ao `saida`.
Camadas, de baixo pra cima: vídeo, B-roll, motion, legenda. Testado no `target/fixtures/corte_motion`:
a cena aparece no tempo das palavras, no pixel em que veio, com a legenda por cima.

Pendente: vídeo de celular (HDR do iPhone: a correção é no código do produto, fora desta camada;
aguarda decisão). Legenda viva lenta (~24 s); se ela fica aqui ou passa pro EffectCraft, em aberto.
Motion, B-roll real e música testados só com material sintético.

Riscos: a escala de entrada das LUTs da Sony (código cheio x faixa de vídeo) não foi confirmada com
cartão cinza (afeta ~3% dos tons médios no modo `sony`). Push pelo SSH só via
`git@github.com:maltaruan/filmcraft.git`.
