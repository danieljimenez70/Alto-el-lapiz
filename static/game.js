
const juego = document.querySelector("#juego");
const codigo = juego.dataset.codigo;
const nombre = juego.dataset.nombre;

const estado = document.querySelector("#estado");
const listaJugadores = document.querySelector("#lista-jugadores");
const totalJugadores = document.querySelector("#total-jugadores");
const botonIniciar = document.querySelector("#iniciar");
const botonAlto = document.querySelector("#alto");
const letraElemento = document.querySelector("#letra");
const tiempoElemento = document.querySelector("#tiempo");
const formulario = document.querySelector("#formulario-respuestas");
const mensaje = document.querySelector("#mensaje");

const socket = io();

let esAnfitrion = false;
let partidaIniciada = false;
let enviandoRespuestas = false;
let finRonda = 0;
let temporizador = null;

const campos = Array.from(
    document.querySelectorAll("[data-categoria]")
);

function obtenerRespuestas() {
    const respuestas = {};

    campos.forEach(function (campo) {
        respuestas[campo.dataset.categoria] = campo.value.trim();
    });

    return respuestas;
}

function enviarRespuestas() {
    if (enviandoRespuestas) {
        return;
    }

    enviandoRespuestas = true;

    socket.emit("enviar_respuestas", {
        respuestas: obtenerRespuestas()
    });

    campos.forEach(function (campo) {
        campo.disabled = true;
    });

    botonAlto.disabled = true;
}

function activarCampos(activar) {
    campos.forEach(function (campo) {
        campo.disabled = !activar;
    });

    botonAlto.disabled = !activar;
}

function actualizarJugadores(jugadores) {
    listaJugadores.replaceChildren();

    totalJugadores.textContent =
        jugadores.length +
        (jugadores.length === 1 ? " jugador" : " jugadores");

    if (jugadores.length === 0) {
        const elemento = document.createElement("li");
        elemento.className = "vacio";
        elemento.textContent = "Esperando jugadores...";
        listaJugadores.appendChild(elemento);
        return;
    }

    jugadores.forEach(function (jugador) {
        const elemento = document.createElement("li");
        elemento.textContent =
            jugador.nombre + " — " + jugador.puntos + " puntos";

        listaJugadores.appendChild(elemento);
    });
}

socket.on("connect", function () {
    socket.emit("unirse_partida", {
        codigo: codigo,
        nombre: nombre
    });
});

socket.on("bienvenido", function (datos) {
    esAnfitrion = datos.anfitrion;

    botonIniciar.hidden = !esAnfitrion;
    estado.textContent = esAnfitrion
        ? "Eres el anfitrión. Puedes comenzar la partida."
        : "Esperando a que el anfitrión comience.";

    mensaje.textContent = "";
});

socket.on("error_juego", function (datos) {
    estado.textContent = datos.mensaje;
    botonIniciar.hidden = true;
    activarCampos(false);
});

socket.on("actualizar_sala", function (datos) {
    actualizarJugadores(datos.jugadores);

    if (!datos.iniciada && !datos.terminada && !partidaIniciada) {
        estado.textContent = esAnfitrion
            ? "La sala está lista. Pulsa para comenzar."
            : "Esperando a que comience la partida.";
    }
});

botonIniciar.addEventListener("click", function () {
    socket.emit("iniciar_ronda");
});

socket.on("ronda_iniciada", function (datos) {
    partidaIniciada = true;
    enviandoRespuestas = false;
    finRonda = datos.fin * 1000;

    letraElemento.textContent = datos.letra;
    mensaje.textContent = "";
    estado.textContent = "¡La ronda ha comenzado!";

    formulario.reset();
    activarCampos(true);

    botonIniciar.hidden = true;

    if (temporizador) {
        clearInterval(temporizador);
    }

    function actualizarTiempo() {
        const restante = Math.max(
            0,
            Math.ceil((finRonda - Date.now()) / 1000)
        );

        tiempoElemento.textContent = restante;

        if (restante <= 0 && temporizador) {
            clearInterval(temporizador);
            temporizador = null;
        }
    }

    actualizarTiempo();
    temporizador = setInterval(actualizarTiempo, 250);
});

botonAlto.addEventListener("click", function () {
    if (!partidaIniciada || enviandoRespuestas) {
        return;
    }

    enviarRespuestas();
    mensaje.textContent = "Has pedido parar la ronda. Esperando resultados...";
    socket.emit("alto_el_lapiz", {});
});

socket.on("preparar_cierre", function (datos) {
    enviarRespuestas();
    estado.textContent =
        datos.jugador + " ha dicho: ¡Alto el lápiz!";
    mensaje.textContent = "La ronda está terminando...";
});

socket.on("tiempo_terminado", function () {
    enviarRespuestas();
    estado.textContent = "Se ha acabado el tiempo.";
    mensaje.textContent = "Calculando puntuaciones...";
});

socket.on("ronda_finalizada", function (datos) {
    partidaIniciada = false;

    if (temporizador) {
        clearInterval(temporizador);
        temporizador = null;
    }

    activarCampos(false);
    estado.textContent = "Ronda finalizada. Consulta la clasificación.";

    sessionStorage.setItem(
        "clasificacionAltoLapiz",
        JSON.stringify(datos.clasificacion)
    );

    window.location.href = "/resultado/" + codigo;
});

socket.on("jugador_salio", function (datos) {
    mensaje.textContent = datos.nombre + " ha salido de la sala.";
});

socket.on("disconnect", function () {
    estado.textContent = "Conexión perdida. Intentando reconectar...";
});
