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
#   IN[3] Afastamento da divisa (m) - padrao 1.5
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
AMOSTRAS_DIVISA = 6     # pontos de cota ao longo de cada divisa


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


def testada(lote, a, b, lotes, dmax):
    """Trecho do tubo a-b de onde raios perpendiculares atingem o lote.

    Retorna (s1, s2, u, n, profundidades) ou None; u = direcao do tubo,
    n = normal apontando para o lote, profundidades = {s: distancia}.
    """
    L = dist(a, b)
    if L < 1e-6:
        return None
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    if cruz(u, sub(lote.centro, a)) >= 0:
        n = (-u[1], u[0])
    else:
        n = (u[1], -u[0])
    projs = [(p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1] for p in lote.poli]
    smin, smax = max(0.0, min(projs)), min(L, max(projs))
    if smax <= smin:
        return None

    # so os lotes proximos podem bloquear os raios (desempenho)
    area = caixa(lote.poli + [a, b], 1.0)
    perto = [o for o in lotes if caixas_cruzam(area, o.caixa)]

    validos = []
    s = smin
    while s <= smax + 1e-9:
        o = soma(a, u, s)
        ts = raio_poligono(o, n, lote.poli, dmax)
        if ts and ts[0] > 1e-6:
            fim = soma(o, n, ts[0])
            if not bloqueado(o, fim, lote, perto):
                validos.append((s, ts[0]))
        s += PASSO_TESTADA
    if not validos:
        return None

    # maior trecho continuo
    melhor, atual = [], [validos[0]]
    for v in validos[1:]:
        if v[0] - atual[-1][0] <= PASSO_TESTADA * 1.5:
            atual.append(v)
        else:
            if len(atual) > len(melhor):
                melhor = atual
            atual = [v]
    if len(atual) > len(melhor):
        melhor = atual
    prof = dict(melhor)
    return melhor[0][0], melhor[-1][0], u, n, prof


def cota_divisa(lote, a, u, n, s, dmax, cota):
    """Cota media ao longo da divisa: raio logo para dentro do lote."""
    o = soma(a, u, s)
    ts = raio_poligono(o, n, lote.poli, dmax * 3 + 1000.0)
    if not ts:
        return None
    entra = ts[0]
    sai = ts[1] if len(ts) > 1 else entra
    zs = []
    for k in range(AMOSTRAS_DIVISA):
        t = entra + (sai - entra) * (k + 0.5) / AMOSTRAS_DIVISA
        z = cota(soma(o, n, t))
        if z is not None:
            zs.append(z)
    if not zs:
        return None
    return sum(zs) / len(zs)


def planejar(lote, lotes, tubos, cota, recuo, afast, dmax):
    """Ligacao de um lote: dict com inicio, fim, lado, cotas... ou motivo."""
    candidatos = []
    for a, b in tubos:
        if dist_seg_poligono(a, b, lote.poli) > dmax:
            continue
        r = testada(lote, a, b, lotes, dmax)
        if r is not None:
            s1, s2, u, n, prof = r
            candidatos.append((s2 - s1, -min(prof.values()), a, b, r))
    if not candidatos:
        return {'lote': lote.nome, 'motivo': 'sem testada voltada para a rede'}
    candidatos.sort(key=lambda c: (c[0], c[1]), reverse=True)
    a, b, (s1, s2, u, n, prof) = candidatos[0][2], candidatos[0][3], candidatos[0][4]

    lados = []
    if s2 - s1 < 2.0 * afast:
        lados.append({'lado': 'meio', 's': (s1 + s2) / 2.0, 'vizinho': None,
                      'cota': None})
    else:
        for nome, sd, sinal in (('inicio', s1, -1.0), ('fim', s2, 1.0)):
            prof_d = prof[sd]
            vizinho = None
            for extra in (2.0, 5.0, 10.0):
                p = soma(soma(a, u, sd + sinal * min(afast, 1.0)), n,
                         prof_d + extra)
                vizinho = lote_em(p, lote, lotes)
                if vizinho is not None:
                    break
            z = cota_divisa(lote, a, u, n, sd - sinal * 0.5, dmax, cota)
            lados.append({'lado': nome, 's': sd - sinal * afast,
                          'vizinho': vizinho.nome if vizinho else None,
                          'cota': z})
        com_vizinho = [l for l in lados if l['vizinho'] is not None]
        if com_vizinho:
            lados = com_vizinho
        lados.sort(key=lambda l: (l['cota'] is None,
                                  l['cota'] if l['cota'] is not None else 0.0))

    escolhido = lados[0]
    o = soma(a, u, escolhido['s'])
    ts = raio_poligono(o, n, lote.poli, dmax)
    if not ts:
        return {'lote': lote.nome, 'motivo': 'raio nao atinge o lote'}
    comp = ts[0] - recuo
    if comp <= 0.05:
        return {'lote': lote.nome, 'motivo': 'lote a menos de %.2f m da rede'
                % recuo}
    return {'lote': lote.nome, 'inicio': o, 'fim': soma(o, n, comp),
            'lado': escolhido['lado'], 'vizinho': escolhido['vizinho'],
            'cota': escolhido['cota'],
            'cotas': [(l['lado'], l['cota']) for l in lados]}


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
                relatorio.append('%s: %.2f m | divisa %s%s | %s'
                                 % (r['lote'], dist(a, b), r['lado'],
                                    ' (vizinho %s)' % r['vizinho']
                                    if r['vizinho'] else '', cotas))

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
                   numero(IN[3], 1.5), numero(IN[4], 30.0),
                   texto(IN[5]) or 'LIGACOES', bool(IN[6]), bool(IN[7]))
except Exception:
    OUT = 'ERRO:\n' + traceback.format_exc()
