# ============================================================
# ajuste_greide.py - codigo do no Python de AjusteGreide.dyn
#
# Civil 3D 2021 / Dynamo 2.5-2.6 / IronPython 2.7
#
# Para cada alinhamento escolhido:
#   1. Le as secoes transversais do terreno (superficie existente) em cada
#      estaca: intervalo fixo + estacas das sample lines existentes.
#   2. Calcula, com o perfil de projeto (greide) e a plataforma (largura +
#      inclinacao transversal), as alturas de CORTE e ATERRO.
#   3. Ajusta o perfil de projeto (move PVIs proximos ou insere PVIs) ate
#      que corte <= Corte maximo e aterro <= Aterro maximo em toda a secao.
#   Por padrao o ajuste e feito numa COPIA do perfil ("<nome> - AJUSTADO").
#
# Entradas (IN):
#   IN[0]  Executar (bool)
#   IN[1]  Alinhamentos (nomes separados por ;)  - vazio = selecionar
#   IN[2]  Nome da superficie existente           - vazio = clicar
#   IN[3]  Nome do perfil de projeto              - vazio = 1o perfil de layout
#   IN[4]  Corte maximo (m)                       - padrao 3.0
#   IN[5]  Aterro maximo (m)                      - padrao 3.0
#   IN[6]  Largura da plataforma (m)              - padrao 7.0 (0 = so o eixo)
#   IN[7]  Inclinacao transversal (%)             - padrao -2.0 (caindo p/ bordos)
#   IN[8]  Intervalo de analise (m)               - padrao 10
#   IN[9]  Espacamento minimo entre PVIs (m)      - padrao 20
#   IN[10] Ajustar o perfil original (bool)       - False = cria copia
#
# Este arquivo e a fonte; o .dyn e gerado por dynamo/build_dyn.py.
# (Strings sem acento para evitar problemas de codificacao.)
# ============================================================

import clr
import traceback

clr.AddReference('AcMgd')
clr.AddReference('AcCoreMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (OpenMode, TypedValue)
from Autodesk.AutoCAD.EditorInput import (PromptEntityOptions,
                                          PromptSelectionOptions,
                                          PromptStatus, SelectionFilter)
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import (Profile, ProfileType, Surface)

TOLERANCIA = 0.005   # m - violacao menor que isso e ignorada
MARGEM = 0.02        # m - folga deixada dentro dos limites ao ajustar
MAX_ITERACOES = 500
PASSO_SECAO = 1.0    # m - espacamento dos pontos na secao transversal


# ------------------------------------------------------------
# Calculo puro - independe do AutoCAD
# ------------------------------------------------------------
def offsets_secao(largura):
    """Afastamentos (m) dos pontos da secao: eixo, bordos e intermediarios."""
    meia = largura / 2.0
    if meia <= 1e-9:
        return [0.0]
    n = max(1, int(meia / PASSO_SECAO + 0.5))
    lado = [meia * k / n for k in range(1, n + 1)]
    return [-o for o in reversed(lado)] + [0.0] + lado


def faixa_greide(secao, corte_max, aterro_max, inc):
    """Faixa (minimo, maximo) da cota do eixo que respeita os limites.

    secao: lista (offset, cota do terreno ou None); inc: inclinacao
    transversal em m/m (negativa = plataforma cai do eixo para os bordos).
    Cota da plataforma no offset o = cota do eixo + inc * |o|.
    """
    base = [z - inc * abs(o) for o, z in secao if z is not None]
    if not base:
        return None
    return max(base) - corte_max, min(base) + aterro_max


def corte_aterro(z_eixo, secao, inc):
    """(corte maximo, aterro maximo) da secao para a cota do eixo dada."""
    corte = aterro = 0.0
    for o, z in secao:
        if z is None:
            continue
        h = z_eixo + inc * abs(o) - z
        if h > aterro:
            aterro = h
        if -h > corte:
            corte = -h
    return corte, aterro


def resumo(perfil, estacoes, secoes, faixas, inc):
    """Estatisticas de corte/aterro e estacas fora dos limites."""
    r = {'corte': 0.0, 'est_corte': None, 'aterro': 0.0, 'est_aterro': None,
         'violacoes': []}
    for s in estacoes:
        z = perfil.cota(s)
        c, a = corte_aterro(z, secoes[s], inc)
        if c > r['corte']:
            r['corte'], r['est_corte'] = c, s
        if a > r['aterro']:
            r['aterro'], r['est_aterro'] = a, s
        f = faixas.get(s)
        if f is not None and f[0] <= f[1] and \
                (z < f[0] - TOLERANCIA or z > f[1] + TOLERANCIA):
            r['violacoes'].append(s)
    return r


def ajustar(perfil, estacoes, faixas, esp_min):
    """Ajusta o perfil ate respeitar as faixas. Retorna log de alteracoes.

    perfil precisa oferecer: cota(s), pvis() -> [(estaca, cota)] ordenados,
    mover_pvi(indice, delta) -> bool, adicionar_pvi(estaca, cota) -> bool.
    Retorna (log, convergiu, estacas_travadas).
    """
    log = {}            # estaca do PVI -> ['movido'|'novo', delta acumulado]
    movimentos = {}     # quantas vezes cada PVI foi movido
    travadas = set()    # estacas em que o Civil recusou mover e inserir PVI
    for _ in range(MAX_ITERACOES):
        pior = None
        for s in estacoes:
            f = faixas.get(s)
            if f is None or f[0] > f[1] or s in travadas:
                continue           # sem terreno, inviavel ou travada
            z = perfil.cota(s)
            if z < f[0] - TOLERANCIA:
                d = f[0] - z
            elif z > f[1] + TOLERANCIA:
                d = f[1] - z
            else:
                continue
            if pior is None or abs(d) > abs(pior[1]):
                pior = (s, d)
        if pior is None:
            return log, True, sorted(travadas)

        s, _ = pior
        lo, hi = faixas[s]
        z = perfil.cota(s)
        if hi - lo > 2 * MARGEM:
            alvo = min(max(z, lo + MARGEM), hi - MARGEM)
        else:
            alvo = (lo + hi) / 2.0
        d = alvo - z

        pvis = perfil.pvis()
        i = min(range(len(pvis)), key=lambda k: abs(pvis[k][0] - s))
        sp = pvis[i][0]
        # PVI movido muitas vezes sem resolver: a cada 6 movimentos o
        # espacamento exigido cai pela metade, permitindo inserir um PVI novo
        limite = esp_min / (2.0 ** (movimentos.get(sp, 0) // 6))
        if abs(sp - s) >= max(limite, 1.0) and perfil.adicionar_pvi(s, alvo):
            log[s] = ['novo', alvo]
            continue

        # peso do PVI na estaca s (funcao "chapeu" entre os vizinhos)
        if abs(sp - s) < 1e-6:
            peso = 1.0
        else:
            viz = pvis[i + 1][0] if s > sp and i + 1 < len(pvis) else \
                pvis[i - 1][0] if s < sp and i > 0 else None
            peso = 1.0 - abs(s - sp) / abs(viz - sp) if viz is not None else 1.0
        delta = d / max(peso, 0.3)
        if not perfil.mover_pvi(i, delta):
            if abs(sp - s) > 1.0 and perfil.adicionar_pvi(s, alvo):
                log[s] = ['novo', alvo]
            else:
                travadas.add(s)
            continue
        movimentos[sp] = movimentos.get(sp, 0) + 1
        if sp in log:
            log[sp][1] += delta   # 'novo': cota final; 'movido': delta total
        else:
            log[sp] = ['movido', delta]
    return log, False, sorted(travadas)


def rampa_maxima(pvis):
    r = 0.0
    for (s1, z1), (s2, z2) in zip(pvis, pvis[1:]):
        if s2 - s1 > 1e-6:
            r = max(r, abs(z2 - z1) / (s2 - s1) * 100.0)
    return r


def fmt_estaca(s):
    """Estaca no formato 0+000.00."""
    km = int(s // 1000)
    return '%d+%06.2f' % (km, s - km * 1000)


# ------------------------------------------------------------
# Adaptadores AutoCAD / Civil 3D
# ------------------------------------------------------------
class PerfilCivil(object):
    def __init__(self, prof):
        self.prof = prof

    def cota(self, s):
        return self.prof.ElevationAt(s)

    def _lista(self):
        return sorted([p for p in self.prof.PVIs], key=lambda p: p.Station)

    def pvis(self):
        return [(p.Station, p.Elevation) for p in self._lista()]

    def mover_pvi(self, i, delta):
        try:
            p = self._lista()[i]
            p.Elevation = p.Elevation + delta
            return True
        except Exception:
            return False

    def adicionar_pvi(self, s, z):
        try:
            self.prof.PVIs.AddPVI(s, z)
            return True
        except Exception:
            return False


def texto(v):
    if v is None:
        return ''
    return str(v).strip()


def numero(v, padrao, minimo=None):
    try:
        v = float(v)
    except Exception:
        return padrao
    if minimo is not None and v < minimo:
        return padrao
    return v


def pedir_superficie(ed):
    opt = PromptEntityOptions('\nSelecione a SUPERFICIE existente: ')
    opt.SetRejectMessage('\nObjeto invalido: selecione uma superficie.')
    opt.AddAllowedClass(clr.GetClrType(Surface), False)
    res = ed.GetEntity(opt)
    return res.ObjectId if res.Status == PromptStatus.OK else None


def pedir_alinhamentos(ed):
    opt = PromptSelectionOptions()
    opt.MessageForAdding = '\nSelecione os ALINHAMENTOS: '
    filtro = SelectionFilter([TypedValue(0, 'AECC_ALIGNMENT')])
    res = ed.GetSelection(opt, filtro)
    if res.Status != PromptStatus.OK:
        return []
    return list(res.Value.GetObjectIds())


def alinhamentos_por_nome(civdoc, t, nomes):
    ids = list(civdoc.GetAlignmentIds())
    try:
        ids += list(civdoc.GetSitelessAlignmentIds())
    except Exception:
        pass
    achados, vistos = [], set()
    for i in ids:
        a = t.GetObject(i, OpenMode.ForRead)
        if a.Name in nomes and a.Name not in vistos:
            achados.append(i)
            vistos.add(a.Name)
    return achados, [n for n in nomes if n not in vistos]


def superficie_por_nome(civdoc, t, nome):
    for i in civdoc.GetSurfaceIds():
        if t.GetObject(i, OpenMode.ForRead).Name == nome:
            return i
    return None


def perfil_projeto(alin, t, nome):
    layouts = []
    for pid in alin.GetProfileIds():
        p = t.GetObject(pid, OpenMode.ForRead)
        if p.ProfileType == ProfileType.FG:
            if nome and p.Name == nome:
                return p
            layouts.append(p)
    if nome:
        return None
    return layouts[0] if layouts else None


def nome_livre(alin, t, base):
    nomes = set(t.GetObject(p, OpenMode.ForRead).Name
                for p in alin.GetProfileIds())
    if base not in nomes:
        return base
    k = 2
    while '%s (%d)' % (base, k) in nomes:
        k += 1
    return '%s (%d)' % (base, k)


def copiar_perfil(orig, alin, t, avisos):
    """Cria '<nome> - AJUSTADO' com os mesmos PVIs e curvas verticais."""
    nome = nome_livre(alin, t, '%s - AJUSTADO' % orig.Name)
    novo_id = Profile.CreateByLayout(nome, alin.ObjectId, orig.LayerId,
                                     orig.StyleId, orig.LabelSetId)
    novo = t.GetObject(novo_id, OpenMode.ForWrite)
    curvas = []
    for p in sorted([p for p in orig.PVIs], key=lambda p: p.Station):
        npvi = novo.PVIs.AddPVI(p.Station, p.Elevation)
        try:
            vc = p.VerticalCurve
            if vc is not None and vc.Length > 1e-6:
                curvas.append((npvi, vc.Length))
        except Exception:
            pass
    for npvi, L in curvas:
        try:
            novo.Entities.AddFreeSymmetricParabolaByPVIAndLength(npvi, L)
        except Exception:
            avisos.append('curva vertical na estaca %s nao copiada'
                          % fmt_estaca(npvi.Station))
    return novo


def pontos_secao(alin, s, offsets, cota):
    secao = []
    e = clr.Reference[float]()
    n = clr.Reference[float]()
    for o in offsets:
        try:
            alin.PointLocation(s, o, e, n)
            secao.append((o, cota(e.Value, n.Value)))
        except Exception:
            secao.append((o, None))
    return secao


def estacas_analise(alin, t, ini, fim, intervalo, pvis):
    est = set()
    s = ini
    while s < fim - 1e-6:
        est.add(round(s, 3))
        s += intervalo
    est.add(round(fim, 3))
    for sp, _ in pvis:
        est.add(round(sp, 3))
    n_sl = 0
    try:
        for gid in alin.GetSampleLineGroupIds():
            g = t.GetObject(gid, OpenMode.ForRead)
            for sid in g.GetSampleLineIds():
                st = t.GetObject(sid, OpenMode.ForRead).Station
                if ini - 1e-6 <= st <= fim + 1e-6:
                    est.add(round(st, 3))
                    n_sl += 1
    except Exception:
        pass
    return sorted(est), n_sl


def processar(alin, t, sup, nome_perfil, cmax, amax, largura, inc,
              intervalo, esp_min, original):
    linhas = ['=== %s ===' % alin.Name]
    orig = perfil_projeto(alin, t, nome_perfil)
    if orig is None:
        linhas.append('  Perfil de projeto %snao encontrado.'
                      % ('"%s" ' % nome_perfil if nome_perfil else ''))
        return linhas

    def cota(x, y):
        try:
            return sup.FindElevationAtXY(x, y)
        except Exception:
            return None

    pvis0 = PerfilCivil(orig).pvis()
    if len(pvis0) < 2:
        linhas.append('  Perfil "%s" sem PVIs suficientes.' % orig.Name)
        return linhas
    ini = max(pvis0[0][0], alin.StartingStation)
    fim = min(pvis0[-1][0], alin.EndingStation)
    estacoes, n_sl = estacas_analise(alin, t, ini, fim, intervalo, pvis0)
    offs = offsets_secao(largura)
    secoes = dict((s, pontos_secao(alin, s, offs, cota)) for s in estacoes)
    faixas = dict((s, faixa_greide(secoes[s], cmax, amax, inc))
                  for s in estacoes)
    estacoes = [s for s in estacoes if faixas[s] is not None]
    if not estacoes:
        linhas.append('  Alinhamento fora da superficie.')
        return linhas
    inviaveis = [s for s in estacoes if faixas[s][0] > faixas[s][1]]

    antes = resumo(PerfilCivil(orig), estacoes, secoes, faixas, inc)
    linhas.append('  Perfil: %s | %d secoes (%d de sample lines) | largura %.2f m'
                  % (orig.Name, len(estacoes), n_sl, largura))
    linhas.append('  ANTES : corte max %.2f m (est. %s) | aterro max %.2f m '
                  '(est. %s) | %d estacas fora dos limites'
                  % (antes['corte'], fmt_estaca(antes['est_corte'] or 0),
                     antes['aterro'], fmt_estaca(antes['est_aterro'] or 0),
                     len(antes['violacoes'])))

    if not antes['violacoes']:
        linhas.append('  Perfil ja atende aos limites - nada alterado.')
    else:
        avisos = []
        if original:
            orig.UpgradeOpen()
            alvo_prof = orig
        else:
            alvo_prof = copiar_perfil(orig, alin, t, avisos)
        perfil = PerfilCivil(alvo_prof)
        log, ok, travadas = ajustar(perfil, estacoes, faixas, esp_min)
        depois = resumo(perfil, estacoes, secoes, faixas, inc)
        linhas.append('  DEPOIS: corte max %.2f m (est. %s) | aterro max %.2f m '
                      '(est. %s) | %d estacas fora dos limites'
                      % (depois['corte'], fmt_estaca(depois['est_corte'] or 0),
                         depois['aterro'],
                         fmt_estaca(depois['est_aterro'] or 0),
                         len(depois['violacoes'])))
        linhas.append('  Perfil ajustado: %s | rampa maxima %.2f%%'
                      % (alvo_prof.Name, rampa_maxima(perfil.pvis())))
        novos = sorted(s for s, v in log.items() if v[0] == 'novo')
        movidos = sorted(s for s, v in log.items() if v[0] == 'movido')
        if novos:
            linhas.append('  PVIs inseridos (%d): %s' % (len(novos), ', '.join(
                '%s (%.3f)' % (fmt_estaca(s), log[s][1]) for s in novos)))
        if movidos:
            linhas.append('  PVIs movidos (%d): %s' % (len(movidos), ', '.join(
                '%s (%+.3f m)' % (fmt_estaca(s), log[s][1]) for s in movidos)))
        if not ok or depois['violacoes']:
            linhas.append('  ATENCAO: ainda fora dos limites em: %s'
                          % ', '.join(fmt_estaca(s)
                                      for s in depois['violacoes'][:30]))
        if travadas:
            linhas.append('  Civil recusou ajustar (curva vertical?) em: %s'
                          % ', '.join(fmt_estaca(s) for s in travadas[:30]))
        for a in avisos:
            linhas.append('  Aviso: %s' % a)
    if inviaveis:
        linhas.append('  INVIAVEIS (terreno transversal inclinado demais para a '
                      'largura e os limites; nao ajustadas): %s'
                      % ', '.join(fmt_estaca(s) for s in inviaveis[:30]))
    return linhas


def executar(executa, nomes_alin, nome_sup, nome_perfil, cmax, amax, largura,
             inc_pct, intervalo, esp_min, original):
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

    nomes = [n.strip() for n in nomes_alin.split(';') if n.strip()]
    alin_ids = []
    if not nomes:
        alin_ids = pedir_alinhamentos(ed)
        if not alin_ids:
            return 'Cancelado: nenhum alinhamento selecionado.'
    sup_id = None
    if not nome_sup:
        sup_id = pedir_superficie(ed)
        if sup_id is None:
            return 'Cancelado: superficie nao selecionada.'

    saida = ['Corte max %.2f m | Aterro max %.2f m | Plataforma %.2f m a %.2f%%'
             % (cmax, amax, largura, inc_pct)]
    with adoc.LockDocument():
        t = db.TransactionManager.StartTransaction()
        try:
            if nomes:
                alin_ids, faltando = alinhamentos_por_nome(civdoc, t, nomes)
                for n in faltando:
                    saida.append('Alinhamento "%s" nao encontrado.' % n)
            if nome_sup:
                sup_id = superficie_por_nome(civdoc, t, nome_sup)
                if sup_id is None:
                    t.Abort()
                    return 'Erro: superficie "%s" nao encontrada.' % nome_sup
            sup = t.GetObject(sup_id, OpenMode.ForRead)
            saida.append('Superficie: %s' % sup.Name)
            for aid in alin_ids:
                alin = t.GetObject(aid, OpenMode.ForRead)
                saida += processar(alin, t, sup, nome_perfil, cmax, amax,
                                   largura, inc_pct / 100.0, intervalo,
                                   esp_min, original)
            t.Commit()
        except Exception:
            t.Abort()
            raise
        finally:
            t.Dispose()
    ed.WriteMessage('\nAjuste de greide concluido. Veja o no Resultado.\n')
    return saida


try:
    OUT = executar(IN[0], texto(IN[1]), texto(IN[2]), texto(IN[3]),
                   numero(IN[4], 3.0, 0.0), numero(IN[5], 3.0, 0.0),
                   numero(IN[6], 7.0, 0.0), numero(IN[7], -2.0),
                   numero(IN[8], 10.0, 0.5), numero(IN[9], 20.0, 0.0),
                   bool(IN[10]))
except Exception:
    OUT = 'ERRO:\n' + traceback.format_exc()
