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
| `VOLCSV`     | (`lisp/volumes_csv.lsp`) Selecione superficies de volume (TIN Volume Surface) e exporte um `.csv` com Corte, Aterro e Liquido de cada uma, mais o TOTAL. |

### Observacoes sobre o `VOLCSV`

- O CSV usa `;` como separador e `,` como decimal (abre direto no Excel em portugues). Ajuste `*volcsv-sep*` e `*volcsv-decimal*` no topo do arquivo se precisar de outro formato.
- Os volumes sao os **nao ajustados** (sem fatores de empolamento/contracao do Volumes Dashboard).
- Se a superficie estiver desatualizada (*Out of date*), faca **Rebuild** antes de exportar.
- Superficies que nao sao de volume sao ignoradas automaticamente.
