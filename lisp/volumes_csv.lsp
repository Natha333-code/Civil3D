;;; ============================================================
;;; volumes_csv.lsp - Exporta volumes de superficies de volume
;;;                   (TIN Volume Surface) do Civil 3D para CSV
;;;
;;; Comando:
;;;   VOLCSV - Selecione as superficies de volume; gera um .csv
;;;            com Corte, Aterro e Liquido de cada superficie e
;;;            o TOTAL (somatorio) no final.
;;;   VOLXLS - Mesma selecao, mas gera uma planilha Excel (.xlsx)
;;;            formatada (cores, bordas, totais com formula).
;;;            Requer o Microsoft Excel instalado.
;;;
;;; Formato do CSV: separador ";" e decimal "," (padrao do Excel
;;; em portugues). Para mudar, altere as variaveis abaixo.
;;;
;;; Como carregar: APPLOAD -> selecione este arquivo
;;; ============================================================

(vl-load-com)

(setq *volcsv-sep*     ";"   ; separador de colunas
      *volcsv-decimal* ","   ; separador decimal
      *volcsv-casas*   3)    ; casas decimais

;;; Numero -> texto com o separador decimal configurado
(defun volcsv:num (x / s)
  (setq s (rtos x 2 *volcsv-casas*))
  (if (/= *volcsv-decimal* ".")
    (while (vl-string-search "." s)
      (setq s (vl-string-subst *volcsv-decimal* "." s))))
  s
)

;;; Retorna (nome corte aterro) de uma superficie de volume,
;;; ou nil se o objeto nao for uma superficie de volume.
(defun volcsv:dados (ent / obj stats cut fill nome)
  (setq obj   (vlax-ename->vla-object ent)
        stats (vl-catch-all-apply 'vlax-get (list obj 'Statistics)))
  (if (and stats
           (not (vl-catch-all-error-p stats))
           (not (vl-catch-all-error-p
                  (setq cut (vl-catch-all-apply 'vlax-get (list stats 'CutVolume)))))
           (not (vl-catch-all-error-p
                  (setq fill (vl-catch-all-apply 'vlax-get (list stats 'FillVolume))))))
    (progn
      (setq nome (vl-catch-all-apply 'vlax-get (list obj 'Name)))
      (if (vl-catch-all-error-p nome) (setq nome "(sem nome)"))
      (list nome cut fill))
  )
)

;;; Retorna (lista-de-dados qtd-ignoradas) a partir de uma selecao
(defun volcsv:coletar (ss / i dados lista ignoradas)
  (setq i 0 ignoradas 0)
  (repeat (sslength ss)
    (if (setq dados (volcsv:dados (ssname ss i)))
      (setq lista (cons dados lista))
      (setq ignoradas (1+ ignoradas)))
    (setq i (1+ i)))
  (list (reverse lista) ignoradas)
)

(defun c:VOLCSV ( / ss dados lista ignoradas arq f totC totA linha)
  (princ "\nSelecione as superficies de volume: ")
  (setq ss (ssget '((0 . "AECC_*SURFACE*"))))
  (if (not ss)
    (progn (princ "\nNenhuma superficie selecionada.") (exit)))

  ;; Coleta dados
  (setq dados     (volcsv:coletar ss)
        lista     (car dados)
        ignoradas (cadr dados))

  (if (not lista)
    (progn (princ "\nNenhuma das superficies selecionadas e de volume.") (exit)))

  ;; Arquivo de saida
  (setq arq (getfiled "Salvar tabela de volumes"
                      (strcat (getvar "DWGPREFIX")
                              (vl-filename-base (getvar "DWGNAME")) "_volumes.csv")
                      "csv" 1))
  (if (not arq) (progn (princ "\nCancelado.") (exit)))
  (if (not (setq f (open arq "w")))
    (progn (princ (strcat "\nNao foi possivel gravar: " arq
                          " (o arquivo esta aberto no Excel?)")) (exit)))

  ;; Cabecalho
  (write-line (strcat "Superficie" *volcsv-sep* "Corte (m3)" *volcsv-sep*
                      "Aterro (m3)" *volcsv-sep* "Liquido Aterro-Corte (m3)") f)

  ;; Linhas
  (setq totC 0.0 totA 0.0)
  (foreach d lista
    (setq totC (+ totC (cadr d))
          totA (+ totA (caddr d)))
    (write-line (strcat (car d)                           *volcsv-sep*
                        (volcsv:num (cadr d))             *volcsv-sep*
                        (volcsv:num (caddr d))            *volcsv-sep*
                        (volcsv:num (- (caddr d) (cadr d)))) f))

  ;; Total
  (setq linha (strcat "TOTAL" *volcsv-sep*
                      (volcsv:num totC) *volcsv-sep*
                      (volcsv:num totA) *volcsv-sep*
                      (volcsv:num (- totA totC))))
  (write-line linha f)
  (close f)

  ;; Resumo na linha de comando
  (princ (strcat "\nSuperficies exportadas: " (itoa (length lista))))
  (if (> ignoradas 0)
    (princ (strcat "  |  Ignoradas (nao sao de volume): " (itoa ignoradas))))
  (princ (strcat "\nCorte total:  " (rtos totC 2 *volcsv-casas*)
                 "\nAterro total: " (rtos totA 2 *volcsv-casas*)
                 "\nArquivo: " arq))
  (princ)
)

;;; ============================================================
;;; VOLXLS - exporta para Excel (.xlsx) com formatacao
;;; ============================================================

;;; Cores (R G B) - altere aqui para personalizar
(setq *volxls-cor-titulo*    '(31 78 121)    ; texto do titulo
      *volxls-cor-cabecalho* '(31 78 121)    ; fundo do cabecalho
      *volxls-cor-cab-texto* '(255 255 255)  ; texto do cabecalho
      *volxls-cor-zebra*     '(221 235 247)  ; fundo das linhas alternadas
      *volxls-cor-total*     '(255 242 204)  ; fundo da linha TOTAL
      *volxls-cor-borda*     '(166 166 166)) ; bordas da tabela

;;; (R G B) -> cor do Excel (inteiro BGR)
(defun volxls:cor (rgb)
  (+ (car rgb) (* 256 (cadr rgb)) (* 65536 (caddr rgb)))
)

;;; Texto com acentos via codigo de caractere (evita problemas de
;;; codificacao do arquivo .lsp): 179 = "3" sobrescrito, 237 = "i" agudo
(defun volxls:m3 () (strcat " (m" (chr 179) ")"))

;;; Formato numerico do Excel conforme *volcsv-casas*.
;;; mil = separador de milhar, dec = separador decimal
(defun volxls:formato (mil dec / s n)
  (setq s (strcat "#" mil "##0") n *volcsv-casas*)
  (if (> n 0) (setq s (strcat s dec)))
  (repeat n (setq s (strcat s "0")))
  s
)

;;; Formatos candidatos. O Excel pode interpretar o formato no padrao
;;; americano ("#,##0.000" / [Red]) ou no padrao do Windows em
;;; portugues ("#.##0,000" / [Vermelho]); tentamos os dois.
;;; vermelho = T -> negativos em vermelho
(defun volxls:formatos (vermelho / en pt res)
  (setq en (volxls:formato "," ".")
        pt (volxls:formato "." ","))
  (if vermelho
    (setq res (list (strcat en ";[Red]-" en)
                    (strcat pt ";[Vermelho]-" pt))))
  (append res (list en pt))
)

;;; Tenta aplicar (propriedade . valor) em ordem ate um funcionar.
;;; Retorna T se algum funcionou.
(defun volxls:tentar (ws endereco pares / r ok)
  (setq r (vlax-get-property ws 'Range endereco))
  (while (and pares (not ok))
    (if (not (vl-catch-all-error-p
               (vl-catch-all-apply 'vlax-put-property
                                   (list r (caar pares) (cdar pares)))))
      (setq ok T))
    (setq pares (cdr pares)))
  (vlax-release-object r)
  ok
)

;;; Aplica o primeiro formato numerico aceito pelo Excel
(defun volxls:numero (ws endereco vermelho / pares)
  (foreach prop '(NumberFormat NumberFormatLocal)
    (foreach f (volxls:formatos vermelho)
      (setq pares (cons (cons prop f) pares))))
  (volxls:tentar ws endereco (reverse pares))
)

;;; Aplica propriedades a um sub-objeto (Font, Interior, Borders)
(defun volxls:sub (obj prop pares / o)
  (setq o (vlax-get-property obj prop))
  (foreach p pares (vlax-put-property o (car p) (cdr p)))
  (vlax-release-object o)
)

;;; Formata um intervalo: props do Range, da Fonte, do Fundo e das Bordas
(defun volxls:cel (ws endereco props fonte fundo bordas / r)
  (setq r (vlax-get-property ws 'Range endereco))
  (foreach p props (vlax-put-property r (car p) (cdr p)))
  (if fonte  (volxls:sub r 'Font fonte))
  (if fundo  (volxls:sub r 'Interior fundo))
  (if bordas (volxls:sub r 'Borders bordas))
  (vlax-release-object r)
)

;;; Ajusta a largura das colunas de um intervalo
(defun volxls:autoajuste (ws endereco / r c)
  (setq r (vlax-get-property ws 'Range endereco)
        c (vlax-get-property r 'Columns))
  (vlax-invoke-method c 'AutoFit)
  (vlax-release-object c)
  (vlax-release-object r)
)

;;; Formata uma borda especifica (8 = superior) de um intervalo
(defun volxls:borda (ws endereco lado pares / r bs b)
  (setq r  (vlax-get-property ws 'Range endereco)
        bs (vlax-get-property r 'Borders)
        b  (vlax-get-property bs 'Item lado))
  (foreach p pares (vlax-put-property b (car p) (cdr p)))
  (vlax-release-object b)
  (vlax-release-object bs)
  (vlax-release-object r)
)

;;; Garante largura minima de uma coluna
(defun volxls:largura-min (ws endereco minimo / r w)
  (setq r (vlax-get-property ws 'Range endereco)
        w (vlax-get-property r 'ColumnWidth))
  (if (= (type w) 'VARIANT) (setq w (vlax-variant-value w)))
  (if (< w minimo) (vlax-put-property r 'ColumnWidth minimo))
  (vlax-release-object r)
)

;;; Monta e salva a planilha. Retorna o objeto Workbook.
(defun volxls:gerar (xl lista arq / wbs wb ws ini lin n tot)
  (vlax-put-property xl 'DisplayAlerts :vlax-false)
  (setq wbs (vlax-get-property xl 'Workbooks)
        wb  (vlax-invoke-method wbs 'Add)
        ws  (vlax-get-property wb 'ActiveSheet))
  (vlax-put-property ws 'Name "Volumes")

  ;; Titulo e informacoes
  (volxls:cel ws "A1" (list (cons 'Value2 "Quadro de Volumes - Corte e Aterro"))
              (list (cons 'Bold :vlax-true) (cons 'Size 14)
                    (cons 'Color (volxls:cor *volxls-cor-titulo*)))
              nil nil)
  (volxls:cel ws "A2" (list (cons 'Value2 (strcat "Desenho: " (getvar "DWGNAME"))))
              (list (cons 'Italic :vlax-true) (cons 'Color (volxls:cor '(89 89 89))))
              nil nil)
  (volxls:cel ws "A3" (list (cons 'Value2
                                  (strcat "Data: "
                                          (menucmd "M=$(edtime,$(getvar,date),DD/MO/YYYY HH:MM)"))))
              (list (cons 'Italic :vlax-true) (cons 'Color (volxls:cor '(89 89 89))))
              nil nil)
  (foreach a '("A1:D1" "A2:D2" "A3:D3")
    (volxls:cel ws a (list (cons 'MergeCells :vlax-true)) nil nil nil))

  ;; Cabecalho (linha 5)
  (volxls:cel ws "A5" (list (cons 'Value2 (strcat "Superf" (chr 237) "cie"))) nil nil nil)
  (volxls:cel ws "B5" (list (cons 'Value2 (strcat "Corte" (volxls:m3)))) nil nil nil)
  (volxls:cel ws "C5" (list (cons 'Value2 (strcat "Aterro" (volxls:m3)))) nil nil nil)
  (volxls:cel ws "D5" (list (cons 'Value2 (strcat "L" (chr 237) "quido Aterro-Corte" (volxls:m3))))
              nil nil nil)
  (volxls:cel ws "A5:D5"
              (list (cons 'HorizontalAlignment -4108) (cons 'RowHeight 22)
                    (cons 'VerticalAlignment -4108))
              (list (cons 'Bold :vlax-true)
                    (cons 'Color (volxls:cor *volxls-cor-cab-texto*)))
              (list (cons 'Color (volxls:cor *volxls-cor-cabecalho*)))
              nil)

  ;; Dados
  (setq ini 6 lin ini)
  (volxls:tentar ws (strcat "A" (itoa ini) ":A" (itoa (+ ini (length lista) -1)))
                 (list (cons 'NumberFormat "@")))            ; nome como texto
  (foreach d lista
    (setq n (itoa lin))
    (volxls:cel ws (strcat "A" n) (list (cons 'Value2 (car d)))   nil nil nil)
    (volxls:cel ws (strcat "B" n) (list (cons 'Value2 (cadr d)))  nil nil nil)
    (volxls:cel ws (strcat "C" n) (list (cons 'Value2 (caddr d))) nil nil nil)
    (volxls:cel ws (strcat "D" n) (list (cons 'Formula (strcat "=C" n "-B" n))) nil nil nil)
    (if (= (rem (- lin ini) 2) 1)
      (volxls:cel ws (strcat "A" n ":D" n) nil nil
                  (list (cons 'Color (volxls:cor *volxls-cor-zebra*))) nil))
    (setq lin (1+ lin)))

  ;; Linha TOTAL (com formulas)
  (setq tot (itoa lin)
        n   (itoa (1- lin)))
  (volxls:cel ws (strcat "A" tot) (list (cons 'Value2 "TOTAL")) nil nil nil)
  (volxls:cel ws (strcat "B" tot)
              (list (cons 'Formula (strcat "=SUM(B" (itoa ini) ":B" n ")"))) nil nil nil)
  (volxls:cel ws (strcat "C" tot)
              (list (cons 'Formula (strcat "=SUM(C" (itoa ini) ":C" n ")"))) nil nil nil)
  (volxls:cel ws (strcat "D" tot)
              (list (cons 'Formula (strcat "=C" tot "-B" tot))) nil nil nil)
  (volxls:cel ws (strcat "A" tot ":D" tot) nil
              (list (cons 'Bold :vlax-true))
              (list (cons 'Color (volxls:cor *volxls-cor-total*)))
              nil)
  ;; Formatos numericos (liquido negativo em vermelho)
  (volxls:numero ws (strcat "B" (itoa ini) ":C" tot) nil)
  (volxls:numero ws (strcat "D" (itoa ini) ":D" tot) T)

  ;; Bordas finas na tabela inteira + borda dupla acima do TOTAL
  (volxls:cel ws (strcat "A5:D" tot) nil nil nil
              (list (cons 'LineStyle 1) (cons 'Weight 2)
                    (cons 'Color (volxls:cor *volxls-cor-borda*))))
  (volxls:borda ws (strcat "A" tot ":D" tot) 8               ; xlEdgeTop
                 (list (cons 'LineStyle -4119)                   ; xlDouble
                       (cons 'Color (volxls:cor *volxls-cor-titulo*))))


  ;; Largura das colunas
  (volxls:autoajuste ws (strcat "A5:D" tot))
  (volxls:largura-min ws "A:A" 28)

  ;; Salvar (.xlsx = 51)
  (vlax-invoke-method wb 'SaveAs arq 51)
  (vlax-release-object ws)
  (vlax-release-object wbs)
  wb
)

(defun c:VOLXLS ( / ss dados lista ignoradas arq xl res abrir)
  (princ "\nSelecione as superficies de volume: ")
  (setq ss (ssget '((0 . "AECC_*SURFACE*"))))
  (cond
    ((not ss)
     (princ "\nNenhuma superficie selecionada."))
    ((not (car (setq dados (volcsv:coletar ss))))
     (princ "\nNenhuma das superficies selecionadas e de volume."))
    ((not (setq arq (getfiled "Salvar planilha de volumes"
                              (strcat (getvar "DWGPREFIX")
                                      (vl-filename-base (getvar "DWGNAME")) "_volumes.xlsx")
                              "xlsx" 1)))
     (princ "\nCancelado."))
    ((not (setq xl (vlax-create-object "Excel.Application")))
     (princ "\nNao foi possivel iniciar o Excel. Ele esta instalado? Use VOLCSV como alternativa."))
    (T
     (setq lista     (car dados)
           ignoradas (cadr dados))
     (princ "\nGerando planilha no Excel...")
     (setq res (vl-catch-all-apply 'volxls:gerar (list xl lista arq)))
     (if (vl-catch-all-error-p res)
       (progn
         (princ (strcat "\nErro ao gerar a planilha: " (vl-catch-all-error-message res)
                        "\n(Se o arquivo ja existe, verifique se ele nao esta aberto no Excel.)"))
         (vl-catch-all-apply 'vlax-invoke-method (list xl 'Quit)))
       (progn
         (princ (strcat "\nSuperficies exportadas: " (itoa (length lista))))
         (if (> ignoradas 0)
           (princ (strcat "  |  Ignoradas (nao sao de volume): " (itoa ignoradas))))
         (princ (strcat "\nArquivo: " arq))
         (initget "Sim Nao")
         (setq abrir (getkword "\nAbrir a planilha agora? [Sim/Nao] <Sim>: "))
         (if (/= abrir "Nao")
           (progn
             (vlax-put-property xl 'DisplayAlerts :vlax-true)
             (vlax-put-property xl 'Visible :vlax-true)
             (vlax-put-property xl 'UserControl :vlax-true))
           (progn
             (vlax-invoke-method res 'Close :vlax-false)
             (vlax-invoke-method xl 'Quit)))
         (vlax-release-object res)))
     (vlax-release-object xl)
     (gc)))
  (princ)
)

(princ "\nvolumes_csv.lsp carregado. Comandos: VOLCSV, VOLXLS")
(princ)
