###############################################################################################
############################## DATOS SINTÉTICOS DE LA DEMO PÚBLICA ############################
###############################################################################################
# Genera pedidos ficticios de una planta metalmecánica: clientes, productos, familias, fechas,
# lead times por área, el estado de cada línea y su historial de movimientos. Nada sale de una
# base real: todo se inventa aquí, con una semilla fija para que la demo sea reproducible.
#
# Cómo se construyen las fechas (el mismo modelo S-DBR que usan las pantallas):
#   - cada pedido tiene una fecha comprometida (Fecha_Venci_Espejo) y un lead time total que se
#     reparte entre Ingeniería, Ops, Almacén y Producción según su familia;
#   - las fechas fin de cada área salen hacia atrás desde la comprometida;
#   - la fecha del pedido (FechaDocumen) es anterior a su liberación y nunca futura.
# Para que la pantalla tenga de todo, cada pedido se "ancla": se elige un área y la zona de color
# que debe tener allí hoy, y las fechas se despejan de ahí. Las demás líneas del pedido van en la
# misma área, una antes o una después, y su color sale de las fechas.
#
# Este módulo es puro (no toca la base): demo/instalar.py lo usa para llenar las tablas.

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

SEMILLA = 2026
NUM_PEDIDOS = 150
PRIMER_PEDIDO = 48001

AREAS_FLUJO = ("Ingenieria", "Planeacion", "Almacen", "Produccion", "Despachos")
DEROGACION = "Derogacion"

# Fecha fin y lead time con que cada pantalla calcula el buffer del área (como en escritorio).
FECHA_Y_LEAD = {
    "Ingenieria": ("Final_Inge", "Buffer_Ing"),
    "Planeacion": ("Final_Plane", "Buffer_Plane"),
    "Almacen": ("Final_Compras", "Buffer_Compras"),
    "Produccion": ("Fecha_Venci_Espejo", "Buffer_Manuf"),
    "Despachos": ("Fecha_Venci_Espejo", "Buffer_Manuf"),
}

# En qué área se ancla cada pedido. Ingeniería pesa más: es la pantalla que ya está en la web.
PESO_ANCLA = {
    "Ingenieria": 0.34,
    "Planeacion": 0.14,
    "Almacen": 0.18,
    "Produccion": 0.24,
    "Despachos": 0.10,
}

# Zona objetivo del ancla: (buffer mínimo, máximo, peso). Blanco, verde, amarillo, rojo, negro.
ZONAS_OBJETIVO = (
    (-70, -5, 0.10),
    (2, 32, 0.24),
    (35, 65, 0.28),
    (68, 99, 0.22),
    (103, 170, 0.16),
)

CLIENTES = (
    "Constructora Ejemplo S.A.",
    "Minera Demo Ltda.",
    "Hidroeléctrica Ficticia S.A. E.S.P.",
    "Cementos de Prueba S.A.",
    "Ingenio Azucarero Modelo S.A.",
    "Petrolera Ejemplo S.A.S.",
    "Siderúrgica Demo S.A.S.",
    "Astillero Ficticio Ltda.",
    "Papelera Modelo S.A.",
    "Acueducto Ejemplo E.S.P.",
    "Transportes Demo S.A.S.",
    "Agroindustria Modelo S.A.",
    "Metalmecánica de Prueba Ltda.",
    "Termoeléctrica Ficticia S.A.",
    "Ferrocarril Ejemplo S.A.",
)

VENDEDORES = (
    "Asesor Zona Norte",
    "Asesor Zona Centro",
    "Asesor Zona Sur",
    "Asesor Exportaciones",
    "Asesor Repuestos",
)

# Familia: (prefijo del código, lead time total en días (mín, máx), reparto Ing/Ops/Almacén/Prod)
FAMILIAS = {
    "BRIDAS": ("BR", (25, 40), (0.15, 0.10, 0.30, 0.45)),
    "EJES": ("EJ", (35, 55), (0.20, 0.10, 0.25, 0.45)),
    "ENGRANAJES": ("EN", (45, 70), (0.25, 0.10, 0.25, 0.40)),
    "PIÑONES": ("PI", (40, 60), (0.25, 0.10, 0.25, 0.40)),
    "RODILLOS": ("RO", (30, 50), (0.15, 0.10, 0.30, 0.45)),
    "PIEZAS ESPECIALES": ("PE", (60, 90), (0.30, 0.10, 0.25, 0.35)),
    "REPUESTOS": ("RP", (15, 25), (0.10, 0.10, 0.35, 0.45)),
}


def _descripcion(familia, azar):
    if familia == "BRIDAS":
        return (
            f'Brida forjada {azar.choice([2, 3, 4, 6, 8, 10, 12])}" '
            f"clase {azar.choice([150, 300, 600])}"
        )
    if familia == "EJES":
        return (
            f"Eje de transmisión Ø{azar.choice([40, 60, 80, 100, 120])} mm "
            f"x {azar.choice([500, 800, 1200, 1800])} mm"
        )
    if familia == "ENGRANAJES":
        return (
            f"Engranaje recto de {azar.randint(18, 96)} dientes "
            f"módulo {azar.choice([3, 4, 5, 6, 8])}"
        )
    if familia == "PIÑONES":
        return f"Piñón cónico de {azar.randint(12, 40)} dientes"
    if familia == "RODILLOS":
        return f"Rodillo de apoyo Ø{azar.choice([150, 200, 250, 300, 400])} mm"
    if familia == "PIEZAS ESPECIALES":
        return azar.choice(
            [
                f"Gancho forjado de {azar.choice([5, 10, 20, 32])} t",
                f"Anillo laminado Ø{azar.choice([600, 900, 1200, 1500])} mm",
                f"Pieza especial según plano DM-{azar.randint(100, 999)}",
            ]
        )
    return azar.choice(
        [
            f"Buje de bronce Ø{azar.choice([30, 45, 60, 75])} mm",
            f"Pasador templado Ø{azar.choice([12, 16, 20, 25])} mm",
        ]
    )


@dataclass
class DatosDemo:
    """Filas listas para insertar, con las fechas del día de generación."""

    fecha_generacion: date
    semilla: int
    lineas: list = field(default_factory=list)  # Demo_Lineas
    estados: list = field(default_factory=list)  # SDBR_MOV y Demo_Estado_Inicial
    historial: list = field(default_factory=list)  # Demo_Historial_Inicial
    vendedores: list = field(default_factory=list)  # vendedores_pedidos


def _elegir(azar, pesos):
    return azar.choices(list(pesos), weights=list(pesos.values()))[0]


def _lead_times(azar, familia):
    _, (minimo, maximo), reparto = FAMILIAS[familia]
    total = azar.randint(minimo, maximo)
    ing, plane, compras = (max(1, round(total * p)) for p in reparto[:3])
    return {
        "Buffer_Ing": ing,
        "Buffer_Plane": plane,
        "Buffer_Compras": compras,
        "Buffer_Manuf": max(1, total - ing - plane - compras),
    }


def _fechas_desde_el_ancla(azar, hoy, area, leads):
    """Fechas del pedido para que su línea ancla tenga hoy un buffer de la zona elegida."""
    minimo, maximo, _ = azar.choices(
        ZONAS_OBJETIVO, weights=[z[2] for z in ZONAS_OBJETIVO]
    )[0]
    buffer = azar.randint(minimo, maximo)
    columna_fecha, columna_lead = FECHA_Y_LEAD[area]
    fin_ancla = hoy + timedelta(days=round((1 - buffer / 100) * leads[columna_lead]))
    # Hacia atrás desde la fecha comprometida.
    retraso = {
        "Fecha_Venci_Espejo": 0,
        "Final_Compras": leads["Buffer_Manuf"],
        "Final_Plane": leads["Buffer_Manuf"] + leads["Buffer_Compras"],
        "Final_Inge": leads["Buffer_Manuf"]
        + leads["Buffer_Compras"]
        + leads["Buffer_Plane"],
    }
    venci = fin_ancla + timedelta(days=retraso[columna_fecha])
    fechas = {col: venci - timedelta(days=dias) for col, dias in retraso.items()}
    liberacion = fechas["Final_Inge"] - timedelta(days=leads["Buffer_Ing"])
    fechas["FechaDocumen"] = min(liberacion, hoy) - timedelta(days=azar.randint(0, 6))
    return fechas


def _area_de_la_linea(azar, ancla):
    """La mayoría de líneas van con el ancla; algunas se retrasan o se adelantan un área."""
    i = AREAS_FLUJO.index(ancla)
    paso = azar.choices((0, -1, 1), weights=(0.6, 0.25, 0.15))[0]
    return AREAS_FLUJO[min(max(i + paso, 0), len(AREAS_FLUJO) - 1)]


def _buffer(fin, lead, momento):
    dias = (fin - momento).total_seconds() / 86400.0
    return round((1 - dias / abs(lead)) * 100)


def _momento_laboral(azar, dia):
    return datetime.combine(dia, time(azar.randint(7, 16), azar.randint(0, 59)))


def _historial_del_pedido(azar, pedido, fechas, leads, lineas, ahora):
    """Movimientos pasados de cada línea hasta su área actual, con Parcial/Ultimo como la web."""
    inicio = fechas["FechaDocumen"]
    salidas = []  # (fecha, producto, sale_de, entra_a)
    for producto, estado in lineas:
        if estado == DEROGACION:
            recorrido = ["Ingenieria", DEROGACION]
        else:
            recorrido = list(AREAS_FLUJO[: AREAS_FLUJO.index(estado) + 1])
        pasos = len(recorrido) - 1
        if pasos == 0:
            continue
        # Reparte el tiempo transcurrido entre las áreas ya recorridas.
        transcurrido = max((ahora - inicio).total_seconds(), 3600.0 * pasos)
        cortes = sorted(azar.uniform(0.1, 0.95) for _ in range(pasos))
        for (sale, entra), corte in zip(zip(recorrido, recorrido[1:]), cortes):
            momento = inicio + timedelta(seconds=transcurrido * corte)
            momento = min(_momento_laboral(azar, momento.date()), ahora)
            salidas.append((momento, producto, sale, entra))

    filas = []
    total_pedido = (fechas["Fecha_Venci_Espejo"] - fechas["FechaDocumen"]).days or 1
    estados = dict(lineas)
    for momento, producto, sale, entra in sorted(salidas):
        columna_fecha, columna_lead = FECHA_Y_LEAD.get(
            sale, ("Final_Inge", "Buffer_Ing")
        )
        buffer_zona = _buffer(fechas[columna_fecha], leads[columna_lead], momento)
        global_ = (
            1 - (fechas["Fecha_Venci_Espejo"] - momento).days / total_pedido
        ) * 100
        filas.append(
            {
                "Fecha_Mov": momento,
                "Pedido": pedido,
                "Producto": producto,
                "Sale_De": sale,
                "Entra_A": entra,
                "Fecha_PSL": fechas["Fecha_Venci_Espejo"],
                "Tiempo_Pedido": round(global_),
                "On_time": 0 if buffer_zona > 100 else 1,
                "Buffer_Zona": buffer_zona,
                "Retroceso": "No",
                "Calificacion": "Parcial",
            }
        )

    # 'Ultimo': la última salida de un área cuando ya no le queda ninguna línea del pedido.
    for area in AREAS_FLUJO:
        quedan = any(
            estado != DEROGACION
            and AREAS_FLUJO.index(estado) <= AREAS_FLUJO.index(area)
            for estado in estados.values()
        )
        de_aqui = [f for f in filas if f["Sale_De"] == area]
        if de_aqui and not quedan:
            de_aqui[-1]["Calificacion"] = "Ultimo"
    return filas


def generar(hoy=None, semilla=SEMILLA, num_pedidos=NUM_PEDIDOS):
    """Genera todos los datos de la demo para el día `hoy` (por defecto, hoy)."""
    hoy = hoy or date.today()
    medianoche = datetime.combine(hoy, time())
    ahora = medianoche + timedelta(hours=7)  # el historial termina esta mañana
    azar = random.Random(semilla)
    datos = DatosDemo(fecha_generacion=hoy, semilla=semilla)
    codigos_usados = set()
    sin_familia, sin_lead = 0, 0

    for n in range(num_pedidos):
        pedido = str(PRIMER_PEDIDO + n)
        cliente = azar.choice(CLIENTES)
        datos.vendedores.append(
            {"peeconsecutivo": pedido, "tgenombre": azar.choice(VENDEDORES)}
        )
        familia_pedido = azar.choice(list(FAMILIAS))
        leads = _lead_times(azar, familia_pedido)
        ancla = _elegir(azar, PESO_ANCLA)
        fechas = _fechas_desde_el_ancla(azar, medianoche, ancla, leads)
        despachado = azar.random() < 0.06
        num_lineas = azar.choices((1, 2, 3, 4, 5, 6), weights=(18, 28, 24, 15, 9, 6))[0]

        lineas_pedido = []
        for i in range(num_lineas):
            familia = (
                familia_pedido if azar.random() < 0.7 else azar.choice(list(FAMILIAS))
            )
            prefijo = FAMILIAS[familia][0]
            codigo = f"{prefijo}-{azar.randint(100, 9999):04d}"
            while (pedido, codigo) in codigos_usados:
                codigo = f"{prefijo}-{azar.randint(100, 9999):04d}"
            codigos_usados.add((pedido, codigo))

            if despachado:
                estado = "Despachos"
            elif azar.random() < 0.04:
                estado = DEROGACION
            else:
                estado = ancla if i == 0 else _area_de_la_linea(azar, ancla)

            fila = {
                "pedconsecutivo": pedido,
                "Producto": codigo,
                "Descripcion": _descripcion(familia, azar),
                "NombCliente": cliente,
                "NombreFamilia": familia,
                "Cantidad": azar.choice((1, 2, 2, 4, 5, 6, 8, 10, 12, 20, 25, 50)),
                **fechas,
                **leads,
            }
            # Casos que la web ya contempla: línea sin familia y buffer no calculable.
            if estado != DEROGACION and n % 23 == 5 and sin_familia < 6:
                fila["NombreFamilia"] = None
                sin_familia += 1
            if estado == "Ingenieria" and n % 37 == 11 and sin_lead < 2:
                fila["Buffer_Ing"] = 0
                sin_lead += 1
            datos.lineas.append(fila)
            datos.estados.append(
                {
                    "pedconsecutivo": pedido,
                    "producto": codigo,
                    "Estado_SDBR": estado,
                    "Estado_Final": "Despachado" if despachado else "En_planta",
                }
            )
            lineas_pedido.append((codigo, estado))

        datos.historial.extend(
            _historial_del_pedido(azar, pedido, fechas, leads, lineas_pedido, ahora)
        )
    return datos
