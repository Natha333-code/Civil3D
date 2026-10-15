;;; ============================================================
;;; diferenca_cotas.lsp - Label de diferenca de cotas entre duas
;;;                       superficies do Civil 3D
;;;
;;; Comando:
;;;   DIFCOTA - Escolha a superficie de calculo e a superficie de
;;;             referencia; depois clique nos pontos. Em cada ponto
;;;             e criada uma label (multileader) com:
;;;               Dh  = cota da superficie - cota da referencia
;;;               cota da superficie e cota da referencia (opcional)
;;;             Dh positivo: superficie ACIMA da referencia.
;;;
;;; Obs.: a label e um texto fixo (nao atualiza se as superficies
;;; mudarem). Rode o comando de novo apos alterar as superficies.
;;;
;;; Como carregar: APPLOAD -> selecione este arquivo
;;; ============================================================

(vl-load-com)

;;; Configuracoes - altere se quiser
(setq *difcota-casas*    3      ; casas decimais
      *difcota-decimal*  ","    ; separador decimal na label
      *difcota-cotas*    T      ; T = mostra tambem as duas cotas
      *difcota-cores*    T      ; T = Dh positivo em verde, negativo em vermelho
      *difcota-camada*   "DIF-COTAS"
      *difcota-altura*   nil)   ; altura do texto (nil = pergunta na 1a vez)

;;; ------------------------------------------------------------
;;; Superficies
;;; ------------------------------------------------------------

;;; Lista de (nome . vla-object) de todas as superficies do desenho
(defun difcota:superficies ( / ss i obj nome res)
  (if (setq ss (ssget "_X" '((0 . "AECC_*SURFACE*"))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (setq obj  (vlax-ename->vla-object (ssname ss i))
              nome (vl-catch-all-apply 'vlax-get (list obj 'Name)))
        (if (not (vl-catch-all-error-p nome))
          (setq res (cons (cons nome obj) res)))
        (setq i (1+ i)))))
  (vl-sort res '(lambda (a b) (< (strcase (car a)) (strcase (car b)))))
)

;;; Pede para o usuario escolher uma superficie da lista (numero),
;;; ou clicar nela na tela. padrao = nome sugerido (ou nil).
(defun difcota:escolher (titulo lista padrao / i n pos sel e obj nome)
  (princ (strcat "\n--- " titulo " ---"))
  (setq i 1)
  (foreach s lista
    (princ (strcat "\n  " (itoa i) " - " (car s)))
    (if (and padrao (= (car s) padrao)) (setq pos i))
    (setq i (1+ i)))
  (setq n (length lista))
  (initget 6 "Selecionar")
  (setq sel (getint (strcat "\nNumero da superficie ou [Selecionar na tela]"
                            (if pos (strcat " <" (itoa pos) ">") "") ": ")))
  (cond
    ((= sel "Selecionar")
     (if (and (setq e (car (entsel "\nClique na superficie: ")))
              (wcmatch (cdr (assoc 0 (entget e))) "AECC_*SURFACE*"))
       (progn
         (setq obj  (vlax-ename->vla-object e)
               nome (vlax-get obj 'Name))
         (cons nome obj))
       (progn (princ "\nO objeto selecionado nao e uma superficie.") nil)))
    ((and (not sel) pos) (nth (1- pos) lista))
    ((and sel (<= sel n)) (nth (1- sel) lista))
    (T (princ "\nOpcao invalida.") nil))
)

;;; Cota da superficie em (x y), ou nil se o ponto estiver fora dela
(defun difcota:cota (obj x y / z)
  (setq z (vl-catch-all-apply 'vlax-invoke-method
                              (list obj 'FindElevationAtXY x y)))
  (if (and (not (vl-catch-all-error-p z)) (numberp z)) z)
)

;;; ------------------------------------------------------------
;;; Texto da label
;;; ------------------------------------------------------------

;;; Numero -> texto com casas e separador decimal configurados
(defun difcota:num (x / s dz)
  (setq dz (getvar "DIMZIN"))
  (setvar "DIMZIN" 0)                    ; mantem zeros finais (0,500)
  (setq s (rtos x 2 *difcota-casas*))
  (setvar "DIMZIN" dz)
  (if (/= *difcota-decimal* ".")
    (while (vl-string-search "." s)
      (setq s (vl-string-subst *difcota-decimal* "." s))))
  s
)

;;; Texto MText da label. \U+0394 = letra grega delta.
(defun difcota:texto (dh z1 z2 nome1 nome2 / sinal linha)
  ;; evita "-0,000" quando a diferenca arredonda para zero
  (if (< (abs dh) (* 0.5 (expt 10.0 (- *difcota-casas*)))) (setq dh 0.0))
  (setq sinal (if (>= dh 0.0) "+" "")
        linha (strcat "\\U+0394h = " sinal (difcota:num dh) " m"))
  (if *difcota-cores*
    (setq linha (strcat "{\\C" (if (>= dh 0.0) "3" "1") ";" linha "}")))
  (if *difcota-cotas*
    (strcat linha
            "\\P" nome1 ": " (difcota:num z1)
            "\\P" nome2 ": " (difcota:num z2))
    linha)
)

;;; ------------------------------------------------------------
;;; Criacao da label
;;; ------------------------------------------------------------

(defun difcota:camada (nome)
  (if (not (tblsearch "LAYER" nome))
    (entmake (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord")
                   '(100 . "AcDbLayerTableRecord") (cons 2 nome) '(70 . 0) '(62 . 7))))
  nome
)

;;; Multileader de p1 (seta) ate p2 (texto). Se falhar, cria MText.
(defun difcota:label (ms p1 p2 txt h / arr ml r)
  (setq arr (vlax-make-safearray vlax-vbDouble '(0 . 5)))
  (vlax-safearray-fill arr (list (car p1) (cadr p1) 0.0 (car p2) (cadr p2) 0.0))
  (setq ml (vl-catch-all-apply 'vla-AddMLeader (list ms (vlax-make-variant arr) 0)))
  (if (not (vl-catch-all-error-p ml))
    (progn
      (vla-put-TextString ml txt)
      (vl-catch-all-apply 'vla-put-TextHeight (list ml h))
      (vla-put-Layer ml *difcota-camada*)
      ml)
    (progn
      (entmake (list '(0 . "MTEXT") '(100 . "AcDbEntity") (cons 8 *difcota-camada*)
                     '(100 . "AcDbMText") (cons 10 (list (car p2) (cadr p2) 0.0))
                     (cons 40 h) '(71 . 7) (cons 1 txt)))
      (entlast)))
)

;;; ------------------------------------------------------------
;;; Comando
;;; ------------------------------------------------------------

(defun c:DIFCOTA ( / doc ms lista sup ref p pw p2 z1 z2 dh h n)
  (setq doc   (vla-get-ActiveDocument (vlax-get-acad-object))
        ms    (vla-get-ModelSpace doc)
        lista (difcota:superficies))
  (cond
    ((< (length lista) 2)
     (princ "\nO desenho precisa ter pelo menos 2 superficies."))
    ((not (setq sup (difcota:escolher "Superficie a medir (ex.: projeto)"
                                      lista *difcota-ultima-sup*))))
    ((not (setq ref (difcota:escolher "Superficie de REFERENCIA (ex.: terreno natural)"
                                      lista *difcota-ultima-ref*))))
    ((= (car sup) (car ref))
     (princ "\nEscolha duas superficies diferentes."))
    (T
     (setq *difcota-ultima-sup* (car sup)
           *difcota-ultima-ref* (car ref))
     (princ (strcat "\nDh = " (car sup) " - " (car ref)
                    "  (positivo = " (car sup) " acima da referencia)"))

     ;; Altura do texto
     (if (not *difcota-altura*) (setq *difcota-altura* 1.0))
     (initget 6)
     (if (setq h (getdist (strcat "\nAltura do texto <" (rtos *difcota-altura* 2 2) ">: ")))
       (setq *difcota-altura* h))
     (difcota:camada *difcota-camada*)

     ;; Pontos
     (setq n 0)
     (while (setq p (getpoint "\nClique no ponto da superficie (Enter para sair): "))
       (setq pw (trans p 1 0)
             z1 (difcota:cota (cdr sup) (car pw) (cadr pw))
             z2 (difcota:cota (cdr ref) (car pw) (cadr pw)))
       (cond
         ((not z1) (princ (strcat "\nPonto fora da superficie " (car sup) ".")))
         ((not z2) (princ (strcat "\nPonto fora da superficie " (car ref) ".")))
         (T
          (setq dh (- z1 z2))
          (princ (strcat "\n" (car sup) ": " (difcota:num z1) "  |  "
                         (car ref) ": " (difcota:num z2) "  |  Dh = "
                         (if (>= dh 0.0) "+" "") (difcota:num dh)))
          (setq p2 (getpoint p "\nPosicao da label <ao lado>: "))
          (setq p2 (if p2
                     (trans p2 1 0)
                     (list (+ (car pw) (* 3.0 *difcota-altura*))
                           (+ (cadr pw) (* 3.0 *difcota-altura*)))))
          (difcota:label ms pw p2
                         (difcota:texto dh z1 z2 (car sup) (car ref))
                         *difcota-altura*)
          (setq n (1+ n)))))
     (princ (strcat "\n" (itoa n) " label(s) criada(s) na camada " *difcota-camada* "."))))
  (princ)
)

(princ "\ndiferenca_cotas.lsp carregado. Comando: DIFCOTA")
(princ)
