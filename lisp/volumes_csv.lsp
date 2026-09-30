;;; ============================================================
;;; volumes_csv.lsp - Exporta volumes de superficies de volume
;;;                   (TIN Volume Surface) do Civil 3D para CSV
;;;
;;; Comando:
;;;   VOLCSV - Selecione as superficies de volume; gera um .csv
;;;            com Corte, Aterro e Liquido de cada superficie e
;;;            o TOTAL (somatorio) no final.
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

(defun c:VOLCSV ( / ss i dados lista ignoradas arq f totC totA linha)
  (princ "\nSelecione as superficies de volume: ")
  (setq ss (ssget '((0 . "AECC_*SURFACE*"))))
  (if (not ss)
    (progn (princ "\nNenhuma superficie selecionada.") (exit)))

  ;; Coleta dados
  (setq i 0 ignoradas 0)
  (repeat (sslength ss)
    (if (setq dados (volcsv:dados (ssname ss i)))
      (setq lista (cons dados lista))
      (setq ignoradas (1+ ignoradas)))
    (setq i (1+ i)))
  (setq lista (reverse lista))

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

(princ "\nvolumes_csv.lsp carregado. Comando: VOLCSV")
(princ)
