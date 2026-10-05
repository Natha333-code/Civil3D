;;; ============================================================
;;; imagem_satelite.lsp - Insere imagem de satelite georreferenciada
;;;                       no Civil 3D, recortada por pontos
;;;
;;; Comando:
;;;   IMGSAT - Define um poligono de recorte (pontos COGO/pontos/
;;;            blocos, polilinha ou cliques), baixa a imagem de
;;;            satelite dessa area JA no sistema de coordenadas do
;;;            desenho (ex.: SIRGAS 2000 / UTM 23S), insere como
;;;            imagem raster na posicao correta e recorta pelo
;;;            poligono.
;;;
;;; Fonte da imagem: Esri World Imagery (servico "export" do
;;; ArcGIS Online), que devolve a imagem ja projetada no codigo
;;; EPSG informado. Verifique os termos de uso da Esri para o
;;; seu caso (uso comercial pode exigir conta ArcGIS).
;;;
;;; Requisitos: internet; Windows 10/11 (usa curl.exe ou PowerShell
;;; para baixar); desenho em metros com coordenadas reais (UTM).
;;;
;;; Como carregar: APPLOAD -> selecione este arquivo
;;; ============================================================

(vl-load-com)

;;; Configuracoes - altere se quiser
(setq *imgsat-res-padrao* 0.5        ; resolucao padrao (metros por pixel)
      *imgsat-margem*     20.0       ; margem em volta do poligono (m)
      *imgsat-max-px*     4096       ; limite de pixels do servico por lado
      *imgsat-camada*     "SATELITE" ; camada da imagem
      *imgsat-url*        (strcat "https://services.arcgisonline.com/ArcGIS/rest/services/"
                                  "World_Imagery/MapServer/export"))

;;; ------------------------------------------------------------
;;; Sistema de coordenadas (codigo EPSG)
;;; ------------------------------------------------------------

(defun imgsat:digito-p (c) (and (>= (ascii c) 48) (<= (ascii c) 57)))
(defun imgsat:letra-p (c)  (and (>= (ascii (strcase c)) 65) (<= (ascii (strcase c)) 90)))

;;; Procura o fuso UTM no nome do sistema (ex.: "SIRGAS2000.UTM-23S",
;;; "UTM84-23S"). Retorna (zona "S"/"N") ou nil.
(defun imgsat:fuso (cs / i n c ini res)
  (setq cs (strcase cs) n (strlen cs) i 2)
  (while (<= i n)
    (setq c (substr cs i 1))
    (if (and (member c '("S" "N"))
             (imgsat:digito-p (substr cs (1- i) 1))
             (or (= i n) (not (imgsat:letra-p (substr cs (1+ i) 1)))))
      (progn
        (setq ini (1- i))
        (if (and (> ini 1) (imgsat:digito-p (substr cs (1- ini) 1)))
          (setq ini (1- ini)))
        (if (or (= ini 1) (not (imgsat:digito-p (substr cs (1- ini) 1))))
          (setq res (list (atoi (substr cs ini (- i ini))) c)))))
    (setq i (1+ i)))
  (if (and res (<= 1 (car res) 60)) res)
)

;;; Tenta descobrir o EPSG pelo sistema de coordenadas do desenho
;;; (Configuracoes do desenho do Civil 3D / variavel CGEOCS).
(defun imgsat:epsg-auto ( / cs f z s)
  (setq cs (getvar "CGEOCS"))
  (if (and cs (/= cs "") (setq f (imgsat:fuso cs)))
    (progn
      (setq cs (strcase cs) z (car f) s (= (cadr f) "S"))
      (cond
        ((vl-string-search "SIRGAS" cs) (if s (+ 31960 z) (+ 31954 z)))
        ((or (vl-string-search "SAD69" cs) (vl-string-search "SAD-69" cs))
         (if s (+ 29170 z) (+ 29150 z)))
        ((or (vl-string-search "CORREGO" cs) (vl-string-search "COA" cs))
         (if s (+ 22500 z)))
        ((or (vl-string-search "WGS84" cs) (vl-string-search "UTM84" cs)
             (vl-string-search "WGS 84" cs))
         (if s (+ 32700 z) (+ 32600 z)))))))

;;; ------------------------------------------------------------
;;; Poligono de recorte
;;; ------------------------------------------------------------

;;; Remove pontos repetidos em sequencia (e o ultimo se = primeiro)
(defun imgsat:limpar (pts / res)
  (foreach p pts
    (if (or (not res) (> (distance p (car res)) 1e-6))
      (setq res (cons p res))))
  (setq res (reverse res))
  (if (and (> (length res) 1) (< (distance (car res) (last res)) 1e-6))
    (setq res (reverse (cdr (reverse res)))))
  res
)

;;; Remove pontos duplicados em qualquer posicao da lista
(defun imgsat:unicos (pts / res)
  (foreach p pts
    (if (not (vl-some '(lambda (q) (< (distance p q) 1e-6)) res))
      (setq res (cons p res))))
  (reverse res)
)

;;; Ordena pontos pelo angulo em torno do centroide
(defun imgsat:ordenar (pts / cx cy cen)
  (setq cx  (/ (apply '+ (mapcar 'car pts)) (length pts))
        cy  (/ (apply '+ (mapcar 'cadr pts)) (length pts))
        cen (list cx cy))
  (vl-sort pts '(lambda (a b) (< (angle cen a) (angle cen b))))
)

;;; Coordenada (x y) em WCS de um ponto COGO, POINT ou bloco
(defun imgsat:coord (e / obj ed tipo x y)
  (setq ed (entget e) tipo (cdr (assoc 0 ed)))
  (cond
    ((= tipo "AECC_COGO_POINT")
     (setq obj (vlax-ename->vla-object e)
           x   (vl-catch-all-apply 'vlax-get (list obj 'Easting))
           y   (vl-catch-all-apply 'vlax-get (list obj 'Northing)))
     (if (or (vl-catch-all-error-p x) (vl-catch-all-error-p y))
       nil
       (list x y)))
    ((= tipo "INSERT")
     (setq x (trans (cdr (assoc 10 ed)) e 0))
     (list (car x) (cadr x)))
    (T
     (setq x (cdr (assoc 10 ed)))
     (list (car x) (cadr x))))
)

(defun imgsat:por-pontos ( / ss i p pts)
  (princ "\nSelecione os pontos (COGO, pontos ou blocos): ")
  (if (setq ss (ssget '((0 . "AECC_COGO_POINT,POINT,INSERT"))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (if (setq p (imgsat:coord (ssname ss i))) (setq pts (cons p pts)))
        (setq i (1+ i)))
      (setq pts (imgsat:unicos pts))
      (if (>= (length pts) 3)
        (progn
          (princ (strcat "\n" (itoa (length pts)) " pontos. Ordenados em volta do centro"
                         " (para areas muito concavas, use Polilinha ou Clicar)."))
          (imgsat:ordenar pts))
        (progn (princ "\nSao necessarios pelo menos 3 pontos.") nil))))
)

(defun imgsat:por-polilinha ( / sel e fim i pts p)
  (setq sel (entsel "\nSelecione a polilinha de recorte: "))
  (if (and sel
           (wcmatch (cdr (assoc 0 (entget (setq e (car sel))))) "LWPOLYLINE,POLYLINE"))
    (progn
      (setq fim (fix (+ 0.5 (vlax-curve-getEndParam e))) i 0)
      (while (<= i fim)
        (setq p   (vlax-curve-getPointAtParam e i)
              pts (cons (list (car p) (cadr p)) pts)
              i   (1+ i)))
      (imgsat:limpar (reverse pts)))
    (progn (princ "\nNenhuma polilinha selecionada.") nil))
)

(defun imgsat:por-cliques ( / p ant pts)
  (princ "\nClique os vertices do recorte em ordem (Enter para terminar).")
  (while (setq p (if ant
                   (getpoint ant "\nProximo vertice <terminar>: ")
                   (getpoint "\nPrimeiro vertice: ")))
    (if ant (grdraw ant p 1 1))
    (setq ant p
          p   (trans p 1 0)
          pts (cons (list (car p) (cadr p)) pts)))
  (redraw)
  (setq pts (imgsat:limpar (reverse pts)))
  (if (>= (length pts) 3) pts (progn (princ "\nSao necessarios pelo menos 3 vertices.") nil))
)

;;; ------------------------------------------------------------
;;; Area da imagem: retangulo envolvente + margem, ajustado para
;;; que largura/altura sejam multiplos exatos do tamanho do pixel.
;;; Retorna (xmin ymin xmax ymax res largura_px altura_px)
;;; ------------------------------------------------------------
(defun imgsat:extensao (pts margem res maxpx / xs ys x1 y1 x2 y2 dx dy w h cx cy)
  (setq xs (mapcar 'car pts) ys (mapcar 'cadr pts)
        x1 (- (apply 'min xs) margem) x2 (+ (apply 'max xs) margem)
        y1 (- (apply 'min ys) margem) y2 (+ (apply 'max ys) margem)
        dx (- x2 x1) dy (- y2 y1))
  (if (> (/ (max dx dy) res) maxpx)
    (setq res (/ (max dx dy) maxpx)))
  (setq w  (fix (+ (/ dx res) 0.999999))
        h  (fix (+ (/ dy res) 0.999999))
        w  (min (max w 1) maxpx)
        h  (min (max h 1) maxpx)
        cx (/ (+ x1 x2) 2.0)
        cy (/ (+ y1 y2) 2.0)
        dx (* w res)
        dy (* h res))
  (list (- cx (/ dx 2.0)) (- cy (/ dy 2.0)) (+ cx (/ dx 2.0)) (+ cy (/ dy 2.0)) res w h)
)

(defun imgsat:montar-url (ext epsg / e)
  (setq e (itoa epsg))
  (strcat *imgsat-url*
          "?bbox=" (rtos (nth 0 ext) 2 3) "," (rtos (nth 1 ext) 2 3) ","
                   (rtos (nth 2 ext) 2 3) "," (rtos (nth 3 ext) 2 3)
          "&bboxSR=" e "&imageSR=" e
          "&size=" (itoa (nth 5 ext)) "," (itoa (nth 6 ext))
          "&format=jpg&transparent=false&f=image")
)

;;; ------------------------------------------------------------
;;; Download (curl.exe do Windows; se falhar, PowerShell)
;;; ------------------------------------------------------------

;;; Executa um programa e espera terminar. Retorna o codigo de saida ou nil.
(defun imgsat:executar (cmd / sh r)
  (if (setq sh (vlax-create-object "WScript.Shell"))
    (progn
      (setq r (vl-catch-all-apply 'vlax-invoke-method (list sh 'Run cmd 0 :vlax-true)))
      (vlax-release-object sh)
      (if (not (vl-catch-all-error-p r)) r)))
)

(defun imgsat:arquivo-ok (arq)
  (and (findfile arq) (> (vl-file-size arq) 2000))
)

(defun imgsat:baixar (url arq / arqps)
  (if (findfile arq) (vl-file-delete arq))
  (imgsat:executar (strcat "curl.exe -s -f -L -o \"" arq "\" \"" url "\""))
  (if (not (imgsat:arquivo-ok arq))
    (progn
      (setq arqps (vl-string-subst "''" "'" arq))
      (imgsat:executar
        (strcat "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \""
                "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;"
                "Invoke-WebRequest -UseBasicParsing -Uri '" url "' -OutFile '" arqps "'\""))))
  (imgsat:arquivo-ok arq)
)

;;; Arquivo de georreferencia (.jgw) para uso em GIS (QGIS, Map 3D...)
(defun imgsat:world-file (arq ext / f res)
  (setq res (nth 4 ext))
  (if (setq f (open (strcat (vl-filename-directory arq) "\\" (vl-filename-base arq) ".jgw") "w"))
    (progn
      (foreach v (list res 0.0 0.0 (- res)
                       (+ (nth 0 ext) (/ res 2.0))
                       (- (nth 3 ext) (/ res 2.0)))
        (write-line (rtos v 2 6) f))
      (close f)))
)

;;; ------------------------------------------------------------
;;; Insercao e recorte
;;; ------------------------------------------------------------

(defun imgsat:camada (doc nome)
  (if (not (tblsearch "LAYER" nome))
    (vla-add (vla-get-layers doc) nome))
  nome
)

;;; Recorta a imagem pelo poligono (ActiveX; se falhar, IMAGECLIP)
(defun imgsat:recortar (img pts / fechado arr i r)
  (setq fechado (append pts (list (car pts)))
        arr     (vlax-make-safearray vlax-vbDouble (cons 0 (1- (* 2 (length fechado)))))
        i       0)
  (foreach p fechado
    (vlax-safearray-put-element arr i (car p))
    (vlax-safearray-put-element arr (1+ i) (cadr p))
    (setq i (+ i 2)))
  (setq r (vl-catch-all-apply 'vla-ClipBoundary (list img (vlax-make-variant arr))))
  (if (not (vl-catch-all-error-p r))
    (setq r (vl-catch-all-apply 'vla-put-ClippingEnabled (list img :vlax-true))))
  (if (vl-catch-all-error-p r)
    (progn
      (command "_.IMAGECLIP" (vlax-vla-object->ename img) "_N" "_P")
      (foreach p pts (command (trans (list (car p) (cadr p) 0.0) 0 1)))
      (command "")))
)

(defun c:IMGSAT ( / *error* doc ms modo pts epsg auto res ext url arq img e
                    osm cme h nomebase)
  (defun *error* (msg)
    (if osm (setvar "OSMODE" osm))
    (if cme (setvar "CMDECHO" cme))
    (if (and msg (not (wcmatch (strcase msg) "*CANCEL*,*QUIT*,*EXIT*")))
      (princ (strcat "\nErro: " msg)))
    (princ))

  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object))
        ms  (vla-get-ModelSpace doc))

  (if (not (member (getvar "INSUNITS") '(0 6)))
    (princ "\nAtencao: as unidades do desenho (INSUNITS) nao estao em metros."))

  ;; 1. Poligono de recorte
  (initget "Pontos Polilinha Clicar")
  (setq modo (getkword "\nDefinir o recorte por [Pontos/Polilinha/Clicar] <Pontos>: "))
  (setq pts (cond ((= modo "Polilinha") (imgsat:por-polilinha))
                  ((= modo "Clicar")    (imgsat:por-cliques))
                  (T                    (imgsat:por-pontos))))
  (if (not pts) (exit))

  ;; 2. Sistema de coordenadas
  (setq auto (imgsat:epsg-auto)
        epsg (cond (auto)
                   ((getenv "IMGSAT_EPSG") (atoi (getenv "IMGSAT_EPSG")))
                   (31983)))
  (if auto
    (princ (strcat "\nSistema do desenho: " (getvar "CGEOCS") " -> EPSG " (itoa auto)))
    (princ "\nSistema de coordenadas do desenho nao identificado automaticamente."))
  (princ "\n(ex.: SIRGAS 2000 UTM 22S = 31982, 23S = 31983, 24S = 31984)")
  (initget 6)
  (setq e (getint (strcat "\nCodigo EPSG das coordenadas do desenho <" (itoa epsg) ">: ")))
  (if e (setq epsg e))
  (setenv "IMGSAT_EPSG" (itoa epsg))

  ;; 3. Resolucao
  (initget 6)
  (setq res (getdist (strcat "\nResolucao da imagem em metros por pixel <"
                             (rtos *imgsat-res-padrao* 2 2) ">: ")))
  (if (not res) (setq res *imgsat-res-padrao*))

  ;; 4. Area e download
  (setq ext (imgsat:extensao pts *imgsat-margem* res *imgsat-max-px*))
  (if (> (nth 4 ext) (* res 1.0001))
    (princ (strcat "\nArea grande: resolucao ajustada para " (rtos (nth 4 ext) 2 2)
                   " m/pixel (limite de " (itoa *imgsat-max-px*) " pixels por lado).")))
  (setq nomebase (if (= (getvar "DWGTITLED") 1)
                   (vl-filename-base (getvar "DWGNAME"))
                   "satelite")
        arq (strcat (getvar "DWGPREFIX") nomebase "_satelite_"
                    (menucmd "M=$(edtime,$(getvar,date),YYYYMODD_HHMMSS)") ".jpg")
        url (imgsat:montar-url ext epsg))
  (princ (strcat "\nBaixando imagem " (itoa (nth 5 ext)) " x " (itoa (nth 6 ext))
                 " pixels... aguarde."))
  (if (not (imgsat:baixar url arq))
    (progn
      (princ "\nNao foi possivel baixar a imagem. Verifique a internet/proxy e o codigo EPSG.")
      (princ (strcat "\nTeste este endereco no navegador:\n" url))
      (exit)))
  (imgsat:world-file arq ext)

  ;; 5. Inserir a imagem no lugar certo (canto inferior esquerdo, largura/altura reais)
  (setq osm (getvar "OSMODE") cme (getvar "CMDECHO"))
  (setvar "OSMODE" 0)
  (setvar "CMDECHO" 0)
  (setq img (vla-AddRaster ms arq (vlax-3d-point (list (nth 0 ext) (nth 1 ext) 0.0)) 1.0 0.0))
  (vla-put-ImageWidth  img (- (nth 2 ext) (nth 0 ext)))
  (vla-put-ImageHeight img (- (nth 3 ext) (nth 1 ext)))
  (vla-put-Origin img (vlax-3d-point (list (nth 0 ext) (nth 1 ext) 0.0)))
  (vla-put-Layer img (imgsat:camada doc *imgsat-camada*))

  ;; 6. Recortar pelo poligono e mandar para tras
  (imgsat:recortar img pts)
  (command "_.DRAWORDER" (vlax-vla-object->ename img) "" "_B")

  ;; 7. Credito da imagem (exigido pela Esri)
  (setq h (max 0.5 (/ (- (nth 2 ext) (nth 0 ext)) 150.0)))
  (entmake (list '(0 . "MTEXT") '(100 . "AcDbEntity") (cons 8 *imgsat-camada*)
                 '(100 . "AcDbMText")
                 (cons 10 (list (nth 2 ext) (- (nth 1 ext) (* 0.5 h)) 0.0))
                 (cons 40 h) '(71 . 3)
                 '(1 . "Imagem: Esri, Maxar, Earthstar Geographics e GIS User Community")))

  (vla-ZoomWindow (vlax-get-acad-object)
                  (vlax-3d-point (list (nth 0 ext) (nth 1 ext) 0.0))
                  (vlax-3d-point (list (nth 2 ext) (nth 3 ext) 0.0)))
  (setvar "OSMODE" osm)
  (setvar "CMDECHO" cme)
  (princ (strcat "\nImagem inserida e recortada. Arquivo: " arq))
  (princ "\n(A imagem fica vinculada: mantenha o .jpg junto com o desenho.)")
  (princ)
)

(princ "\nimagem_satelite.lsp carregado. Comando: IMGSAT")
(princ)
