;;; ============================================================
;;; max_corte_aterro.lsp - Localiza o ponto de MAIOR CORTE e de
;;;                        MAIOR ATERRO e cria labels com as cotas
;;;
;;; Comando:
;;;   MAXCA - Selecione uma superficie:
;;;     * Superficie de VOLUME (TIN Volume Surface): resultado
;;;       exato. A "cota" da superficie de volume em cada vertice e
;;;       a diferenca (comparacao - base); o menor valor e o maior
;;;       corte e o maior valor e o maior aterro.
;;;     * Superficie TIN comum (projeto): a LISP pede o terreno de
;;;       referencia e compara as cotas nos vertices das duas
;;;       superficies (diferenca = projeto - terreno).
;;;   Em cada ponto e criada uma label (multileader) com o corte ou
;;;   aterro e as cotas de projeto e terreno.
;;;
;;; Obs.: as labels sao texto fixo. Se as superficies mudarem,
;;; apague as labels (camada CORTE-ATERRO) e rode de novo.
;;;
;;; Como carregar: APPLOAD -> selecione este arquivo
;;; ============================================================

(vl-load-com)

;;; Configuracoes - altere se quiser
(setq *mca-casas*   3              ; casas decimais
      *mca-decimal* ","            ; separador decimal na label
      *mca-camada*  "CORTE-ATERRO" ; camada das labels
      *mca-altura*  nil)           ; altura do texto (nil = pergunta)

;;; ------------------------------------------------------------
;;; Utilitarios
;;; ------------------------------------------------------------

;;; Numero -> texto (mantem zeros finais e usa o separador configurado)
(defun mca:num (x / s dz)
  (setq dz (getvar "DIMZIN"))
  (setvar "DIMZIN" 0)
  (setq s (rtos x 2 *mca-casas*))
  (setvar "DIMZIN" dz)
  (if (/= *mca-decimal* ".")
    (while (vl-string-search "." s)
      (setq s (vl-string-subst *mca-decimal* "." s))))
  s
)

;;; Nome da superficie (ou "?")
(defun mca:nome (obj / n)
  (setq n (vl-catch-all-apply 'vlax-get (list obj 'Name)))
  (if (vl-catch-all-error-p n) "?" n)
)

;;; Cota da superficie em (x y), ou nil se estiver fora dela
(defun mca:cota (obj x y / z)
  (setq z (vl-catch-all-apply 'vlax-invoke-method (list obj 'FindElevationAtXY x y)))
  (if (and (not (vl-catch-all-error-p z)) (numberp z)) z)
)

;;; T se for superficie de volume (tem volume de corte nas estatisticas)
(defun mca:volume-p (obj / st c)
  (setq st (vl-catch-all-apply 'vlax-get (list obj 'Statistics)))
  (and (not (vl-catch-all-error-p st))
       st
       (not (vl-catch-all-error-p
              (setq c (vl-catch-all-apply 'vlax-get (list st 'CutVolume)))))
       (numberp c))
)

;;; Base e comparacao de uma superficie de volume: (base . comparacao),
;;; ou nil se a API nao fornecer.
(defun mca:base-comparacao (obj / b c)
  (setq b (vl-catch-all-apply 'vlax-get (list obj 'BaseSurface))
        c (vl-catch-all-apply 'vlax-get (list obj 'ComparisonSurface)))
  (if (and (not (vl-catch-all-error-p b)) (not (vl-catch-all-error-p c))
           (= (type b) 'VLA-OBJECT) (= (type c) 'VLA-OBJECT))
    (cons b c))
)

;;; ------------------------------------------------------------
;;; Vertices da superficie: lista de (x y z)
;;; Usa a propriedade Points; se nao existir, OutputTriangles
;;; (vertices dos triangulos, com repeticoes - nao afeta o resultado).
;;; ------------------------------------------------------------
(defun mca:vertices (obj / l res)
  (foreach prop '(Points OutputTriangles)
    (if (not res)
      (progn
        (setq l (vl-catch-all-apply 'vlax-get (list obj prop)))
        (if (and (not (vl-catch-all-error-p l)) (listp l) l)
          (setq res (mca:triplas l))))))
  res
)

;;; Aceita lista plana (x y z x y z ...) ou lista de pontos ((x y z) ...)
(defun mca:triplas (l / res)
  (if (listp (car l))
    (foreach p l
      (if (>= (length p) 3) (setq res (cons (list (car p) (cadr p) (caddr p)) res))))
    (while (cddr l)
      (setq res (cons (list (car l) (cadr l) (caddr l)) res)
            l   (cdddr l))))
  res
)

;;; ------------------------------------------------------------
;;; Busca dos extremos
;;; Cada resultado: (x y dif cota-projeto cota-terreno)
;;; Retorna (minimo maximo)
;;; ------------------------------------------------------------

;;; Superficie de volume: dif = z do vertice
(defun mca:extremos-volume (obj / vs bc mn mx)
  (setq vs (mca:vertices obj))
  (foreach v vs
    (if (or (not mn) (< (caddr v) (caddr mn))) (setq mn v))
    (if (or (not mx) (> (caddr v) (caddr mx))) (setq mx v)))
  (if (and mn mx)
    (progn
      ;; cotas de projeto (comparacao) e terreno (base), se disponiveis
      (setq bc (mca:base-comparacao obj))
      (list (mca:completar mn bc) (mca:completar mx bc))))
)

(defun mca:completar (v bc)
  (list (car v) (cadr v) (caddr v)
        (if bc (mca:cota (cdr bc) (car v) (cadr v)))
        (if bc (mca:cota (car bc) (car v) (cadr v))))
)

;;; Atualiza (minimo maximo) com o resultado r = (x y dif zp zt)
(defun mca:atualizar (ext r)
  (cond
    ((not ext) (list r r))
    (T (list (if (< (caddr r) (caddr (car ext))) r (car ext))
             (if (> (caddr r) (caddr (cadr ext))) r (cadr ext)))))
)

;;; Duas superficies TIN: compara nos vertices de ambas
(defun mca:extremos-par (proj terr / ext zo n)
  (setq n 0)
  (princ "\nLendo vertices do projeto...")
  (foreach v (mca:vertices proj)
    (if (setq zo (mca:cota terr (car v) (cadr v)))
      (setq ext (mca:atualizar ext (list (car v) (cadr v) (- (caddr v) zo) (caddr v) zo))))
    (if (= 0 (rem (setq n (1+ n)) 5000)) (princ ".")))
  (princ "\nLendo vertices do terreno...")
  (foreach v (mca:vertices terr)
    (if (setq zo (mca:cota proj (car v) (cadr v)))
      (setq ext (mca:atualizar ext (list (car v) (cadr v) (- zo (caddr v)) zo (caddr v)))))
    (if (= 0 (rem (setq n (1+ n)) 5000)) (princ ".")))
  ext
)

;;; ------------------------------------------------------------
;;; Escolha de superficies
;;; ------------------------------------------------------------

(defun mca:superficies ( / ss i obj res)
  (if (setq ss (ssget "_X" '((0 . "AECC_*SURFACE*"))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (setq obj (vlax-ename->vla-object (ssname ss i))
              res (cons (cons (mca:nome obj) obj) res)
              i   (1+ i)))))
  (vl-sort res '(lambda (a b) (< (strcase (car a)) (strcase (car b)))))
)

(defun mca:escolher (titulo lista padrao / i pos sel e obj)
  (princ (strcat "\n--- " titulo " ---"))
  (setq i 1)
  (foreach s lista
    (princ (strcat "\n  " (itoa i) " - " (car s)
                   (if (mca:volume-p (cdr s)) "  [volume]" "")))
    (if (and padrao (= (car s) padrao)) (setq pos i))
    (setq i (1+ i)))
  (initget 6 "Selecionar")
  (setq sel (getint (strcat "\nNumero da superficie ou [Selecionar na tela]"
                            (if pos (strcat " <" (itoa pos) ">") "") ": ")))
  (cond
    ((= sel "Selecionar")
     (if (and (setq e (car (entsel "\nClique na superficie: ")))
              (wcmatch (cdr (assoc 0 (entget e))) "AECC_*SURFACE*"))
       (progn (setq obj (vlax-ename->vla-object e)) (cons (mca:nome obj) obj))
       (progn (princ "\nO objeto selecionado nao e uma superficie.") nil)))
    ((and (not sel) pos) (nth (1- pos) lista))
    ((and (numberp sel) (<= sel (length lista))) (nth (1- sel) lista))
    (T (princ "\nOpcao invalida.") nil))
)

;;; ------------------------------------------------------------
;;; Labels
;;; ------------------------------------------------------------

(defun mca:camada (nome)
  (if (not (tblsearch "LAYER" nome))
    (entmake (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord")
                   '(100 . "AcDbLayerTableRecord") (cons 2 nome) '(70 . 0) '(62 . 7))))
  nome
)

;;; Texto MText. cor: 1 = vermelho (corte), 5 = azul (aterro)
(defun mca:texto (titulo cor r nproj nterr / d)
  (setq d (caddr r))
  (strcat "{\\C" (itoa cor) ";\\L" titulo "\\l}"
          "\\P" (if (>= d 0.0) "Aterro" "Corte") " = " (mca:num (abs d)) " m"
          (if (nth 3 r) (strcat "\\PCota " nproj ": " (mca:num (nth 3 r))) "")
          (if (nth 4 r) (strcat "\\PCota " nterr ": " (mca:num (nth 4 r))) ""))
)

;;; Multileader com seta no ponto e texto deslocado (se falhar, MText)
(defun mca:label (ms r txt h / p1 p2 arr ml)
  (setq p1 (list (car r) (cadr r) 0.0)
        p2 (list (+ (car r) (* 4.0 h)) (+ (cadr r) (* 4.0 h)) 0.0)
        arr (vlax-make-safearray vlax-vbDouble '(0 . 5)))
  (vlax-safearray-fill arr (append p1 p2))
  (setq ml (vl-catch-all-apply 'vla-AddMLeader (list ms (vlax-make-variant arr) 0)))
  (if (not (vl-catch-all-error-p ml))
    (progn
      (vla-put-TextString ml txt)
      (vl-catch-all-apply 'vla-put-TextHeight (list ml h))
      (vla-put-Layer ml *mca-camada*))
    (entmake (list '(0 . "MTEXT") '(100 . "AcDbEntity") (cons 8 *mca-camada*)
                   '(100 . "AcDbMText") (cons 10 p2) (cons 40 h) '(71 . 7) (cons 1 txt))))
)

;;; ------------------------------------------------------------
;;; Comando
;;; ------------------------------------------------------------

(defun c:MAXCA ( / doc ms lista sup terr proj ext mn mx nproj nterr bc h)
  (setq doc   (vla-get-ActiveDocument (vlax-get-acad-object))
        ms    (vla-get-ModelSpace doc)
        lista (mca:superficies))
  (cond
    ((not lista) (princ "\nNenhuma superficie no desenho."))
    ((not (setq sup (mca:escolher "Superficie (de volume, ou TIN de projeto)"
                                  lista *mca-ultima-sup*))))
    (T
     (setq *mca-ultima-sup* (car sup))
     (if (mca:volume-p (cdr sup))
       ;; --- Superficie de volume ---
       (progn
         (princ (strcat "\nAnalisando a superficie de volume " (car sup) "..."))
         (setq ext (mca:extremos-volume (cdr sup))
               bc  (mca:base-comparacao (cdr sup)))
         ;; Se a API nao informar base/comparacao, pergunta (para as cotas)
         (if (and ext (not bc))
           (progn
             (princ "\nPara mostrar as cotas, informe as superficies usadas no volume.")
             (if (and (setq terr (mca:escolher "Superficie BASE (terreno)" lista nil))
                      (setq proj (mca:escolher "Superficie de COMPARACAO (projeto)" lista nil)))
               (setq bc  (cons (cdr terr) (cdr proj))
                     ext (list (mca:completar (car ext) bc)
                               (mca:completar (cadr ext) bc))))))
         (setq nproj (if bc (mca:nome (cdr bc)) "projeto")
               nterr (if bc (mca:nome (car bc)) "terreno")))
       ;; --- Duas superficies TIN ---
       (if (setq terr (mca:escolher "Superficie de REFERENCIA (terreno natural)"
                                    lista *mca-ultima-terr*))
         (if (= (car terr) (car sup))
           (princ "\nEscolha duas superficies diferentes.")
           (progn
             (setq *mca-ultima-terr* (car terr)
                   nproj (car sup)
                   nterr (car terr)
                   ext   (mca:extremos-par (cdr sup) (cdr terr)))))))

     (cond
       ((not ext)
        (princ "\nNao foi possivel ler os vertices ou as superficies nao se sobrepoem."))
       (T
        (setq mn (car ext) mx (cadr ext))
        (if (not *mca-altura*) (setq *mca-altura* 1.0))
        (initget 6)
        (if (setq h (getdist (strcat "\nAltura do texto <" (rtos *mca-altura* 2 2) ">: ")))
          (setq *mca-altura* h))
        (mca:camada *mca-camada*)

        ;; Maior corte = menor diferenca (negativa)
        (if (< (caddr mn) 0.0)
          (progn
            (mca:label ms mn (mca:texto "MAIOR CORTE" 1 mn nproj nterr) *mca-altura*)
            (princ (strcat "\nMaior corte:  " (mca:num (abs (caddr mn))) " m  em  E="
                           (mca:num (car mn)) "  N=" (mca:num (cadr mn)))))
          (princ "\nNao ha corte (a superficie nao fica abaixo da referencia)."))

        ;; Maior aterro = maior diferenca (positiva)
        (if (> (caddr mx) 0.0)
          (progn
            (mca:label ms mx (mca:texto "MAIOR ATERRO" 5 mx nproj nterr) *mca-altura*)
            (princ (strcat "\nMaior aterro: " (mca:num (caddr mx)) " m  em  E="
                           (mca:num (car mx)) "  N=" (mca:num (cadr mx)))))
          (princ "\nNao ha aterro (a superficie nao fica acima da referencia)."))
        (princ (strcat "\nLabels na camada " *mca-camada* "."))))))
  (princ)
)

(princ "\nmax_corte_aterro.lsp carregado. Comando: MAXCA")
(princ)
