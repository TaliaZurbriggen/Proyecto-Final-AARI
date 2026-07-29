#!/usr/bin/env python3
"""
Validador minimo de la base de conocimiento (base_conocimiento.json) de AARI.
No depende de APIs externas ni de librerias de terceros: solo stdlib.

Uso:
    python3 validate_kb.py base_conocimiento.json

Chequeos que realiza:
  1. El archivo es JSON valido.
  2. Estan presentes las claves de nivel superior requeridas.
  3. categorias_validas contiene exactamente ordinario/extraordinario/expensa.
  4. Cada regla tiene los campos minimos obligatorios y tipos correctos.
  5. Los IDs de regla son unicos.
  6. clasificacion_default, cuando no es null, pertenece a categorias_validas.
  7. Toda regla con clasificacion_default = null debe declarar una accion
     (ej. escalar_urgente) — coherencia entre "no clasifica" y "que hace en su lugar".
  8. Toda regla con accion definida (ej. escalar_urgente) tiene
     clasificacion_default = null, para evitar contradicciones.
  9. confianza_base pertenece a un set de valores esperados.
  10. Si admite_override_contractual = false, la regla debe tener fundamento_legal
      o nota explicando por que es una norma imperativa (evita marcar overrides
      prohibidos sin justificacion).
  11. umbral_confianza_escalado.valor: si no es null, debe ser numerico entre 0 y 1.
  12. Reporta cuantas reglas tienen revision_pendiente = true, como recordatorio
      de que la validacion de dominio con Oikos / revision juridica sigue abierta.

El script termina con exit code 0 si no hay errores (los warnings no bloquean),
y exit code 1 si hay al menos un error.
"""

import json
import sys

CAMPOS_OBLIGATORIOS_REGLA = {"id", "rubro", "descripcion", "clasificacion_default", "confianza_base"}
CONFIANZAS_VALIDAS = {"alta", "media", "baja", "n/a"}
CATEGORIAS_ESPERADAS = {"ordinario", "extraordinario", "expensa"}


def cargar_json(path):
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: el archivo no es JSON valido: {e}")
            sys.exit(1)


def validar(data):
    errores = []
    warnings = []

    # 1. Claves de nivel superior
    claves_requeridas = [
        "version", "fecha_actualizacion", "marco_legal", "categorias_validas",
        "principio_general", "reglas", "excepciones_contractuales",
        "disparadores_escalado_obligatorio", "umbral_confianza_escalado",
    ]
    for clave in claves_requeridas:
        if clave not in data:
            errores.append(f"Falta la clave de nivel superior obligatoria: '{clave}'")

    # 2. categorias_validas
    categorias = set(data.get("categorias_validas", []))
    if categorias != CATEGORIAS_ESPERADAS:
        errores.append(
            f"categorias_validas debe ser exactamente {CATEGORIAS_ESPERADAS}, "
            f"se encontro {categorias}"
        )

    # 3. Reglas
    reglas = data.get("reglas", [])
    if not isinstance(reglas, list) or len(reglas) == 0:
        errores.append("'reglas' debe ser una lista no vacia")
        reglas = []

    ids_vistos = set()
    revision_pendiente_count = 0

    for i, regla in enumerate(reglas):
        etiqueta = regla.get("id", f"<sin id, indice {i}>")

        faltantes = CAMPOS_OBLIGATORIOS_REGLA - regla.keys()
        if faltantes:
            errores.append(f"Regla '{etiqueta}': faltan campos obligatorios {faltantes}")

        rid = regla.get("id")
        if rid is not None:
            if rid in ids_vistos:
                errores.append(f"ID de regla duplicado: '{rid}'")
            ids_vistos.add(rid)

        clasificacion = regla.get("clasificacion_default", "___missing___")
        if clasificacion not in (None, "___missing___") and clasificacion not in CATEGORIAS_ESPERADAS:
            errores.append(
                f"Regla '{etiqueta}': clasificacion_default '{clasificacion}' "
                f"no esta en {CATEGORIAS_ESPERADAS}"
            )

        accion = regla.get("accion")
        if clasificacion is None and not accion:
            errores.append(
                f"Regla '{etiqueta}': clasificacion_default es null pero no declara "
                f"'accion' (ej. escalar_urgente); queda ambigua sobre que hacer"
            )
        if accion and clasificacion not in (None, "___missing___"):
            errores.append(
                f"Regla '{etiqueta}': declara 'accion' ({accion}) pero tambien tiene "
                f"clasificacion_default distinto de null; es contradictorio"
            )

        confianza = regla.get("confianza_base")
        if confianza not in CONFIANZAS_VALIDAS:
            errores.append(
                f"Regla '{etiqueta}': confianza_base '{confianza}' no esta en {CONFIANZAS_VALIDAS}"
            )

        if regla.get("admite_override_contractual") is False:
            if not regla.get("fundamento_legal") and not regla.get("nota"):
                errores.append(
                    f"Regla '{etiqueta}': admite_override_contractual=false sin "
                    f"'fundamento_legal' ni 'nota' que lo justifique"
                )

        if regla.get("revision_pendiente") is True:
            revision_pendiente_count += 1

        if not regla.get("fundamento_legal") and clasificacion not in (None, "___missing___"):
            warnings.append(
                f"Regla '{etiqueta}': tiene clasificacion_default pero no declara "
                f"'fundamento_legal' (recomendado para trazabilidad)"
            )

    # 4. umbral_confianza_escalado
    umbral = data.get("umbral_confianza_escalado", {})
    valor_umbral = umbral.get("valor")
    if valor_umbral is not None:
        if not isinstance(valor_umbral, (int, float)) or not (0 <= valor_umbral <= 1):
            errores.append(
                f"umbral_confianza_escalado.valor debe ser null o un numero entre 0 y 1, "
                f"se encontro {valor_umbral!r}"
            )

    # 5. Resumen de validacion de dominio
    if revision_pendiente_count > 0:
        warnings.append(
            f"{revision_pendiente_count} regla(s) con revision_pendiente=true: "
            f"aun no confirmadas con Oikos ni revisadas juridicamente"
        )

    validacion_dominio = data.get("validacion_dominio", {})
    if not validacion_dominio.get("validado_por"):
        warnings.append(
            "validacion_dominio.validado_por esta vacio: la base de conocimiento "
            "aun no tiene una validacion de dominio registrada"
        )

    return errores, warnings


def main():
    if len(sys.argv) != 2:
        print(f"Uso: python3 {sys.argv[0]} <ruta_al_json>")
        sys.exit(1)

    data = cargar_json(sys.argv[1])
    errores, warnings = validar(data)

    print(f"Reglas encontradas: {len(data.get('reglas', []))}")
    print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
        print()

    if errores:
        print(f"ERRORES ({len(errores)}):")
        for e in errores:
            print(f"  - {e}")
        print()
        print("Resultado: INVALIDO")
        sys.exit(1)
    else:
        print("Resultado: VALIDO (sin errores bloqueantes)")
        sys.exit(0)


if __name__ == "__main__":
    main()
