# ============================================================
# eixo_entre_linhas.py - codigo do no Python de EixoEntreLinhas.dyn
#
# Civil 3D 2021 / Dynamo 2.5-2.6 / IronPython 2.7
#
# 1. Pede no desenho duas curvas abertas: LINE, ARC, polilinha (2D/3D,
#    com ou sem arcos) ou SPLINE.
# 2. Calcula o eixo (centro) entre elas e cria um alinhamento com
#    tangentes e curvas ajustadas a esse eixo.
# 3. Pede a superficie (ou usa o nome informado) e cria o perfil
#    da superficie (Surface Profile) nesse alinhamento.
# 4. Pede o ponto de insercao e cria o perfil longitudinal
#    (Profile View) ja com o perfil da superficie.
#
# Entradas (IN):
#   IN[0] Executar (bool)          - so roda quando True
#   IN[1] Nome do alinhamento      - ex. "EIXO" (sufixo automatico se ja existir)
#   IN[2] Nome da superficie       - vazio = clicar na superficie no desenho
#   IN[3] Estilo do alinhamento    - vazio = primeiro estilo do desenho
#   IN[4] Estilo do perfil         - vazio = primeiro estilo do desenho
#   IN[5] Estilo do perfil long.   - (Profile View Style) vazio = primeiro
#   IN[6] Band set do perfil long. - vazio = primeiro
#   IN[7] Inverter sentido (bool)  - inverte o sentido do estaqueamento
#   IN[8] Tolerancia (m)           - desvio maximo do alinhamento em relacao
#                                    ao eixo calculado (padrao 0.01)
#
# Este arquivo e a fonte; o .dyn e gerado por dynamo/build_dyn.py.
# (Strings sem acento para evitar problemas de codificacao.)
# ============================================================

import clr
import math
import traceback

clr.AddReference('AcMgd')
clr.AddReference('AcCoreMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.EditorInput import (PromptEntityOptions,
                                          PromptPointOptions, PromptStatus)
from Autodesk.AutoCAD.DatabaseServices import (Curve,
                                               OpenMode, ObjectId, Polyline,
                                               Ray, Xline)
from Autodesk.AutoCAD.Geometry import Point2d, Point3d, Vector3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import (Alignment, PolylineOptions,
                                             Profile, ProfileView, Surface)

PASSO_AMOSTRA = 0.5     # espacamento (m) dos pontos de calculo do eixo
MIN_AMOSTRAS = 16
MAX_AMOSTRAS = 3000
RAIO_MAXIMO = 100000.0  # acima disso o trecho e tratado como reta


def texto(v):
    """Normaliza entrada de texto do Dynamo (None -> '')."""
    if v is None:
        return ''
    return str(v).strip()


# ------------------------------------------------------------
# Geometria pura (pontos como tuplas (x, y)) - independe do AutoCAD
# ------------------------------------------------------------
def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def media(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def ponto_extremo(a, b, proximo1, proximo2):
    """Ponto do segmento a-b (que liga as pontas das curvas) equidistante
    das duas curvas - mantem o eixo com o comprimento total das curvas."""
    def g(t):
        p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        return dist(p, proximo1(p)) - dist(p, proximo2(p)), p
    lo, hi = 0.0, 1.0
    p = media(a, b)
    if g(lo)[0] > 0 or g(hi)[0] < 0:
        return p
    for _ in range(50):
        meio = (lo + hi) / 2.0
        v, p = g(meio)
        if abs(v) < 1e-7:
            break
        if v < 0:
            lo = meio
        else:
            hi = meio
    return p


def pontos_eixo(amostra1, amostra2, proximo1, proximo2, n, refinos=6):
    """Pontos do eixo entre duas curvas.

    amostraK(f) -> ponto na fracao f (0..1) do comprimento da curva K
    proximoK(p) -> ponto da curva K (prolongada nas pontas) mais proximo de p

    Cada ponto interno parte da media dos pontos de mesma fracao das duas
    curvas e e refinado para ficar equidistante delas; as extremidades
    ficam sobre o segmento que liga as pontas das curvas.
    """
    pts = []
    for i in range(n + 1):
        f = float(i) / n
        a, b = amostra1(f), amostra2(f)
        if i == 0 or i == n:
            m = ponto_extremo(a, b, proximo1, proximo2)
        else:
            m = media(a, b)
            for _ in range(refinos):
                novo = media(proximo1(m), proximo2(m))
                mudou = dist(novo, m)
                m = novo
                if mudou < 1e-6:
                    break
        if not pts or dist(pts[-1], m) > 1e-6:
            pts.append(m)
    return pts


def precisa_inverter(a1, b1, a2, b2):
    """True se a curva 2 esta desenhada no sentido contrario da curva 1."""
    return dist(a1, b2) + dist(b1, a2) < dist(a1, a2) + dist(b1, b2)


def desvio_reta(pts, i, j):
    a, b = pts[i], pts[j]
    L = dist(a, b)
    if L < 1e-9:
        return float('inf')
    dx, dy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    d = 0.0
    for k in range(i + 1, j):
        p = pts[k]
        d = max(d, abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx))
    return d


def circulo(a, b, c):
    """Centro e raio do circulo por 3 pontos (None se colineares)."""
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) +
               c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    a2 = a[0] ** 2 + a[1] ** 2
    b2 = b[0] ** 2 + b[1] ** 2
    c2 = c[0] ** 2 + c[1] ** 2
    ux = (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d
    uy = (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d
    centro = (ux, uy)
    return centro, dist(centro, a)


def bulge_arco(a, m, b):
    """Bulge da polilinha para o arco que vai de a ate b passando por m."""
    circ = circulo(a, m, b)
    if circ is None:
        return 0.0
    c = circ[0]
    ang_a = math.atan2(a[1] - c[1], a[0] - c[0])
    ang_b = math.atan2(b[1] - c[1], b[0] - c[0])
    giro = (m[0] - a[0]) * (b[1] - m[1]) - (m[1] - a[1]) * (b[0] - m[0])
    if giro > 0:   # anti-horario
        varredura = (ang_b - ang_a) % (2 * math.pi)
    else:          # horario
        varredura = -((ang_a - ang_b) % (2 * math.pi))
    return math.tan(varredura / 4.0)


def desvio_arco(pts, i, j):
    if j - i < 2:
        return float('inf')
    circ = circulo(pts[i], pts[(i + j) // 2], pts[j])
    if circ is None or circ[1] > RAIO_MAXIMO:
        return float('inf')
    c, r = circ
    if abs(bulge_arco(pts[i], pts[(i + j) // 2], pts[j])) > 0.98:
        return float('inf')   # arco de quase 360 graus: nao e um trecho
    d = 0.0
    for k in range(i + 1, j):
        d = max(d, abs(dist(c, pts[k]) - r))
    return d


def maior_trecho(pts, i, desvio, tol, minimo):
    """Maior j tal que pts[i..j] cabe no trecho (busca exponencial+binaria)."""
    n = len(pts) - 1
    ok = i + minimo
    if ok > n or desvio(pts, i, ok) > tol:
        return None
    passo = 1
    while ok < n:
        prox = min(n, ok + passo)
        if desvio(pts, i, prox) <= tol:
            ok = prox
            passo *= 2
        else:
            lo, hi = ok, prox     # lo cabe, hi nao
            while hi - lo > 1:
                meio = (lo + hi) // 2
                if desvio(pts, i, meio) <= tol:
                    lo = meio
                else:
                    hi = meio
            return lo
    return ok


def ajustar_trechos(pts, tol):
    """Converte a sequencia de pontos em retas e arcos.

    Retorna lista de vertices (ponto, bulge) no formato de polilinha; o
    ultimo vertice tem bulge 0.
    """
    vertices = []
    i, n = 0, len(pts) - 1
    while i < n:
        j_reta = maior_trecho(pts, i, desvio_reta, tol, 1) or (i + 1)
        j_arco = maior_trecho(pts, i, desvio_arco, tol, 2)
        if j_arco is not None and j_arco > j_reta:
            vertices.append((pts[i], bulge_arco(pts[i], pts[(i + j_arco) // 2],
                                                pts[j_arco])))
            i = j_arco
        else:
            vertices.append((pts[i], 0.0))
            i = j_reta
    vertices.append((pts[n], 0.0))
    return vertices


# ------------------------------------------------------------
# Adaptadores AutoCAD
# ------------------------------------------------------------
def comprimento(c):
    return (c.GetDistanceAtParameter(c.EndParam) -
            c.GetDistanceAtParameter(c.StartParam))


def funcoes_curva(c, inverter=False):
    """(amostra(f), proximo(p)) de uma curva, opcionalmente invertida."""
    d0 = c.GetDistanceAtParameter(c.StartParam)
    L = comprimento(c)

    def amostra(f):
        if inverter:
            f = 1.0 - f
        if f <= 0.0:
            p = c.StartPoint
        elif f >= 1.0:
            p = c.EndPoint
        else:
            p = c.GetPointAtDist(d0 + L * f)
        return (p.X, p.Y)

    estado = {'estender': True}

    def proximo(pt):
        # Projeta na vertical (funciona com curvas em qualquer elevacao) e
        # considera a curva prolongada nas pontas, para que curvas de
        # comprimentos diferentes nao "puxem" o eixo nas extremidades.
        q = Point3d(pt[0], pt[1], 0.0)
        if estado['estender']:
            try:
                p = c.GetClosestPointTo(q, Vector3d.ZAxis, True)
                return (p.X, p.Y)
            except Exception:
                estado['estender'] = False   # ex.: splines
        p = c.GetClosestPointTo(q, Vector3d.ZAxis, False)
        return (p.X, p.Y)

    return amostra, proximo


def xy(p):
    return (p.X, p.Y)


def estilo(colecao, nome):
    """Estilo pelo nome; se vazio ou inexistente, o primeiro da colecao."""
    if nome and colecao.Contains(nome):
        return colecao[nome]
    if colecao.Count == 0:
        raise Exception('O desenho nao possui estilos do tipo necessario.')
    return colecao[0]


def pedir_entidade(ed, msg, rejeicao, classe, exata):
    opt = PromptEntityOptions(msg)
    opt.SetRejectMessage(rejeicao)
    opt.AddAllowedClass(clr.GetClrType(classe), exata)
    res = ed.GetEntity(opt)
    if res.Status != PromptStatus.OK:
        return None
    return res.ObjectId


def nomes_alinhamentos(civdoc, t):
    ids = list(civdoc.GetAlignmentIds())
    try:
        ids += list(civdoc.GetSitelessAlignmentIds())
    except Exception:
        pass
    nomes = set()
    for i in ids:
        nomes.add(t.GetObject(i, OpenMode.ForRead).Name)
    return nomes


def nome_unico(base, existentes):
    if base not in existentes:
        return base
    n = 1
    while True:
        cand = '%s (%d)' % (base, n)
        if cand not in existentes:
            return cand
        n += 1


def superficie_por_nome(civdoc, t, nome):
    for i in civdoc.GetSurfaceIds():
        if t.GetObject(i, OpenMode.ForRead).Name == nome:
            return i
    return None


def executar(executa, nome_alin, nome_sup, est_alin, est_perfil,
             est_pv, band_set, inverter, tol):
    if not executa:
        return 'Defina "Executar" = True e rode o grafico.'

    adoc = Application.DocumentManager.MdiActiveDocument
    ed = adoc.Editor
    db = adoc.Database
    civdoc = CivilApplication.ActiveDocument

    nome_alin = nome_alin or 'EIXO'
    tol = tol if tol and tol > 0 else 0.01

    # Leva o foco para o desenho para responder aos prompts
    try:
        from Autodesk.AutoCAD.Internal import Utils
        Utils.SetFocusToDwgView()
    except Exception:
        pass

    # ---- 1. selecao das curvas (fora do lock/transacao) ----
    rej = '\nObjeto invalido: selecione linha, arco, polilinha ou spline.'
    id1 = pedir_entidade(ed, '\nSelecione a PRIMEIRA linha/polilinha: ',
                         rej, Curve, False)
    if id1 is None:
        return 'Cancelado: primeira linha nao selecionada.'
    id2 = pedir_entidade(ed, '\nSelecione a SEGUNDA linha/polilinha: ',
                         rej, Curve, False)
    if id2 is None:
        return 'Cancelado: segunda linha nao selecionada.'
    if id1 == id2:
        return 'Erro: a mesma linha foi selecionada duas vezes.'

    # ---- 2. superficie ----
    sup_id = None
    if not nome_sup:
        sup_id = pedir_entidade(ed, '\nSelecione a SUPERFICIE: ',
                                '\nObjeto invalido: selecione uma superficie.',
                                Surface, False)
        if sup_id is None:
            return 'Cancelado: superficie nao selecionada.'

    # ---- 3. ponto de insercao do perfil longitudinal ----
    popt = PromptPointOptions(
        '\nPonto de insercao do perfil longitudinal <automatico>: ')
    popt.AllowNone = True
    pres = ed.GetPoint(popt)
    ponto_pv = pres.Value if pres.Status == PromptStatus.OK else None

    with adoc.LockDocument():
        t = db.TransactionManager.StartTransaction()
        try:
            c1 = t.GetObject(id1, OpenMode.ForRead)
            c2 = t.GetObject(id2, OpenMode.ForRead)
            for c in (c1, c2):
                if isinstance(c, (Xline, Ray)) or c.Closed:
                    t.Abort()
                    return ('Erro: use curvas abertas (sem XLINE/RAY, '
                            'circulos ou polilinhas fechadas).')

            if nome_sup:
                sup_id = superficie_por_nome(civdoc, t, nome_sup)
                if sup_id is None:
                    t.Abort()
                    return 'Erro: superficie "%s" nao encontrada.' % nome_sup
            sup = t.GetObject(sup_id, OpenMode.ForRead)

            # ---- eixo entre as curvas ----
            inv2 = precisa_inverter(xy(c1.StartPoint), xy(c1.EndPoint),
                                    xy(c2.StartPoint), xy(c2.EndPoint))
            am1, px1 = funcoes_curva(c1)
            am2, px2 = funcoes_curva(c2, inv2)
            n = int(max(comprimento(c1), comprimento(c2)) / PASSO_AMOSTRA)
            n = min(max(n, MIN_AMOSTRAS), MAX_AMOSTRAS)
            pts = pontos_eixo(am1, am2, px1, px2, n)
            if inverter:
                pts.reverse()
            if len(pts) < 2:
                t.Abort()
                return 'Erro: o eixo resultante tem comprimento zero.'
            vertices = ajustar_trechos(pts, tol)

            # polilinha temporaria com o eixo (convertida em alinhamento)
            pl = Polyline()
            for k, (p, b) in enumerate(vertices):
                pl.AddVertexAt(k, Point2d(p[0], p[1]), b, 0.0, 0.0)
            pl.Layer = c1.Layer
            ms = t.GetObject(db.CurrentSpaceId, OpenMode.ForWrite)
            ms.AppendEntity(pl)
            t.AddNewlyCreatedDBObject(pl, True)
            comp_eixo = pl.Length
            n_curvas = len([v for v in vertices[:-1] if abs(v[1]) > 1e-9])
            n_tang = len(vertices) - 1 - n_curvas

            # ---- alinhamento ----
            styles = civdoc.Styles
            nome_final = nome_unico(nome_alin, nomes_alinhamentos(civdoc, t))
            opts = PolylineOptions()
            opts.PlineId = pl.ObjectId
            opts.AddCurvesBetweenTangents = False
            opts.EraseExistingEntities = True
            alin_id = Alignment.Create(
                civdoc, opts, nome_final, ObjectId.Null, db.Clayer,
                estilo(styles.AlignmentStyles, est_alin),
                estilo(styles.LabelSetStyles.AlignmentLabelSetStyles, ''))
            alin = t.GetObject(alin_id, OpenMode.ForRead)

            # ---- perfil da superficie ----
            nome_perfil = 'TN - %s' % sup.Name
            Profile.CreateFromSurface(
                nome_perfil, alin_id, sup_id, db.Clayer,
                estilo(styles.ProfileStyles, est_perfil),
                estilo(styles.LabelSetStyles.ProfileLabelSetStyles, ''))

            # ---- perfil longitudinal (Profile View) ----
            if ponto_pv is None:
                ext = alin.GeometricExtents
                folga = max(ext.MaxPoint.X - ext.MinPoint.X,
                            ext.MaxPoint.Y - ext.MinPoint.Y, 10.0) * 0.2
                ponto_pv = Point3d(ext.MaxPoint.X + folga, ext.MinPoint.Y, 0.0)
            ProfileView.Create(
                alin_id, ponto_pv, 'PL - %s' % nome_final,
                estilo(styles.ProfileViewBandSetStyles, band_set),
                estilo(styles.ProfileViewStyles, est_pv))

            t.Commit()
        except Exception:
            t.Abort()
            raise
        finally:
            t.Dispose()

    ed.WriteMessage('\nAlinhamento "%s" criado (%.3f m) com perfil "%s".\n'
                    % (nome_final, comp_eixo, nome_perfil))
    return ['Alinhamento: %s' % nome_final,
            'Comprimento: %.3f' % comp_eixo,
            'Tangentes: %d  |  Curvas: %d' % (n_tang, n_curvas),
            'Perfil: %s' % nome_perfil,
            'Perfil longitudinal: PL - %s' % nome_final]


try:
    OUT = executar(IN[0], texto(IN[1]), texto(IN[2]), texto(IN[3]),
                   texto(IN[4]), texto(IN[5]), texto(IN[6]), bool(IN[7]),
                   float(IN[8] or 0))
except Exception:
    OUT = 'ERRO:\n' + traceback.format_exc()
