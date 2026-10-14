
import random
import string
import time
import unicodedata

from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = "alto-el-lapiz-clave-local"
socketio = SocketIO(app, async_mode="threading")

DURACION = 60

CATEGORIAS = [
    "nombre",
    "apellido",
    "lugar",
    "comida",
    "animal",
    "marca",
    "objeto"
]

LETRAS = list("ABCDEFGHIJKLMNÑOPQRSTUVWXYZ")

salas = {}
jugadores_sid = {}


def crear_codigo():
    while True:
        codigo = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if codigo not in salas:
            return codigo


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def datos_sala(codigo):
    sala = salas[codigo]

    return {
        "codigo": codigo,
        "jugadores": [
            {
                "nombre": jugador["nombre"],
                "puntos": jugador["puntos"]
            }
            for jugador in sala["jugadores"].values()
        ],
        "iniciada": sala["iniciada"],
        "terminada": sala["terminada"],
        "letra": sala["letra"],
        "duracion": DURACION
    }


def emitir_sala(codigo):
    socketio.emit("actualizar_sala", datos_sala(codigo), to=codigo)


def finalizar_ronda(codigo):
    sala = salas.get(codigo)

    if not sala or sala["terminada"] or not sala["iniciada"]:
        return

    sala["terminada"] = True
    sala["iniciada"] = False

    respuestas = {}

    for sid, jugador in sala["jugadores"].items():
        respuestas[sid] = jugador.get("respuestas", {})

    conteo = {}

    for sid, respuestas_jugador in respuestas.items():
        for categoria in CATEGORIAS:
            respuesta = normalizar(respuestas_jugador.get(categoria, ""))

            if respuesta:
                clave = (categoria, respuesta)
                conteo[clave] = conteo.get(clave, 0) + 1

    for sid, jugador in sala["jugadores"].items():
        puntos_ronda = 0
        detalle = {}

        for categoria in CATEGORIAS:
            respuesta_original = respuestas[sid].get(categoria, "").strip()
            respuesta = normalizar(respuesta_original)

            valido = (
                bool(respuesta)
                and normalizar(respuesta_original).startswith(normalizar(sala["letra"]))
                and conteo.get((categoria, respuesta), 0) == 1
            )

            puntos = 10 if valido else 0
            puntos_ronda += puntos

            detalle[categoria] = {
                "respuesta": respuesta_original or "—",
                "puntos": puntos
            }

        jugador["puntos"] += puntos_ronda
        jugador["detalle"] = detalle
        jugador["puntos_ronda"] = puntos_ronda

    clasificacion = sorted(
        [
            {
                "nombre": jugador["nombre"],
                "puntos": jugador["puntos"],
                "puntos_ronda": jugador.get("puntos_ronda", 0),
                "detalle": jugador.get("detalle", {})
            }
            for jugador in sala["jugadores"].values()
        ],
        key=lambda jugador: jugador["puntos"],
        reverse=True
    )

    socketio.emit(
        "ronda_finalizada",
        {"clasificacion": clasificacion},
        to=codigo
    )


def cerrar_ronda_despues(codigo):
    socketio.sleep(1.5)
    finalizar_ronda(codigo)


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/crear", methods=["POST"])
def crear_sala():
    nombre = request.form.get("nombre", "").strip()

    if not nombre:
        return redirect(url_for("inicio"))

    codigo = crear_codigo()

    salas[codigo] = {
        "jugadores": {},
        "anfitrion": None,
        "iniciada": False,
        "terminada": False,
        "letra": "",
        "fin": 0,
        "cerrando": False
    }

    return redirect(url_for("juego", codigo=codigo, nombre=nombre))


@app.route("/unirse", methods=["POST"])
def unirse_sala():
    nombre = request.form.get("nombre", "").strip()
    codigo = request.form.get("codigo", "").strip().upper()

    if not nombre or codigo not in salas:
        return redirect(url_for("inicio"))

    return redirect(url_for("juego", codigo=codigo, nombre=nombre))


@app.route("/juego/<codigo>")
def juego(codigo):
    if codigo not in salas:
        return redirect(url_for("inicio"))

    nombre = request.args.get("nombre", "").strip()

    if not nombre:
        return redirect(url_for("inicio"))

    return render_template("jugador.html", codigo=codigo, nombre=nombre)


@app.route("/resultado/<codigo>")
def resultado(codigo):
    sala = salas.get(codigo)

    if not sala:
        return redirect(url_for("inicio"))

    clasificacion = sorted(
        [
            {
                "nombre": jugador["nombre"],
                "puntos": jugador["puntos"],
                "puntos_ronda": jugador.get("puntos_ronda", 0),
                "detalle": jugador.get("detalle", {})
            }
            for jugador in sala["jugadores"].values()
        ],
        key=lambda jugador: jugador["puntos"],
        reverse=True
    )

    return render_template(
        "resultado.html",
        codigo=codigo,
        clasificacion=clasificacion
    )


@socketio.on("unirse_partida")
def unirse_partida(datos):
    codigo = datos.get("codigo", "").upper()
    nombre = datos.get("nombre", "").strip()

    if codigo not in salas or not nombre:
        emit("error_juego", {"mensaje": "La sala no existe o el nombre no es válido."})
        return

    sala = salas[codigo]

    if sala["iniciada"] or sala["terminada"]:
        emit("error_juego", {"mensaje": "La partida ya ha comenzado o ha terminado."})
        return

    if len(sala["jugadores"]) >= 10:
        emit("error_juego", {"mensaje": "La sala está llena."})
        return

    nombre_repetido = any(
        jugador["nombre"].lower() == nombre.lower()
        for jugador in sala["jugadores"].values()
    )

    if nombre_repetido:
        emit("error_juego", {"mensaje": "Ese nombre ya está en la sala."})
        return

    join_room(codigo)

    sala["jugadores"][request.sid] = {
        "nombre": nombre,
        "puntos": 0,
        "respuestas": {},
        "puntos_ronda": 0,
        "detalle": {}
    }

    jugadores_sid[request.sid] = codigo

    if sala["anfitrion"] is None:
        sala["anfitrion"] = request.sid

    emit(
        "bienvenido",
        {
            "anfitrion": sala["anfitrion"] == request.sid,
            "nombre": nombre
        }
    )

    emitir_sala(codigo)


@socketio.on("iniciar_ronda")
def iniciar_ronda():
    codigo = jugadores_sid.get(request.sid)

    if not codigo or codigo not in salas:
        return

    sala = salas[codigo]

    if sala["anfitrion"] != request.sid:
        emit("error_juego", {"mensaje": "Solo el anfitrión puede iniciar la ronda."})
        return

    if len(sala["jugadores"]) < 1 or sala["iniciada"]:
        return

    sala["letra"] = random.choice(LETRAS)
    sala["iniciada"] = True
    sala["terminada"] = False
    sala["cerrando"] = False
    sala["fin"] = time.time() + DURACION

    for jugador in sala["jugadores"].values():
        jugador["respuestas"] = {}
        jugador["detalle"] = {}
        jugador["puntos_ronda"] = 0

    socketio.emit(
        "ronda_iniciada",
        {
            "letra": sala["letra"],
            "duracion": DURACION,
            "fin": sala["fin"]
        },
        to=codigo
    )

    socketio.start_background_task(
        esperar_fin,
        codigo,
        sala["fin"]
    )

    emitir_sala(codigo)


def esperar_fin(codigo, fin):
    while time.time() < fin:
        socketio.sleep(0.25)

        sala = salas.get(codigo)

        if not sala or not sala["iniciada"] or sala["fin"] != fin:
            return

    pedir_respuestas(codigo)


def pedir_respuestas(codigo):
    sala = salas.get(codigo)

    if not sala or not sala["iniciada"] or sala["cerrando"]:
        return

    sala["cerrando"] = True

    socketio.emit("tiempo_terminado", {}, to=codigo)
    socketio.start_background_task(cerrar_ronda_despues, codigo)


@socketio.on("alto_el_lapiz")
def alto_el_lapiz(datos):
    codigo = jugadores_sid.get(request.sid)

    if not codigo or codigo not in salas:
        return

    sala = salas[codigo]

    if not sala["iniciada"] or sala["cerrando"]:
        return

    sala["cerrando"] = True

    socketio.emit(
        "preparar_cierre",
        {"jugador": sala["jugadores"][request.sid]["nombre"]},
        to=codigo
    )

    socketio.start_background_task(cerrar_ronda_despues, codigo)


@socketio.on("enviar_respuestas")
def enviar_respuestas(datos):
    codigo = jugadores_sid.get(request.sid)

    if not codigo or codigo not in salas:
        return

    sala = salas[codigo]

    if not sala["iniciada"]:
        return

    jugador = sala["jugadores"].get(request.sid)

    if not jugador:
        return

    respuestas = datos.get("respuestas", {})

    jugador["respuestas"] = {
        categoria: str(respuestas.get(categoria, "")).strip()[:100]
        for categoria in CATEGORIAS
    }


@socketio.on("disconnect")
def desconectar():
    codigo = jugadores_sid.pop(request.sid, None)

    if not codigo or codigo not in salas:
        return

    sala = salas[codigo]
    jugador = sala["jugadores"].pop(request.sid, None)

    if jugador:
        socketio.emit(
            "jugador_salio",
            {"nombre": jugador["nombre"]},
            to=codigo
        )

    if sala["anfitrion"] == request.sid:
        sala["anfitrion"] = next(iter(sala["jugadores"]), None)

    emitir_sala(codigo)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
