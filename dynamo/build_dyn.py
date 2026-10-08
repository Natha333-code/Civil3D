#!/usr/bin/env python3
"""Gera os arquivos .dyn a partir do codigo em dynamo/src/.

Cada grafico = nos de entrada (String / Boolean / Number, marcados como entrada do
Dynamo Player) -> um no Python Script (IronPython) -> um no Watch.
Formato compativel com Dynamo 2.5+ (Civil 3D 2021).

Uso:  python3 dynamo/build_dyn.py
"""
import json
import os
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
DYNAMO_VERSION = "2.5.0.7460"


def gid():
    return uuid.uuid4().hex


def porta(nome, desc):
    return {"Id": gid(), "Name": nome, "Description": desc,
            "UsingDefaultValue": False, "Level": 2, "UseLevels": False,
            "KeepListStructure": False}


def no_string(valor):
    return {"ConcreteType": "CoreNodeModels.Input.StringInput, CoreNodeModels",
            "NodeType": "StringInputNode", "InputValue": valor, "Id": gid(),
            "Inputs": [], "Outputs": [porta("", "String")],
            "Replication": "Disabled", "Description": "Creates a string."}


def no_bool(valor):
    return {"ConcreteType": "CoreNodeModels.Input.BoolSelector, CoreNodeModels",
            "NodeType": "BooleanInputNode", "InputValue": valor, "Id": gid(),
            "Inputs": [], "Outputs": [porta("", "Boolean")],
            "Replication": "Disabled",
            "Description": "Selection between a true and false."}


def no_numero(valor):
    return {"ConcreteType": "CoreNodeModels.Input.DoubleInput, CoreNodeModels",
            "NodeType": "NumberInputNode", "NumberType": "Double",
            "InputValue": valor, "Id": gid(),
            "Inputs": [], "Outputs": [porta("", "Double")],
            "Replication": "Disabled", "Description": "Creates a number."}


NOS_ENTRADA = {"string": no_string, "boolean": no_bool, "number": no_numero}


def no_python(codigo, n_entradas):
    return {"ConcreteType": "PythonNodeModels.PythonNode, PythonNodeModels",
            "NodeType": "PythonScriptNode", "Code": codigo,
            "VariableInputPorts": True, "Id": gid(),
            "Inputs": [porta("IN[%d]" % i, "Input #%d" % i)
                       for i in range(n_entradas)],
            "Outputs": [porta("OUT", "Result of the python script")],
            "Replication": "Disabled",
            "Description": "Runs an embedded IronPython script."}


def no_watch():
    return {"ConcreteType": "CoreNodeModels.Watch, CoreNodeModels",
            "NodeType": "ExtensionNode", "Id": gid(),
            "Inputs": [porta("", "Node to show output from")],
            "Outputs": [porta("", "Node output")],
            "Replication": "Disabled",
            "Description": "Visualize the output of node."}


def gerar(nome, descricao, arquivo_py, entradas, saida_dyn):
    """entradas: lista de (rotulo, tipo, valor, descricao);
    tipo = 'string' | 'boolean' | 'number'."""
    with open(os.path.join(AQUI, "src", arquivo_py), encoding="utf-8") as f:
        codigo = f.read()

    nos, views, conectores, inputs = [], [], [], []
    py = no_python(codigo, len(entradas))
    watch = no_watch()

    for i, (rotulo, tipo, valor, desc) in enumerate(entradas):
        no = NOS_ENTRADA[tipo](valor)
        nos.append(no)
        views.append({"Id": no["Id"], "IsSetAsInput": True,
                      "IsSetAsOutput": False, "Name": rotulo,
                      "ShowGeometry": True, "Excluded": False,
                      "X": 0.0, "Y": 110.0 * i})
        entrada = {"Id": no["Id"], "Name": rotulo, "Type": tipo,
                   "Value": (str(valor).lower() if tipo == "boolean"
                             else str(valor)),
                   "Description": desc}
        if tipo == "number":
            entrada["NumberType"] = "Double"
        inputs.append(entrada)
        conectores.append({"Start": no["Outputs"][0]["Id"],
                           "End": py["Inputs"][i]["Id"], "Id": gid()})

    nos += [py, watch]
    meio = 110.0 * (len(entradas) - 1) / 2.0
    views.append({"Id": py["Id"], "IsSetAsInput": False,
                  "IsSetAsOutput": False, "Name": nome,
                  "ShowGeometry": True, "Excluded": False,
                  "X": 450.0, "Y": meio})
    views.append({"Id": watch["Id"], "IsSetAsInput": False,
                  "IsSetAsOutput": True, "Name": "Resultado",
                  "ShowGeometry": True, "Excluded": False,
                  "X": 750.0, "Y": meio})
    conectores.append({"Start": py["Outputs"][0]["Id"],
                       "End": watch["Inputs"][0]["Id"], "Id": gid()})

    dyn = {
        "Uuid": str(uuid.uuid4()), "IsCustomNode": False,
        "Description": descricao, "Name": nome,
        "ElementResolver": {"ResolutionMap": {}},
        "Inputs": inputs, "Outputs": [],
        "Nodes": nos, "Connectors": conectores,
        "Dependencies": [], "NodeLibraryDependencies": [], "Bindings": [],
        "View": {
            "Dynamo": {"ScaleFactor": 1.0, "HasRunWithoutCrash": True,
                       "IsVisibleInDynamoLibrary": True,
                       "Version": DYNAMO_VERSION, "RunType": "Manual",
                       "RunPeriod": "1000"},
            "Camera": {"Name": "Background Preview", "EyeX": -17.0,
                       "EyeY": 24.0, "EyeZ": 50.0, "LookX": 12.0,
                       "LookY": -13.0, "LookZ": -58.0, "UpX": 0.0,
                       "UpY": 1.0, "UpZ": 0.0},
            "NodeViews": views, "Annotations": [],
            "X": 60.0, "Y": 60.0, "Zoom": 0.8,
        },
    }
    with open(os.path.join(AQUI, saida_dyn), "w", encoding="utf-8") as f:
        json.dump(dyn, f, indent=2, ensure_ascii=False)
    print("Gerado:", saida_dyn)


if __name__ == "__main__":
    gerar(
        "EixoEntreLinhas",
        "Seleciona duas linhas/polilinhas (retas ou curvas), cria um "
        "alinhamento no eixo entre elas, "
        "o perfil da superficie escolhida e o perfil longitudinal.",
        "eixo_entre_linhas.py",
        [
            ("Executar", "boolean", False, "Ative para rodar a rotina."),
            ("Nome do alinhamento", "string", "EIXO",
             "Nome base do alinhamento (sufixo automatico se ja existir)."),
            ("Nome da superficie", "string", "",
             "Vazio = clicar na superficie no desenho."),
            ("Estilo do alinhamento", "string", "",
             "Vazio = primeiro estilo do desenho."),
            ("Estilo do perfil", "string", "",
             "Vazio = primeiro estilo do desenho."),
            ("Estilo do perfil longitudinal", "string", "",
             "Profile View Style. Vazio = primeiro estilo."),
            ("Band set do perfil longitudinal", "string", "",
             "Vazio = primeiro band set."),
            ("Inverter sentido", "boolean", False,
             "Inverte o sentido do estaqueamento."),
            ("Tolerancia (m)", "number", 0.01,
             "Desvio maximo do alinhamento em relacao ao eixo calculado."),
        ],
        "EixoEntreLinhas.dyn",
    )
    gerar(
        "LigacoesPrediais",
        "Cria uma linha magenta por lote (parcel), perpendicular a rede "
        "(pipe network), do eixo do tubo ate 1 m antes do lote, junto a "
        "divisa de menor cota pela superficie existente.",
        "ligacoes_prediais.py",
        [
            ("Executar", "boolean", False, "Ative para rodar a rotina."),
            ("Nome da superficie", "string", "",
             "Superficie existente. Vazio = clicar na superficie no desenho."),
            ("Recuo do lote (m)", "number", 1.0,
             "A linha termina esta distancia antes do limite do lote."),
            ("Afastamento da divisa (m)", "number", 1.5,
             "Distancia entre a linha e a divisa lateral escolhida."),
            ("Distancia maxima rede-lote (m)", "number", 30.0,
             "Lotes mais distantes da rede sao ignorados."),
            ("Layer", "string", "LIGACOES",
             "Layer das linhas (criado em magenta se nao existir)."),
            ("Usar LINE", "boolean", False,
             "True = LINE; False = polilinha (LWPOLYLINE)."),
            ("Apagar linhas anteriores do layer", "boolean", False,
             "Apaga linhas/polilinhas ja existentes no layer antes de criar."),
        ],
        "LigacoesPrediais.dyn",
    )
