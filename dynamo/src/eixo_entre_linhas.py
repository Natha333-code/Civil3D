# ============================================================
# eixo_entre_linhas.py - codigo do no Python de EixoEntreLinhas.dyn
#
# Civil 3D 2021 / Dynamo 2.5-2.6 / IronPython 2.7
#
# 1. Pede no desenho duas LINHAS (LINE).
# 2. Cria um alinhamento no eixo (centro) entre elas.
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
from Autodesk.AutoCAD.EditorInput import (PromptEntityOptions,
                                          PromptPointOptions, PromptStatus)
from Autodesk.AutoCAD.DatabaseServices import (Line, OpenMode, ObjectId)
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import (Alignment, Profile, ProfileView,
                                             Surface)


def texto(v):
    """Normaliza entrada de texto do Dynamo (None -> '')."""
    if v is None:
        return ''
    return str(v).strip()


def ponto_medio(p, q):
    return Point3d((p.X + q.X) / 2.0, (p.Y + q.Y) / 2.0, 0.0)


def eixo_entre(a1, b1, a2, b2):
    """Retorna (inicio, fim) do eixo entre os segmentos a1-b1 e a2-b2.

    A segunda linha e orientada no mesmo sentido da primeira (se os
    vetores apontam para lados opostos, inverte-se a2/b2), e o eixo liga
    o ponto medio dos inicios ao ponto medio dos fins.
    """
    d1x, d1y = b1.X - a1.X, b1.Y - a1.Y
    d2x, d2y = b2.X - a2.X, b2.Y - a2.Y
    if d1x * d2x + d1y * d2y < 0:
        a2, b2 = b2, a2
    return ponto_medio(a1, a2), ponto_medio(b1, b2)


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
             est_pv, band_set, inverter):
    if not executa:
        return 'Defina "Executar" = True e rode o grafico.'

    adoc = Application.DocumentManager.MdiActiveDocument
    ed = adoc.Editor
    db = adoc.Database
    civdoc = CivilApplication.ActiveDocument

    nome_alin = nome_alin or 'EIXO'

    # Leva o foco para o desenho para responder aos prompts
    try:
        from Autodesk.AutoCAD.Internal import Utils
        Utils.SetFocusToDwgView()
    except Exception:
        pass

    # ---- 1. selecao das linhas (fora do lock/transacao) ----
    rej = '\nObjeto invalido: selecione uma LINE.'
    id1 = pedir_entidade(ed, '\nSelecione a PRIMEIRA linha: ', rej, Line, True)
    if id1 is None:
        return 'Cancelado: primeira linha nao selecionada.'
    id2 = pedir_entidade(ed, '\nSelecione a SEGUNDA linha: ', rej, Line, True)
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
            l1 = t.GetObject(id1, OpenMode.ForRead)
            l2 = t.GetObject(id2, OpenMode.ForRead)

            if nome_sup:
                sup_id = superficie_por_nome(civdoc, t, nome_sup)
                if sup_id is None:
                    t.Abort()
                    return 'Erro: superficie "%s" nao encontrada.' % nome_sup
            sup = t.GetObject(sup_id, OpenMode.ForRead)

            ini, fim = eixo_entre(l1.StartPoint, l1.EndPoint,
                                  l2.StartPoint, l2.EndPoint)
            if inverter:
                ini, fim = fim, ini
            if ini.DistanceTo(fim) < 1e-6:
                t.Abort()
                return 'Erro: o eixo resultante tem comprimento zero.'

            # ---- alinhamento ----
            styles = civdoc.Styles
            nome_final = nome_unico(nome_alin, nomes_alinhamentos(civdoc, t))
            alin_id = Alignment.Create(
                civdoc, nome_final, ObjectId.Null, db.Clayer,
                estilo(styles.AlignmentStyles, est_alin),
                estilo(styles.LabelSetStyles.AlignmentLabelSetStyles, ''))
            alin = t.GetObject(alin_id, OpenMode.ForWrite)
            alin.Entities.AddFixedLine(ini, fim)

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
                    % (nome_final, ini.DistanceTo(fim), nome_perfil))
    return ['Alinhamento: %s' % nome_final,
            'Comprimento: %.3f' % ini.DistanceTo(fim),
            'Perfil: %s' % nome_perfil,
            'Perfil longitudinal: PL - %s' % nome_final]


try:
    OUT = executar(IN[0], texto(IN[1]), texto(IN[2]), texto(IN[3]),
                   texto(IN[4]), texto(IN[5]), texto(IN[6]), bool(IN[7]))
except Exception:
    OUT = 'ERRO:\n' + traceback.format_exc()
