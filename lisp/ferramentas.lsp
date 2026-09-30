;;; ============================================================
;;; ferramentas.lsp - Rotinas AutoLISP para AutoCAD / Civil 3D
;;;
;;; Comandos:
;;;   SOMACOMP   - Soma o comprimento de linhas, polilinhas, arcos etc.
;;;   ANOTACOORD - Clica em pontos e escreve E / N / Z como MTEXT
;;;
;;; Como carregar: APPLOAD -> selecione este arquivo
;;; (Obs.: strings sem acento para evitar problemas de codificacao)
;;; ============================================================

(vl-load-com)

;;; ------------------------------------------------------------
;;; SOMACOMP - soma de comprimentos
;;; ------------------------------------------------------------
(defun c:SOMACOMP ( / ss i ent total)
  (princ "\nSelecione linhas, polilinhas, arcos, circulos ou splines: ")
  (if (setq ss (ssget '((0 . "LINE,ARC,CIRCLE,LWPOLYLINE,POLYLINE,SPLINE,ELLIPSE"))))
    (progn
      (setq total 0.0
            i     0)
      (repeat (sslength ss)
        (setq ent   (ssname ss i)
              total (+ total
                       (vlax-curve-getDistAtParam ent (vlax-curve-getEndParam ent)))
              i     (1+ i))
      )
      (princ (strcat "\nObjetos: " (itoa (sslength ss))
                     "  |  Comprimento total: " (rtos total 2 3)))
    )
    (princ "\nNenhum objeto selecionado.")
  )
  (princ)
)

;;; ------------------------------------------------------------
;;; ANOTACOORD - anota coordenadas E / N / Z
;;; ------------------------------------------------------------
(if (not *anotacoord-altura*) (setq *anotacoord-altura* 1.0))

(defun c:ANOTACOORD ( / h pt ptw txt)
  (setq h (getdist (strcat "\nAltura do texto <" (rtos *anotacoord-altura* 2 2) ">: ")))
  (if h (setq *anotacoord-altura* h))
  (while (setq pt (getpoint "\nClique no ponto (Enter para sair): "))
    (setq ptw (trans pt 1 0)   ; UCS atual -> WCS (coordenadas reais)
          txt (strcat "E= "  (rtos (car ptw) 2 3)
                      "\\PN= " (rtos (cadr ptw) 2 3)
                      "\\PZ= " (rtos (caddr ptw) 2 3)))
    (entmake
      (list '(0 . "MTEXT")
            '(100 . "AcDbEntity")
            '(100 . "AcDbMText")
            (cons 10 ptw)
            (cons 40 *anotacoord-altura*)
            '(71 . 7)                 ; justificacao: inferior esquerda
            (cons 1 txt)))
  )
  (princ)
)

(princ "\nferramentas.lsp carregado. Comandos: SOMACOMP, ANOTACOORD")
(princ)
