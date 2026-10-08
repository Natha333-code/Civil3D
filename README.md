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
- fica a **1,5 m da divisa lateral** com o lote vizinho (*Afastamento da divisa*);
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
| Afastamento da divisa (m) | `1.5` | Distancia entre a linha e a divisa lateral. |
| Distancia maxima rede-lote (m) | `30` | Lotes mais distantes sao ignorados. |
| Layer | `LIGACOES` | Criado em magenta se nao existir. As linhas tambem recebem cor magenta. |
| Usar LINE | `False` | `False` = polilinha (LWPOLYLINE); `True` = LINE. |
| Apagar linhas anteriores do layer | `False` | Use `True` para refazer sem duplicar (apaga LINE/polilinhas desse layer no espaco atual). |

**Como funciona**

1. Le os contornos de todos os parcels de todos os sites. Parcels **atravessados pela rede**
   (rua / faixa de dominio, gleba) ficam de fora.
2. Para cada lote, lanca raios perpendiculares a partir do eixo do tubo mais proximo, a cada
   0,25 m. O trecho em que o raio atinge o lote sem cruzar outro lote e a **testada**; suas pontas
   sao as **divisas laterais**. Lotes de fundo (sem testada para a rede) sao ignorados.
3. Uma divisa so e considerada se houver **outro lote do outro lado** (em lote de esquina usa a
   divisa com vizinho). A **cota da divisa** e a media de pontos da superficie ao longo dela, por
   dentro do lote; a mais baixa e escolhida.
4. Testada menor que 2x o afastamento: a ligacao vai no meio da testada.

**Observacoes**

- Tubos sao tratados como retos (do ponto inicial ao final). Linhas criadas em Z = 0.
- Pontos fora da superficie sao desconsiderados no calculo da cota.
