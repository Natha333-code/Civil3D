# ============================================================
# ligacoes_prediais.py - codigo do no Python de LigacoesPrediais.dyn
#
# Civil 3D 2021 / Dynamo 2.5-2.6 / IronPython 2.7
#
# Cria uma linha (ramal / ligacao predial) por lote (parcel):
#   - perpendicular a rede (pipe network) selecionada;
#   - partindo do eixo do tubo e terminando RECUO metros antes do lote;
#   - posicionada a AFASTAMENTO metros da divisa com o lote vizinho;
#   - sempre na divisa de MENOR COTA, pela superficie escolhida.
# As linhas sao criadas na cor magenta (ACI 6).
#
# Entradas (IN):
#   IN[0] Executar (bool)
#   IN[1] Nome da superficie      - vazio = clicar na superficie
#   IN[2] Recuo do lote (m)       - padrao 1.0
#   IN[3] Afastamento da divisa (m) - padrao 1.0
#   IN[4] Distancia maxima rede-lote (m) - padrao 30
#   IN[5] Layer                   - padrao "LIGACOES"
#   IN[6] Usar LINE (bool)        - False = polilinha (LWPOLYLINE)
#   IN[7] Apagar linhas anteriores do layer (bool)
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
from Autodesk.AutoCAD.Colors import Color, ColorMethod
from Autodesk.AutoCAD.DatabaseServices import (Curve, DBObjectCollection,
                                               LayerTableRecord, Line,
                                               OpenMode, Polyline)
from Autodesk.AutoCAD.EditorInput import PromptEntityOptions, PromptStatus
from Autodesk.AutoCAD.Geometry import Point2d, Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Pipe, Surface

COR_MAGENTA = 6
PASSO_TESTADA = 0.25    # espacamento (m) dos raios que medem a testada
AMOSTRAS_DIVISA = 10    # pontos de cota ao longo de cada divisa


# ------------------------------------------------------------
# Geometria pura (pontos como tuplas (x, y)) - independe do AutoCAD
# ------------------------------------------------------------
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def soma(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


def cruz(a, b):
    return a[0] * b[1] - a[1] * b[0]


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def arestas(poli):
    n = len(poli)
    for i in range(n):
        yield poli[i], poli[(i + 1) % n]


def caixa(poli, folga=0.0):
    xs = [p[0] for p in poli]
    ys = [p[1] for p in poli]
    return (min(xs) - folga, min(ys) - folga, max(xs) + folga, max(ys) + folga)


def caixas_cruzam(c1, c2):
    return not (c1[2] < c2[0] or c2[2] < c1[0] or c1[3] < c2[1] or c2[3] < c1[1])


def centroide(poli):
    a = cx = cy = 0.0
    for p, q in arestas(poli):
        k = cruz(p, q)
        a += k
        cx += (p[0] + q[0]) * k
        cy += (p[1] + q[1]) * k
    if abs(a) < 1e-12:
        n = float(len(poli))
        return (sum(p[0] for p in poli) / n, sum(p[1] for p in poli) / n)
    return (cx / (3.0 * a), cy / (3.0 * a))


def dentro(p, poli):
    """Ponto dentro do poligono (ray casting)."""
    x, y = p
    res = False
    for a, b in arestas(poli):
        if (a[1] > y) != (b[1] > y):
            xi = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if xi > x:
                res = not res
    return res


def inter_segmentos(p, p2, q, q2):
    """Parametros (t, u) da intersecao de p-p2 com q-q2, ou None."""
    r = sub(p2, p)
    s = sub(q2, q)
    den = cruz(r, s)
    if abs(den) < 1e-12:
        return None
    qp = sub(q, p)
    t = cruz(qp, s) / den
    u = cruz(qp, r) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return t, u
    return None


def raio_poligono(o, d, poli, alcance):
    """Distancias (ordenadas) em que o raio o + t*d corta o poligono."""
    fim = soma(o, d, alcance)
    ts = []
    for a, b in arestas(poli):
        r = inter_segmentos(o, fim, a, b)
        if r is not None:
            ts.append(r[0] * alcance)
    ts.sort()
    return ts


def dist_ponto_seg(p, a, b):
    ab = sub(b, a)
    l2 = ab[0] ** 2 + ab[1] ** 2
    if l2 < 1e-18:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
    return dist(p, soma(a, ab, t))


def seg_corta_poligono(a, b, poli):
    if dentro(a, poli) or dentro(b, poli):
        return True
    for p, q in arestas(poli):
        if inter_segmentos(a, b, p, q) is not None:
            return True
    return False


def dist_seg_poligono(a, b, poli):
    if seg_corta_poligono(a, b, poli):
        return 0.0
    d = min(dist_ponto_seg(p, a, b) for p in poli)
    for p, q in arestas(poli):
        d = min(d, dist_ponto_seg(a, p, q), dist_ponto_seg(b, p, q))
    return d


class Lote(object):
    def __init__(self, nome, poli):
        self.nome = nome
        self.poli = poli
        self.caixa = caixa(poli)
        self.centro = centroide(poli)


def bloqueado(a, b, lote, lotes):
    """True se o segmento a-b atravessa outro lote antes de chegar."""
    cx = caixa([a, b])
    for outro in lotes:
        if outro is lote or not caixas_cruzam(cx, outro.caixa):
            continue
        for p, q in arestas(outro.poli):
            r = inter_segmentos(a, b, p, q)
            if r is not None and r[0] < 1.0 - 1e-6:
                return True
    return False


def lote_em(p, lote, lotes):
    for outro in lotes:
        if outro is lote:
            continue
        c = outro.caixa
        if c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3] and dentro(p, outro.poli):
            return outro
    return None


def unit(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L)


def escalar(a, b):
    return a[0] * b[0] + a[1] * b[1]


def dist_reta(p, a, b):
    """Distancia de p a reta infinita que passa por a e b."""
    return abs(cruz(sub(b, a), sub(p, a))) / dist(a, b)


def bissecao(f, ok, ruim, iteracoes=40):
    """Ultimo valor entre ok (f verdadeiro) e ruim (f falso)."""
    for _ in range(iteracoes):
        m = (ok + ruim) / 2.0
        if f(m):
            ok = m
        else:
            ruim = m
    return ok


class Frente(object):
    """Testada de um lote vista a partir da reta de um tubo (prolongada).

    A reta do tubo e prolongada alem das pontas, para que os PVs (fim dos
    tubos) no meio de um lote nao cortem a testada.
    """

    def __init__(self, lote, a, b, lotes, dmax):
        self.ok = False
        L = dist(a, b)
        if L < 1e-6:
            return
        self.lote, self.a, self.dmax = lote, a, dmax
        self.u = u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        if cruz(u, sub(lote.centro, a)) >= 0:
            self.n = (-u[1], u[0])
        else:
            self.n = (u[1], -u[0])
        projs = [escalar(sub(p, a), u) for p in lote.poli]
        smin, smax = min(projs), max(projs)
        area = caixa(lote.poli + [a, b, soma(a, u, smin), soma(a, u, smax)],
                     1.0)
        self.perto = [o for o in lotes if caixas_cruzam(area, o.caixa)]

        validos = []
        s = smin
        while s <= smax + 1e-9:
            if self.prof(s) is not None:
                validos.append(s)
            s += PASSO_TESTADA
        if not validos:
            return
        melhor, atual = [], [validos[0]]
        for v in validos[1:]:
            if v - atual[-1] <= PASSO_TESTADA * 1.5:
                atual.append(v)
            else:
                if len(atual) > len(melhor):
                    melhor = atual
                atual = [v]
        if len(atual) > len(melhor):
            melhor = atual
        valido = lambda x: self.prof(x) is not None
        # cantos exatos da testada (onde o raio deixa de atingir o lote)
        self.s1 = bissecao(valido, melhor[0], melhor[0] - PASSO_TESTADA)
        self.s2 = bissecao(valido, melhor[-1], melhor[-1] + PASSO_TESTADA)
        self.ok = True

    def origem(self, s):
        return soma(self.a, self.u, s)

    def prof(self, s):
        """Distancia da reta do tubo ao lote no raio da estacao s."""
        o = self.origem(s)
        ts = raio_poligono(o, self.n, self.lote.poli, self.dmax)
        if not ts or ts[0] <= 1e-6:
            return None
        if bloqueado(o, soma(o, self.n, ts[0]), self.lote, self.perto):
            return None
        return ts[0]

    def ponto(self, s):
        """Ponto da frente do lote atingido pelo raio da estacao s."""
        d = self.prof(s)
        if d is None:
            return None
        return soma(self.origem(s), self.n, d)


def caminho_divisa(lote, canto, n):
    """Vertices da divisa lateral que sai do canto da testada.

    Parte do vertice do lote mais proximo do canto e segue o contorno no
    sentido que se afasta da rede, enquanto as arestas continuarem indo
    para o fundo do lote.
    """
    poli = lote.poli
    N = len(poli)
    i = min(range(N), key=lambda k: dist(poli[k], canto))
    passos = []
    for passo in (1, -1):
        e = sub(poli[(i + passo) % N], poli[i])
        if math.hypot(e[0], e[1]) > 1e-9:
            passos.append((escalar(unit(e), n), passo))
    passo = max(passos)[1]
    caminho = [poli[i]]
    j = i
    for _ in range(N - 1):
        k = (j + passo) % N
        e = sub(poli[k], poli[j])
        if math.hypot(e[0], e[1]) < 1e-9:
            j = k
            continue
        if len(caminho) > 1 and escalar(unit(e), n) < 0.5:
            break
        caminho.append(poli[k])
        j = k
    return caminho


def cota_divisa(lote, caminho, cota):
    """Cota media da superficie ao longo da divisa, 0,5 m para dentro do lote."""
    trechos = list(zip(caminho, caminho[1:]))
    total = sum(dist(p, q) for p, q in trechos)
    if total < 1e-6:
        return None
    zs = []
    for k in range(AMOSTRAS_DIVISA):
        alvo = total * (k + 0.5) / AMOSTRAS_DIVISA
        for p, q in trechos:
            L = dist(p, q)
            if alvo <= L or (p, q) == trechos[-1]:
                e = unit(sub(q, p))
                base = soma(p, e, min(alvo, L))
                for perp in ((-e[1], e[0]), (e[1], -e[0])):
                    x = soma(base, perp, 0.5)
                    if dentro(x, lote.poli):
                        z = cota(x)
                        if z is not None:
                            zs.append(z)
                        break
                break
            alvo -= L
    if not zs:
        return None
    return sum(zs) / len(zs)


def pe_na_rede(q, tubos, lote, perto):
    """Pe da perpendicular de q no tubo mais proximo que esta em frente.

    Retorna (ponto, perpendicular?). Se nenhum tubo tem q a sua frente
    (ex.: lado externo de uma deflexao), usa o PV (ponta) mais proximo.
    """
    melhor = None
    for a, b in tubos:
        L = dist(a, b)
        if L < 1e-6:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        t = escalar(sub(q, a), u)
        if -1e-6 <= t <= L + 1e-6:
            f = soma(a, u, t)
            d = dist(f, q)
            if (melhor is None or d < melhor[0]) and \
                    not bloqueado(f, q, lote, perto):
                melhor = (d, f)
    if melhor is not None:
        return melhor[1], True
    pontas = [p for ab in tubos for p in ab]
    return min(pontas, key=lambda p: dist(p, q)), False


def planejar(lote, lotes, tubos, cota, recuo, afast, dmax):
    """Ligacao de um lote: dict com inicio, fim, lado, cotas... ou motivo."""
    candidatos = []
    for a, b in tubos:
        d = dist_seg_poligono(a, b, lote.poli)
        if d > dmax:
            continue
        fr = Frente(lote, a, b, lotes, dmax)
        if fr.ok:
            candidatos.append((round(d, 3), -(fr.s2 - fr.s1), fr))
    if not candidatos:
        return {'lote': lote.nome, 'motivo': 'sem testada voltada para a rede'}
    candidatos.sort(key=lambda c: (c[0], c[1]))
    fr = candidatos[0][2]
    s1, s2, u, n = fr.s1, fr.s2, fr.u, fr.n
    meio = (s1 + s2) / 2.0

    lados = []
    for nome, sd, sinal in (('inicio', s1, -1.0), ('fim', s2, 1.0)):
        canto = fr.ponto(sd)
        if canto is None:
            continue
        cam = caminho_divisa(lote, canto, n)
        if len(cam) < 2:
            continue
        vizinho = None
        for extra in (2.0, 5.0, 10.0):
            p = soma(soma(canto, u, sinal * min(afast, 1.0)), n, extra)
            vizinho = lote_em(p, lote, lotes)
            if vizinho is not None:
                break
        lados.append({'lado': nome, 'sd': sd, 'divisa': (cam[0], cam[1]),
                      'vizinho': vizinho.nome if vizinho else None,
                      'cota': cota_divisa(lote, cam, cota)})
    if not lados:
        return {'lote': lote.nome, 'motivo': 'divisas nao identificadas'}
    todos = list(lados)
    com_vizinho = [l for l in lados if l['vizinho'] is not None]
    if com_vizinho:
        lados = com_vizinho
    lados.sort(key=lambda l: (l['cota'] is None,
                              l['cota'] if l['cota'] is not None else 0.0))
    esc = lados[0]

    # estacao onde a frente do lote fica a 'afast' metros da divisa
    da, db_ = esc['divisa']

    def longe(s):
        q = fr.ponto(s)
        return q is not None and dist_reta(q, da, db_) >= afast

    if longe(meio):
        # longe() e falso no canto e verdadeiro no meio: busca a transicao
        s_lig = bissecao(longe, meio, esc['sd'])
        dist_div = afast
    else:
        s_lig = meio     # testada estreita: ligacao no meio
        q = fr.ponto(meio)
        dist_div = dist_reta(q, da, db_) if q is not None else 0.0
    q = fr.ponto(s_lig)
    if q is None:
        return {'lote': lote.nome, 'motivo': 'frente do lote nao encontrada'}

    # inicio no eixo do tubo em frente, perpendicular a ele
    ini, perpendicular = pe_na_rede(q, tubos, lote, fr.perto)
    if dist(ini, q) < 1e-6:
        return {'lote': lote.nome, 'motivo': 'rede encostada no lote'}
    d = unit(sub(q, ini))
    ts = raio_poligono(ini, d, lote.poli, dist(ini, q) + 1.0)
    alcance = ts[0] if ts else dist(ini, q)
    comp = alcance - recuo
    if comp <= 0.05:
        return {'lote': lote.nome, 'motivo': 'lote a menos de %.2f m da rede'
                % recuo}
    return {'lote': lote.nome, 'inicio': ini, 'fim': soma(ini, d, comp),
            'frente': q, 'lado': esc['lado'], 'vizinho': esc['vizinho'],
            'cota': esc['cota'], 'dist_divisa': dist_div,
            'perpendicular': perpendicular,
            'cotas': [(l['lado'], l['cota']) for l in todos]}


# ------------------------------------------------------------
# Adaptadores AutoCAD / Civil 3D
# ------------------------------------------------------------
def texto(v):
    if v is None:
        return ''
    return str(v).strip()


def numero(v, padrao):
    try:
        v = float(v)
        return v if v > 0 else padrao
    except Exception:
        return padrao


def pontos_curva(c):
    """Pontos (x, y) ao longo de uma curva (arcos discretizados)."""
    pts = []
    if isinstance(c, Polyline):
        nv = c.NumberOfVertices
        nseg = nv if c.Closed else nv - 1
        for i in range(nseg):
            p = c.GetPoint2dAt(i)
            pts.append((p.X, p.Y))
            if abs(c.GetBulgeAt(i)) > 1e-9:
                for k in range(1, 12):
                    q = c.GetPointAtParameter(i + k / 12.0)
                    pts.append((q.X, q.Y))
        if not c.Closed:
            p = c.GetPoint2dAt(nv - 1)
            pts.append((p.X, p.Y))
    else:
        d0 = c.GetDistanceAtParameter(c.StartParam)
        L = c.GetDistanceAtParameter(c.EndParam) - d0
        n = max(int(L / 0.5), 16)
        for k in range(n + 1):
            q = c.GetPointAtDist(d0 + L * k / n)
            pts.append((q.X, q.Y))
    return pts


def encadear(trechos):
    """Une listas de pontos pelas pontas e devolve um poligono."""
    trechos = [t for t in trechos if len(t) >= 2]
    if not trechos:
        return []
    poli = list(trechos.pop(0))
    while trechos:
        fim = poli[-1]
        melhor = None
        for i, t in enumerate(trechos):
            for inv in (False, True):
                d = dist(fim, t[-1] if inv else t[0])
                if melhor is None or d < melhor[0]:
                    melhor = (d, i, inv)
        t = trechos.pop(melhor[1])
        if melhor[2]:
            t = list(reversed(t))
        poli.extend(t[1:])
    return poli


def limpar_poligono(pts):
    res = []
    for p in pts:
        if not res or dist(res[-1], p) > 1e-6:
            res.append(p)
    if len(res) > 1 and dist(res[0], res[-1]) < 1e-6:
        res.pop()
    return res


def poligono_lote(parcel, t):
    """Contorno do parcel como lista de pontos."""
    try:
        c = parcel.BaseCurve
        if c is not None:
            return limpar_poligono(pontos_curva(c))
    except Exception:
        pass
    # alternativa: explodir o parcel e unir as curvas resultantes
    objs = DBObjectCollection()
    parcel.Explode(objs)
    trechos = []
    for o in objs:
        if isinstance(o, Curve):
            trechos.append(pontos_curva(o))
        o.Dispose()
    return limpar_poligono(encadear(trechos))


def pedir_entidade(ed, msg, rejeicao, classe):
    opt = PromptEntityOptions(msg)
    opt.SetRejectMessage(rejeicao)
    opt.AddAllowedClass(clr.GetClrType(classe), False)
    res = ed.GetEntity(opt)
    if res.Status != PromptStatus.OK:
        return None
    return res.ObjectId


def superficie_por_nome(civdoc, t, nome):
    for i in civdoc.GetSurfaceIds():
        if t.GetObject(i, OpenMode.ForRead).Name == nome:
            return i
    return None


def garantir_layer(db, t, nome):
    lt = t.GetObject(db.LayerTableId, OpenMode.ForRead)
    if lt.Has(nome):
        return
    lt.UpgradeOpen()
    ltr = LayerTableRecord()
    ltr.Name = nome
    ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, COR_MAGENTA)
    lt.Add(ltr)
    t.AddNewlyCreatedDBObject(ltr, True)


def executar(executa, nome_sup, recuo, afast, dmax, layer, usar_line, apagar):
    if not executa:
        return 'Defina "Executar" = True e rode o grafico.'

    adoc = Application.DocumentManager.MdiActiveDocument
    ed = adoc.Editor
    db = adoc.Database
    civdoc = CivilApplication.ActiveDocument

    try:
        from Autodesk.AutoCAD.Internal import Utils
        Utils.SetFocusToDwgView()
    except Exception:
        pass

    tubo_id = pedir_entidade(ed, '\nSelecione um TUBO da rede: ',
                             '\nObjeto invalido: selecione um tubo (pipe).',
                             Pipe)
    if tubo_id is None:
        return 'Cancelado: rede nao selecionada.'
    sup_id = None
    if not nome_sup:
        sup_id = pedir_entidade(ed, '\nSelecione a SUPERFICIE existente: ',
                                '\nObjeto invalido: selecione uma superficie.',
                                Surface)
        if sup_id is None:
            return 'Cancelado: superficie nao selecionada.'

    with adoc.LockDocument():
        t = db.TransactionManager.StartTransaction()
        try:
            if nome_sup:
                sup_id = superficie_por_nome(civdoc, t, nome_sup)
                if sup_id is None:
                    t.Abort()
                    return 'Erro: superficie "%s" nao encontrada.' % nome_sup
            sup = t.GetObject(sup_id, OpenMode.ForRead)

            def cota(p):
                try:
                    return sup.FindElevationAtXY(p[0], p[1])
                except Exception:
                    return None

            # ---- tubos da rede ----
            tubo = t.GetObject(tubo_id, OpenMode.ForRead)
            rede = t.GetObject(tubo.NetworkId, OpenMode.ForRead)
            tubos = []
            for i in rede.GetPipeIds():
                p = t.GetObject(i, OpenMode.ForRead)
                tubos.append(((p.StartPoint.X, p.StartPoint.Y),
                              (p.EndPoint.X, p.EndPoint.Y)))

            # ---- lotes (parcels de todos os sites) ----
            lotes, ignorados = [], []
            for site_id in civdoc.GetSiteIds():
                site = t.GetObject(site_id, OpenMode.ForRead)
                for pid in site.GetParcelIds():
                    parcel = t.GetObject(pid, OpenMode.ForRead)
                    poli = poligono_lote(parcel, t)
                    if len(poli) < 3:
                        ignorados.append('%s: contorno invalido' % parcel.Name)
                        continue
                    # lotes cortados pela rede (rua / faixa de dominio) ficam de fora
                    if any(seg_corta_poligono(a, b, poli) for a, b in tubos):
                        ignorados.append('%s: atravessado pela rede' % parcel.Name)
                        continue
                    lotes.append(Lote(parcel.Name, poli))
            if not lotes:
                t.Abort()
                return 'Erro: nenhum lote (parcel) encontrado no desenho.'

            # ---- layer e limpeza ----
            garantir_layer(db, t, layer)
            espaco = t.GetObject(db.CurrentSpaceId, OpenMode.ForWrite)
            apagadas = 0
            if apagar:
                for eid in espaco:
                    ent = t.GetObject(eid, OpenMode.ForRead)
                    if ent.Layer == layer and isinstance(ent, (Line, Polyline)):
                        ent.UpgradeOpen()
                        ent.Erase()
                        apagadas += 1

            # ---- ligacoes ----
            criadas, relatorio = 0, []
            for lote in lotes:
                r = planejar(lote, lotes, tubos, cota, recuo, afast, dmax)
                if 'motivo' in r:
                    ignorados.append('%s: %s' % (r['lote'], r['motivo']))
                    continue
                a, b = r['inicio'], r['fim']
                if usar_line:
                    ent = Line(Point3d(a[0], a[1], 0.0), Point3d(b[0], b[1], 0.0))
                else:
                    ent = Polyline()
                    ent.AddVertexAt(0, Point2d(a[0], a[1]), 0.0, 0.0, 0.0)
                    ent.AddVertexAt(1, Point2d(b[0], b[1]), 0.0, 0.0, 0.0)
                ent.SetDatabaseDefaults()
                ent.Layer = layer
                ent.ColorIndex = COR_MAGENTA
                espaco.AppendEntity(ent)
                t.AddNewlyCreatedDBObject(ent, True)
                criadas += 1
                cotas = ', '.join('%s=%s' % (l, '%.3f' % z if z is not None
                                             else 's/ cota')
                                  for l, z in r['cotas'])
                relatorio.append('%s: %.2f m | divisa %s%s a %.2f m | %s%s'
                                 % (r['lote'], dist(a, b), r['lado'],
                                    ' (vizinho %s)' % r['vizinho']
                                    if r['vizinho'] else '',
                                    r['dist_divisa'], cotas,
                                    '' if r['perpendicular'] else
                                    ' | sai do PV (nenhum tubo em frente)'))

            t.Commit()
        except Exception:
            t.Abort()
            raise
        finally:
            t.Dispose()

    ed.WriteMessage('\n%d ligacoes criadas no layer "%s".\n' % (criadas, layer))
    res = ['Ligacoes criadas: %d (layer %s)' % (criadas, layer)]
    if apagadas:
        res.append('Linhas anteriores apagadas: %d' % apagadas)
    res.append('--- Ligacoes ---')
    res += relatorio
    if ignorados:
        res.append('--- Lotes ignorados ---')
        res += ignorados
    return res


try:
    OUT = executar(IN[0], texto(IN[1]), numero(IN[2], 1.0),
                   numero(IN[3], 1.0), numero(IN[4], 30.0),
                   texto(IN[5]) or 'LIGACOES', bool(IN[6]), bool(IN[7]))
except Exception:
    OUT = 'ERRO:\n' + traceback.format_exc()
