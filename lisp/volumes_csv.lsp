;;; ============================================================
;;; volumes_csv.lsp - Exporta volumes de superficies de volume
;;;                   (TIN Volume Surface) do Civil 3D para CSV
;;;
;;; Comando:
;;;   VOLCSV - Selecione as superficies de volume; gera um .csv
;;;            com Corte, Aterro e Liquido de cada superficie e
;;;            o TOTAL (somatorio) no final.
;;;   VOLXLS - Mesma selecao, mas gera uma planilha formatada
;;;            (cores, bordas, totais com formula) no formato
;;;            "Planilha XML 2003" (.xml), que o Excel abre direto.
;;;            Nao precisa do Excel para gerar o arquivo.
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
;;; VOLXLS - planilha formatada (Planilha XML 2003 / SpreadsheetML)
;;;
;;; A LISP grava o arquivo diretamente (sem automacao do Excel).
;;; O Excel abre o .xml ja com cores, bordas, formatos e formulas.
;;; ============================================================

;;; Cores (R G B) - altere aqui para personalizar
(setq *volxls-cor-titulo*    '(31 78 121)    ; texto do titulo
      *volxls-cor-cabecalho* '(31 78 121)    ; fundo do cabecalho
      *volxls-cor-cab-texto* '(255 255 255)  ; texto do cabecalho
      *volxls-cor-zebra*     '(221 235 247)  ; fundo das linhas alternadas
      *volxls-cor-total*     '(255 242 204)  ; fundo da linha TOTAL
      *volxls-cor-borda*     '(166 166 166)) ; bordas da tabela

;;; (R G B) -> "#RRGGBB"
(defun volxml:hex (rgb / d)
  (setq d "0123456789ABCDEF")
  (apply 'strcat
         (cons "#"
               (mapcar '(lambda (n)
                          (strcat (substr d (1+ (/ n 16)) 1)
                                  (substr d (1+ (rem n 16)) 1)))
                       rgb)))
)

;;; Escapa texto para XML. Caracteres acentuados viram &#codigo;
;;; (assim o arquivo fica 100% ASCII e nao ha problema de codificacao)
(defun volxml:esc (s / r)
  (setq r "")
  (foreach c (vl-string->list s)
    (setq r (strcat r
                    (cond ((= c 38) "&amp;")
                          ((= c 60) "&lt;")
                          ((= c 62) "&gt;")
                          ((= c 34) "&quot;")
                          ((> c 127) (strcat "&#" (itoa c) ";"))
                          (T (chr c))))))
  r
)

;;; Numero para o XML (sempre com ponto decimal)
(defun volxml:num (x) (rtos x 2 6))

;;; Formato numerico do Excel (padrao interno, com ponto decimal;
;;; o Excel exibe conforme o idioma do Windows, ex.: 1.520,350)
(defun volxml:formato ( / s n)
  (setq s "#,##0" n *volcsv-casas*)
  (if (> n 0) (setq s (strcat s ".")))
  (repeat n (setq s (strcat s "0")))
  s
)

;;; <Borders> com as 4 bordas finas; topo duplo se duplo = T
(defun volxml:bordas (duplo / cor)
  (setq cor (volxml:hex *volxls-cor-borda*))
  (strcat "<Borders>"
          "<Border ss:Position=\"Bottom\" ss:LineStyle=\"Continuous\" ss:Weight=\"1\" ss:Color=\"" cor "\"/>"
          "<Border ss:Position=\"Left\" ss:LineStyle=\"Continuous\" ss:Weight=\"1\" ss:Color=\"" cor "\"/>"
          "<Border ss:Position=\"Right\" ss:LineStyle=\"Continuous\" ss:Weight=\"1\" ss:Color=\"" cor "\"/>"
          (if duplo
            (strcat "<Border ss:Position=\"Top\" ss:LineStyle=\"Double\" ss:Weight=\"3\" ss:Color=\""
                    (volxml:hex *volxls-cor-titulo*) "\"/>")
            (strcat "<Border ss:Position=\"Top\" ss:LineStyle=\"Continuous\" ss:Weight=\"1\" ss:Color=\"" cor "\"/>"))
          "</Borders>")
)

;;; Estilo de celula da tabela
;;;   id: nome do estilo | fundo: (R G B) ou nil | negrito: T/nil
;;;   fmt: formato numerico ou nil | duplo: borda dupla em cima
(defun volxml:estilo (id fundo negrito fmt duplo)
  (strcat "<Style ss:ID=\"" id "\">"
          (volxml:bordas duplo)
          (if negrito "<Font ss:Bold=\"1\"/>" "")
          (if fundo
            (strcat "<Interior ss:Color=\"" (volxml:hex fundo) "\" ss:Pattern=\"Solid\"/>")
            "")
          (if fmt (strcat "<NumberFormat ss:Format=\"" fmt "\"/>") "")
          "</Style>")
)

;;; <Cell> com estilo, tipo ("String"/"Number"), valor e formula opcional
(defun volxml:cel (estilo tipo valor formula)
  (strcat "<Cell ss:StyleID=\"" estilo "\""
          (if formula (strcat " ss:Formula=\"" formula "\"") "")
          "><Data ss:Type=\"" tipo "\">" valor "</Data></Cell>")
)

;;; Grava a planilha XML
(defun volxml:gravar (f lista / fmt fmtneg zebra nomemax n z liq totC totA
                               m3 cabecalho)
  (setq fmt    (volxml:formato)
        fmtneg (strcat fmt ";[Red]\\-" fmt)
        zebra  *volxls-cor-zebra*
        m3     " (m&#179;)"
        totC   0.0
        totA   0.0
        nomemax 10)
  (foreach d lista
    (setq nomemax (max nomemax (strlen (car d)))))

  ;; Cabecalho do arquivo
  (foreach l
    (list "<?xml version=\"1.0\"?>"
          "<?mso-application progid=\"Excel.Sheet\"?>"
          "<Workbook xmlns=\"urn:schemas-microsoft-com:office:spreadsheet\""
          " xmlns:o=\"urn:schemas-microsoft-com:office:office\""
          " xmlns:x=\"urn:schemas-microsoft-com:office:excel\""
          " xmlns:ss=\"urn:schemas-microsoft-com:office:spreadsheet\""
          " xmlns:html=\"http://www.w3.org/TR/REC-html40\">"
          "<Styles>"
          "<Style ss:ID=\"Default\" ss:Name=\"Normal\"><Alignment ss:Vertical=\"Center\"/><Font ss:FontName=\"Calibri\" ss:Size=\"11\"/></Style>"
          (strcat "<Style ss:ID=\"titulo\"><Font ss:FontName=\"Calibri\" ss:Size=\"14\" ss:Bold=\"1\" ss:Color=\""
                  (volxml:hex *volxls-cor-titulo*) "\"/></Style>")
          "<Style ss:ID=\"info\"><Font ss:FontName=\"Calibri\" ss:Size=\"11\" ss:Italic=\"1\" ss:Color=\"#595959\"/></Style>"
          (strcat "<Style ss:ID=\"cab\"><Alignment ss:Horizontal=\"Center\" ss:Vertical=\"Center\" ss:WrapText=\"1\"/>"
                  (volxml:bordas nil)
                  "<Font ss:FontName=\"Calibri\" ss:Size=\"11\" ss:Bold=\"1\" ss:Color=\""
                  (volxml:hex *volxls-cor-cab-texto*) "\"/>"
                  "<Interior ss:Color=\"" (volxml:hex *volxls-cor-cabecalho*) "\" ss:Pattern=\"Solid\"/></Style>")
          (volxml:estilo "t"  nil   nil nil    nil)
          (volxml:estilo "tz" zebra nil nil    nil)
          (volxml:estilo "n"  nil   nil fmt    nil)
          (volxml:estilo "nz" zebra nil fmt    nil)
          (volxml:estilo "l"  nil   nil fmtneg nil)
          (volxml:estilo "lz" zebra nil fmtneg nil)
          (volxml:estilo "Tt" *volxls-cor-total* T nil    T)
          (volxml:estilo "Tn" *volxls-cor-total* T fmt    T)
          (volxml:estilo "Tl" *volxls-cor-total* T fmtneg T)
          "</Styles>"
          "<Worksheet ss:Name=\"Volumes\">"
          "<Table>"
          (strcat "<Column ss:Width=\"" (itoa (max 160 (+ 20 (* 7 nomemax)))) "\"/>")
          "<Column ss:Width=\"115\"/>"
          "<Column ss:Width=\"115\"/>"
          "<Column ss:Width=\"175\"/>"
          ;; Titulo e informacoes
          "<Row ss:Height=\"21\"><Cell ss:MergeAcross=\"3\" ss:StyleID=\"titulo\"><Data ss:Type=\"String\">Quadro de Volumes - Corte e Aterro</Data></Cell></Row>"
          (strcat "<Row><Cell ss:MergeAcross=\"3\" ss:StyleID=\"info\"><Data ss:Type=\"String\">Desenho: "
                  (volxml:esc (getvar "DWGNAME")) "</Data></Cell></Row>")
          (strcat "<Row><Cell ss:MergeAcross=\"3\" ss:StyleID=\"info\"><Data ss:Type=\"String\">Data: "
                  (menucmd "M=$(edtime,$(getvar,date),DD/MO/YYYY HH:MM)") "</Data></Cell></Row>")
          "<Row/>"
          ;; Cabecalho da tabela
          (strcat "<Row ss:Height=\"24\">"
                  (volxml:cel "cab" "String" "Superf&#237;cie" nil)
                  (volxml:cel "cab" "String" (strcat "Corte" m3) nil)
                  (volxml:cel "cab" "String" (strcat "Aterro" m3) nil)
                  (volxml:cel "cab" "String" (strcat "L&#237;quido Aterro-Corte" m3) nil)
                  "</Row>"))
    (write-line l f))

  ;; Linhas de dados (liquido = formula Aterro - Corte)
  (setq n 0)
  (foreach d lista
    (setq z   (if (= (rem n 2) 1) "z" "")
          liq (- (caddr d) (cadr d))
          totC (+ totC (cadr d))
          totA (+ totA (caddr d)))
    (write-line
      (strcat "<Row>"
              (volxml:cel (strcat "t" z) "String" (volxml:esc (car d)) nil)
              (volxml:cel (strcat "n" z) "Number" (volxml:num (cadr d)) nil)
              (volxml:cel (strcat "n" z) "Number" (volxml:num (caddr d)) nil)
              (volxml:cel (strcat "l" z) "Number" (volxml:num liq) "=RC[-1]-RC[-2]")
              "</Row>")
      f)
    (setq n (1+ n)))

  ;; Linha TOTAL (formulas de soma; valores ja calculados como reserva)
  (write-line
    (strcat "<Row ss:Height=\"18\">"
            (volxml:cel "Tt" "String" "TOTAL" nil)
            (volxml:cel "Tn" "Number" (volxml:num totC)
                        (strcat "=SUM(R[-" (itoa n) "]C:R[-1]C)"))
            (volxml:cel "Tn" "Number" (volxml:num totA)
                        (strcat "=SUM(R[-" (itoa n) "]C:R[-1]C)"))
            (volxml:cel "Tl" "Number" (volxml:num (- totA totC)) "=RC[-1]-RC[-2]")
            "</Row>")
    f)

  ;; Fim: impressao em A4 paisagem, 1 pagina de largura; congela ate o cabecalho
  (foreach l
    (list "</Table>"
          "<WorksheetOptions xmlns=\"urn:schemas-microsoft-com:office:excel\">"
          "<PageSetup><Layout x:Orientation=\"Landscape\" x:CenterHorizontal=\"1\"/></PageSetup>"
          "<FitToPage/>"
          "<Print><FitHeight>0</FitHeight><ValidPrinterInfo/><PaperSizeIndex>9</PaperSizeIndex></Print>"
          "<FreezePanes/><FrozenNoSplit/>"
          "<SplitHorizontal>5</SplitHorizontal><TopRowBottomPane>5</TopRowBottomPane>"
          "<ActivePane>2</ActivePane>"
          "</WorksheetOptions>"
          "</Worksheet>"
          "</Workbook>")
    (write-line l f))
  (list totC totA)
)

(defun c:VOLXLS ( / ss dados lista ignoradas arq f tot abrir)
  (princ "\nSelecione as superficies de volume: ")
  (setq ss (ssget '((0 . "AECC_*SURFACE*"))))
  (cond
    ((not ss)
     (princ "\nNenhuma superficie selecionada."))
    ((not (car (setq dados (volcsv:coletar ss))))
     (princ "\nNenhuma das superficies selecionadas e de volume."))
    ((not (setq arq (getfiled "Salvar planilha de volumes (abre no Excel)"
                              (strcat (getvar "DWGPREFIX")
                                      (vl-filename-base (getvar "DWGNAME")) "_volumes.xml")
                              "xml" 1)))
     (princ "\nCancelado."))
    ((not (setq f (open arq "w")))
     (princ (strcat "\nNao foi possivel gravar: " arq
                    " (o arquivo esta aberto no Excel?)")))
    (T
     (setq lista     (car dados)
           ignoradas (cadr dados)
           tot       (volxml:gravar f lista))
     (close f)
     (princ (strcat "\nSuperficies exportadas: " (itoa (length lista))))
     (if (> ignoradas 0)
       (princ (strcat "  |  Ignoradas (nao sao de volume): " (itoa ignoradas))))
     (princ (strcat "\nCorte total:  " (rtos (car tot) 2 *volcsv-casas*)
                    "\nAterro total: " (rtos (cadr tot) 2 *volcsv-casas*)
                    "\nArquivo: " arq))
     (initget "Sim Nao")
     (setq abrir (getkword "\nAbrir a planilha agora? [Sim/Nao] <Sim>: "))
     (if (/= abrir "Nao")
       (startapp "explorer" (strcat "\"" arq "\"")))))
  (princ)
)

(princ "\nvolumes_csv.lsp carregado. Comandos: VOLCSV, VOLXLS")
(princ)
