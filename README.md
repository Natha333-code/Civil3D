# Civil3D - Rotinas LISP e Dynamo

Rotinas AutoLISP e Dynamo para uso no AutoCAD Civil 3D.

## Como carregar

1. No Civil 3D, digite `APPLOAD`.
2. Selecione `lisp/ferramentas.lsp` e clique em **Load**.
3. (Opcional) Adicione ao **Startup Suite** para carregar automaticamente.

## Comandos

| Comando      | O que faz |
|--------------|-----------|
| `SOMACOMP`   | Soma o comprimento de linhas, polilinhas (2D/3D), arcos, circulos, splines e elipses selecionados. |
| `ANOTACOORD` | Clique em pontos e insere um MTEXT com as coordenadas E, N e Z (em WCS). |
| `VOLXLS`     | (`lisp/volumes_csv.lsp`) Igual ao `VOLCSV`, mas gera uma planilha Excel `.xlsx` formatada. |
| `VOLCSV`     | (`lisp/volumes_csv.lsp`) Selecione superficies de volume (TIN Volume Surface) e exporte um `.csv` com Corte, Aterro e Liquido de cada uma, mais o TOTAL. |

### Observacoes sobre o `VOLCSV`

- O CSV usa `;` como separador e `,` como decimal (abre direto no Excel em portugues). Ajuste `*volcsv-sep*` e `*volcsv-decimal*` no topo do arquivo se precisar de outro formato.
- Os volumes sao os **nao ajustados** (sem fatores de empolamento/contracao do Volumes Dashboard).
- Se a superficie estiver desatualizada (*Out of date*), faca **Rebuild** antes de exportar.
- Superficies que nao sao de volume sao ignoradas automaticamente.

### `VOLXLS` - planilha Excel formatada

Mesmo arquivo (`lisp/volumes_csv.lsp`). Gera um `.xlsx` com titulo, nome do desenho e data,
cabecalho colorido, linhas alternadas, bordas, numeros formatados, liquido negativo em
vermelho e linha TOTAL com formulas `=SOMA(...)`. Ao final pergunta se deseja abrir a planilha.

- **Requer o Microsoft Excel instalado** (a LISP controla o Excel via COM).
- As cores ficam nas variaveis `*volxls-cor-...*` no arquivo, em formato `(R G B)`.

---

## Rotinas Dynamo (Civil 3D 2021)

Ficam em `dynamo/`. Os `.dyn` sao gerados a partir do codigo Python em `dynamo/src/`
(`python3 dynamo/build_dyn.py`), entao para alterar uma rotina edite o `.py` e gere de novo.
Compativeis com Dynamo 2.5/2.6 (IronPython 2.7), que acompanha o Civil 3D 2021.

### `EixoEntreLinhas.dyn` - alinhamento no eixo de duas linhas + perfil longitudinal

1. Selecione duas **linhas ou polilinhas** - retas ou curvas: `LINE`, `ARC`, polilinha 2D/3D
   (com ou sem arcos) ou `SPLINE` - e um alinhamento e criado no **centro** entre elas,
   com **tangentes e curvas**.
2. A **superficie** escolhida e amostrada no alinhamento (perfil de superficie `TN - <superficie>`).
3. O **perfil longitudinal** (Profile View `PL - <alinhamento>`) e criado ja com esse perfil.

**Como usar**

- Abra o desenho, va em **Manage > Dynamo** (ou **Dynamo Player**) e abra `dynamo/EixoEntreLinhas.dyn`.
- Preencha as entradas e coloque **Executar = True**. No Dynamo, clique em **Run** (o grafico esta em modo *Manual*).
- Responda aos prompts na linha de comando do Civil 3D:
  primeira linha/polilinha, segunda linha/polilinha, superficie (se o nome nao foi informado) e ponto de insercao
  do perfil longitudinal (**Enter** = posicao automatica a direita do alinhamento).
- O no **Resultado** mostra o que foi criado ou a mensagem de erro.

| Entrada | Padrao | Observacao |
|---|---|---|
| Executar | `False` | So roda com `True` (evita rodar sem querer). |
| Nome do alinhamento | `EIXO` | Se ja existir, vira `EIXO (1)`, `EIXO (2)`... |
| Nome da superficie | vazio | Vazio = clicar na superficie no desenho. |
| Estilo do alinhamento / do perfil / do perfil longitudinal | vazio | Nome do estilo; vazio ou inexistente = primeiro estilo do desenho. |
| Band set do perfil longitudinal | vazio | Idem. |
| Inverter sentido | `False` | Inverte o sentido do estaqueamento. |
| Tolerancia (m) | `0.01` | Desvio maximo do alinhamento em relacao ao eixo calculado. Menor = mais fiel (mais trechos); maior = menos trechos. |

**Observacoes**

- **Como o eixo e calculado:** a rotina gera pontos a cada ~0,5 m que ficam **equidistantes**
  das duas curvas (curvas prolongadas nas pontas, entao bordos de comprimentos diferentes ou
  desencontrados funcionam). Depois esses pontos sao convertidos em retas e arcos dentro da
  tolerancia e viram o alinhamento. Ex.: dois bordos de pista com tangente-curva-tangente geram
  um alinhamento tangente-curva-tangente com o raio medio.
- A segunda curva e orientada automaticamente no mesmo sentido da primeira. As curvas podem ter
  quantidade de vertices diferente.
- As tangentes e curvas sao entidades fixas que seguem o eixo dentro da tolerancia; a
  tangencia entre elas nao e imposta (um ponto de tangencia pode deslocar ~1 m com 0,01 m de
  tolerancia). Em quinas vivas (polilinha sem arco), o eixo ganha uma curva pequena de concordancia.
- Nao aceita curvas fechadas (circulos, polilinhas fechadas), `XLINE` ou `RAY`.
- O alinhamento e criado sem site (*siteless*), no layer corrente, e com o primeiro label set.
- O estaqueamento segue o sentido da primeira linha selecionada (use *Inverter sentido* para trocar).
- Se o Dynamo estiver em primeiro plano, clique no desenho antes de responder aos prompts.

### `LigacoesPrediais.dyn` - ligacoes perpendiculares a rede, na divisa mais baixa de cada lote

Cria **uma linha magenta por lote** (parcel), perpendicular a rede (pipe network):

- parte do **eixo do tubo** e termina **1 m antes** do limite do lote (*Recuo do lote*);
- fica a **1 m da divisa lateral** com o lote vizinho (*Afastamento da divisa*), medido
  perpendicularmente a divisa, na frente do lote;
- usa sempre a **divisa de menor cota**, medida na superficie existente.

**Como usar**

- Abra `dynamo/LigacoesPrediais.dyn`, coloque **Executar = True** e clique em **Run**.
- Na linha de comando: clique em **um tubo** da rede (todos os tubos dessa rede sao usados) e,
  se o nome nao foi informado, na **superficie existente**.
- O no **Resultado** lista cada ligacao (comprimento, divisa usada, vizinho e cotas das divisas)
  e os lotes ignorados com o motivo.

| Entrada | Padrao | Observacao |
|---|---|---|
| Executar | `False` | So roda com `True`. |
| Nome da superficie | vazio | Vazio = clicar na superficie no desenho. |
| Recuo do lote (m) | `1.0` | A linha termina esta distancia antes do lote. |
| Afastamento da divisa (m) | `1.0` | Distancia entre a linha e a divisa mais baixa (perpendicular a divisa). |
| Distancia maxima rede-lote (m) | `30` | Lotes mais distantes sao ignorados. |
| Layer | `LIGACOES` | Criado em magenta se nao existir. As linhas tambem recebem cor magenta. |
| Usar LINE | `False` | `False` = polilinha (LWPOLYLINE); `True` = LINE. |
| Apagar linhas anteriores do layer | `False` | Use `True` para refazer sem duplicar (apaga LINE/polilinhas desse layer no espaco atual). |

**Como funciona**

1. Le os contornos de todos os parcels de todos os sites. Parcels **atravessados pela rede**
   (rua / faixa de dominio, gleba) ficam de fora.
2. Para cada lote, lanca raios perpendiculares a partir da reta do tubo mais proximo
   (**prolongada alem dos PVs**, entao um PV no meio do lote nao atrapalha), a cada 0,25 m.
   O trecho em que o raio atinge o lote sem cruzar outro lote e a **testada**; os cantos dela sao
   localizados com precisao e as **divisas laterais** sao as arestas do lote que saem desses cantos.
   Lotes de fundo (sem testada para a rede) sao ignorados.
3. Uma divisa so e considerada se houver **outro lote do outro lado** (em lote de esquina usa a
   divisa com vizinho). A **cota da divisa** e a media de 10 pontos da superficie ao longo da
   propria divisa, 0,5 m para dentro do lote; a mais baixa e escolhida.
4. A ligacao e posicionada onde a frente do lote fica a exatamente *Afastamento* da divisa
   escolhida (vale para divisas obliquas). Testada estreita demais: a ligacao vai no meio.
5. A linha comeca no **eixo do tubo que esta em frente**, perpendicular a ele. Se nenhum tubo
   estiver em frente (lado externo de uma deflexao), parte do PV mais proximo e o relatorio avisa.

**Observacoes**

- Tubos sao tratados como retos (do ponto inicial ao final). Linhas criadas em Z = 0.
- O relatorio mostra, para cada lote, a divisa usada, a distancia ate ela e as cotas das duas divisas.
- Pontos fora da superficie sao desconsiderados no calculo da cota.

### `AjusteGreide.dyn` - analise de corte/aterro e ajuste automatico do perfil longitudinal

Para cada alinhamento escolhido, analisa o **perfil longitudinal de projeto (greide)** contra as
**secoes transversais do terreno**, identifica as alturas de **corte e aterro** e **ajusta o
greide automaticamente** para que nenhum ponto da secao passe do corte maximo ou do aterro maximo.

**Como usar**

- Abra `dynamo/AjusteGreide.dyn`, preencha os limites, coloque **Executar = True** e clique em **Run**.
- Na linha de comando: selecione os **alinhamentos** (ou informe os nomes) e clique na
  **superficie existente** (ou informe o nome).
- Por padrao o perfil original **nao e alterado**: e criada uma copia `<perfil> - AJUSTADO`
  (mesmos PVIs e curvas verticais) e o ajuste e feito nela. Ela aparece automaticamente nos
  perfis longitudinais (Profile Views) do alinhamento.
- O no **Resultado** mostra, por alinhamento, o corte e o aterro maximos **antes e depois**
  (com a estaca), os PVIs inseridos e movidos, a rampa maxima resultante e as estacas que nao
  puderam ser atendidas.

| Entrada | Padrao | Observacao |
|---|---|---|
| Executar | `False` | So roda com `True`. |
| Alinhamentos | vazio | Nomes separados por `;`. Vazio = selecionar no desenho. |
| Nome da superficie existente | vazio | Vazio = clicar na superficie. |
| Nome do perfil de projeto | vazio | Perfil de layout. Vazio = primeiro perfil de layout do alinhamento. |
| Corte maximo (m) | `3.0` | Em qualquer ponto da secao (eixo e bordos). |
| Aterro maximo (m) | `3.0` | Idem. |
| Largura da plataforma (m) | `7.0` | Largura total da secao analisada. `0` = analisa so o eixo. |
| Inclinacao transversal (%) | `-2.0` | Do eixo para os bordos (negativo = caindo para os bordos). |
| Intervalo de analise (m) | `10` | Espacamento das secoes. Estacas das sample lines e dos PVIs tambem entram. |
| Espacamento minimo entre PVIs (m) | `20` | Mais perto que isso, move o PVI existente em vez de criar outro. |
| Ajustar o perfil original | `False` | `True` = altera o proprio perfil (Ctrl+Z desfaz). |

**Como funciona**

1. **Secoes transversais**: em cada estaca, a cota do terreno e lida na superficie a cada ~1 m na
   perpendicular ao alinhamento, de bordo a bordo da plataforma (estacas = intervalo + sample
   lines existentes + PVIs).
2. **Corte/aterro**: a plataforma e o eixo do greide mais a inclinacao transversal ate os
   bordos; corte/aterro = diferenca entre a plataforma e o terreno em cada ponto da secao.
3. **Faixa permitida**: para cada estaca calcula a cota minima e maxima do eixo que mantem
   **todos** os pontos da secao dentro dos limites.
4. **Ajuste**: enquanto houver estaca fora da faixa, pega a pior e: se houver PVI a menos do
   espacamento minimo, **move esse PVI**; senao **insere um PVI** na estaca, deixando 2 cm de folga
   dentro do limite. As curvas verticais existentes sao mantidas. Se um PVI for movido varias
   vezes sem resolver, a rotina passa a aceitar PVIs novos mais proximos dele.

**Observacoes**

- Estacas marcadas como **inviaveis** sao aquelas em que o terreno, na transversal, varia mais
  que `corte max + aterro max` ao longo da largura: nenhuma cota de greide atende. Elas sao
  listadas e nao sao ajustadas (reduza a largura ou aumente os limites).
- A rotina nao impoe rampa maxima nem comprimento minimo de curva: confira a **rampa maxima**
  informada no resultado e, se precisar, acrescente curvas verticais nos PVIs inseridos.
- A plataforma e simplificada (largura + inclinacao unica); taludes e subleito nao entram no
  calculo. Pontos fora da superficie sao desconsiderados.
- Se o Civil recusar mover/inserir um PVI (por exemplo, sobreposicao de curvas verticais), a
  estaca e informada no resultado.
