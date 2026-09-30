# Civil3D - Rotinas LISP

Rotinas AutoLISP para uso no AutoCAD Civil 3D.

## Como carregar

1. No Civil 3D, digite `APPLOAD`.
2. Selecione `lisp/ferramentas.lsp` e clique em **Load**.
3. (Opcional) Adicione ao **Startup Suite** para carregar automaticamente.

## Comandos

| Comando      | O que faz |
|--------------|-----------|
| `SOMACOMP`   | Soma o comprimento de linhas, polilinhas (2D/3D), arcos, circulos, splines e elipses selecionados. |
| `ANOTACOORD` | Clique em pontos e insere um MTEXT com as coordenadas E, N e Z (em WCS). |
| `VOLXLS`     | (`lisp/volumes_csv.lsp`) Igual ao `VOLCSV`, mas gera uma planilha formatada (`.xml`, abre no Excel). |
| `VOLCSV`     | (`lisp/volumes_csv.lsp`) Selecione superficies de volume (TIN Volume Surface) e exporte um `.csv` com Corte, Aterro e Liquido de cada uma, mais o TOTAL. |

### Observacoes sobre o `VOLCSV`

- O CSV usa `;` como separador e `,` como decimal (abre direto no Excel em portugues). Ajuste `*volcsv-sep*` e `*volcsv-decimal*` no topo do arquivo se precisar de outro formato.
- Os volumes sao os **nao ajustados** (sem fatores de empolamento/contracao do Volumes Dashboard).
- Se a superficie estiver desatualizada (*Out of date*), faca **Rebuild** antes de exportar.
- Superficies que nao sao de volume sao ignoradas automaticamente.

### `VOLXLS` - planilha formatada

Mesmo arquivo (`lisp/volumes_csv.lsp`). Gera uma planilha no formato **Planilha XML 2003**
(`.xml`), que o Excel abre direto com dois cliques, ja formatada:

- titulo, nome do desenho e data;
- cabecalho colorido, linhas alternadas e bordas;
- numeros com separador de milhar (exibidos conforme o idioma do Windows, ex.: `1.520,350`);
- liquido negativo em vermelho;
- linha TOTAL com formulas de soma;
- cabecalho congelado e impressao em A4 paisagem com 1 pagina de largura.

A LISP grava o arquivo sozinha: **nao usa automacao do Excel** e nao depende dele para gerar
o arquivo. Para ter um `.xlsx`, abra no Excel e use *Salvar como > Pasta de Trabalho do Excel*.

As cores ficam nas variaveis `*volxls-cor-...*` no arquivo, em formato `(R G B)`.
