"use strict";

/*
 * Simulador del estudiante.
 * Regla RF-14: durante el juego solo se usan los datos de la vista de estudiante
 * (sin es_correcta ni justificación). La corrección aparece únicamente en /app/resultado.
 * El tiempo restante SIEMPRE viene del servidor (segundos_restantes); el cliente solo
 * lo cuenta hacia atrás entre una respuesta del servidor y la siguiente.
 */

(function () {
  const claims = Api.exigirRol("ESTUDIANTE");
  if (!claims) return;

  const h = Dom.h.bind(Dom);
  const $ = Dom.$;
  const escena = $("#escena");
  const hud = $("#hud");
  const barraBriefing = $("#barra-briefing");

  const LETRAS = "ABCDEFGHIJ";
  const UMBRAL_ALERTA_SEG = 300;
  const RESINCRONIZAR_CADA_MS = 20000;

  const estado = {
    caso: null,
    preguntas: [], // lista plana: { escenario, pregunta, posicion }
    participacion: null,
    respuestas: new Map(), // pregunta_id -> opcion_id confirmada por el servidor
    indice: 0,
    guardando: false,
    finalizando: false,
    reloj: { finMs: 0, intervalo: null, ultimoSync: 0 },
  };

  /* ---------- unirse a una sesión con el código (cuenta registrada) ---------- */

  function mostrarUnirseConCodigo() {
    const usuario = Api.usuario() || {};
    const entrada = h("input", {
      type: "text",
      id: "codigo-sesion",
      autocomplete: "off",
      autocapitalize: "characters",
      required: true,
      placeholder: "Ej.: 2L3Q5RSY",
    });
    const boton = h("button", { type: "submit", clase: "boton boton-grande boton-principal" }, "UNIRME");
    const formulario = h(
      "form",
      {
        novalidate: true,
        onsubmit: async (evento) => {
          evento.preventDefault();
          const codigo = entrada.value.trim();
          if (!codigo) {
            Aviso.error("Escribe el código que te dio tu docente.");
            return;
          }
          boton.disabled = true;
          boton.classList.add("cargando");
          try {
            const respuesta = await Api.post(
              "/auth/student-login",
              { correo: usuario.correo, codigo },
              { credenciales: true },
            );
            Api.guardarSesion(respuesta.token_acceso, respuesta.usuario || usuario);
            window.location.reload();
          } catch (error) {
            Aviso.deError(error);
            boton.disabled = false;
            boton.classList.remove("cargando");
          }
        },
      },
      h("label", { clase: "campo" }, h("span", {}, "Código de tu sesión"), entrada),
      boton,
    );

    hud.classList.add("oculto");
    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "briefing aparece" },
        h("p", { clase: "kicker" }, usuario.nombre ? `Hola, ${usuario.nombre}` : "Bienvenido/a"),
        h("h1", { clase: "titulo-caso" }, "Únete a una sesión"),
        h(
          "div",
          { clase: "tarjeta elevada tarjeta-historia" },
          h("p", { clase: "texto-historia" }, "Tu docente te dará un código cuando te convoque a una sesión. Escríbelo aquí para empezar el caso."),
          formulario,
        ),
      ),
    );
  }

  /* ---------- carga inicial ---------- */

  function ordenar(lista) {
    return [...lista].sort((a, b) => a.orden - b.orden);
  }

  function aplanar(caso) {
    const plana = [];
    ordenar(caso.escenarios).forEach((escenario, indiceEscenario) => {
      ordenar(escenario.preguntas).forEach((pregunta, indicePregunta) => {
        plana.push({
          escenario,
          numeroEscenario: indiceEscenario + 1,
          primeraDelEscenario: indicePregunta === 0,
          pregunta,
        });
      });
    });
    return plana;
  }

  async function intentar(promesa) {
    try {
      return await promesa;
    } catch (error) {
      if (error instanceof ErrorApi && error.estado === 401) throw error;
      return null;
    }
  }

  async function iniciar() {
    if (!claims.caso_id || !claims.convocatoria_id) {
      // Estudiante registrado que entró con contraseña: aún no eligió su sesión.
      mostrarUnirseConCodigo();
      return;
    }
    try {
      estado.caso = await Api.get(`/cases/${encodeURIComponent(claims.caso_id)}/vista-estudiante`);
    } catch (error) {
      Aviso.deError(error);
      Dom.reemplazar(escena, h("div", { clase: "tarjeta centrado" }, h("p", {}, "No se pudo cargar el caso. Recarga la página para intentarlo de nuevo.")));
      return;
    }
    estado.preguntas = aplanar(estado.caso);

    const convocatoria = encodeURIComponent(claims.convocatoria_id);
    const [enCurso, resultadoPrevio] = await Promise.all([
      intentar(Api.get(`/participations/by-convocatoria/${convocatoria}`)),
      intentar(Api.get(`/convocatorias/${convocatoria}/result`)),
    ]);
    mostrarBriefing(enCurso, resultadoPrevio);
  }

  /* ---------- briefing ---------- */

  function mostrarBriefing(enCurso, resultadoPrevio) {
    hud.classList.add("oculto");
    barraBriefing.classList.remove("oculto");
    const caso = estado.caso;
    const nombreEstudiante = (Api.usuario() || {}).nombre;
    const escenarios = caso.escenarios.length;

    const boton = h("button", {
      type: "button",
      clase: "boton boton-grande boton-principal boton-comenzar",
      texto: enCurso ? "CONTINUAR CASO" : "COMENZAR CASO",
      onclick: () => comenzar(boton),
    });

    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "briefing aparece" },
        h("p", { clase: "kicker" }, nombreEstudiante ? `Bienvenido/a, ${nombreEstudiante}` : "Nuevo caso"),
        h("h1", { clase: "titulo-caso" }, caso.nombre),
        h(
          "div",
          { clase: "tarjeta elevada tarjeta-historia" },
          h("h2", { clase: "titulo-tarjeta" }, "📖 La historia"),
          h("p", { clase: "texto-historia" }, caso.contexto_historia),
          caso.desarrollo_situacional &&
            h(
              "details",
              { clase: "detalles" },
              h("summary", {}, "Desarrollo de la situación"),
              h("p", { clase: "texto-historia" }, caso.desarrollo_situacional),
            ),
        ),
        h(
          "ul",
          { clase: "datos-briefing" },
          h("li", {}, h("strong", {}, `${caso.tiempo_estimado_min} min`), h("span", {}, "tiempo estimado")),
          h("li", {}, h("strong", {}, String(escenarios)), h("span", {}, escenarios === 1 ? "escenario" : "escenarios")),
          h("li", {}, h("strong", {}, String(estado.preguntas.length)), h("span", {}, "preguntas")),
        ),
        enCurso &&
          h("p", { clase: "ayuda centrado" }, "Tienes una participación en curso. El tiempo sigue corriendo."),
        boton,
        resultadoPrevio &&
          h("a", { clase: "boton boton-fantasma boton-bloque", href: "/app/resultado" }, "Ver mi resultado anterior"),
      ),
    );
  }

  async function comenzar(boton) {
    boton.disabled = true;
    boton.classList.add("cargando");
    try {
      const participacion = await Api.post(
        `/participations/start/${encodeURIComponent(claims.convocatoria_id)}`,
      );
      empezarJuego(participacion);
    } catch (error) {
      boton.disabled = false;
      boton.classList.remove("cargando");
      let mensaje = Api.mensajeDe(error);
      const limite = error.detalles && error.detalles.limite_ingreso;
      if (limite) mensaje += ` (límite de ingreso: ${Fechas.formatear(limite)})`;
      Aviso.error(mensaje);
    }
  }

  /* ---------- juego ---------- */

  function empezarJuego(participacion) {
    estado.participacion = participacion;
    estado.respuestas = new Map(
      participacion.respuestas_actuales.map((r) => [r.pregunta_id, r.opcion_id]),
    );
    barraBriefing.classList.add("oculto");
    hud.classList.remove("oculto");
    document.body.classList.add("jugando");

    const primeraSinResponder = estado.preguntas.findIndex(
      (p) => !estado.respuestas.has(p.pregunta.id),
    );
    estado.indice = primeraSinResponder === -1 ? estado.preguntas.length - 1 : primeraSinResponder;

    sincronizarProgreso(participacion.progreso);
    arrancarReloj();
    // Al retomar a mitad de un capítulo no se repite la portada.
    const mostrarPortada = estado.respuestas.size === 0 || estado.preguntas[estado.indice].primeraDelEscenario;
    irA(estado.indice, { portada: mostrarPortada });
  }

  function irA(indice, { portada = false } = {}) {
    estado.indice = indice;
    const paso = estado.preguntas[indice];
    $("#hud-contador").textContent = `Pregunta ${indice + 1} de ${estado.preguntas.length}`;
    window.scrollTo({ top: 0 });
    if (portada && paso.primeraDelEscenario) pintarCapitulo(paso);
    else pintarPregunta(paso);
  }

  function pintarCapitulo(paso) {
    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "capitulo aparece" },
        h("p", { clase: "kicker" }, `Capítulo ${paso.numeroEscenario}`),
        h("h2", { clase: "titulo-capitulo" }, paso.escenario.titulo),
        h("div", { clase: "tarjeta elevada tarjeta-historia" }, h("p", { clase: "texto-historia" }, paso.escenario.contexto)),
        h("button", {
          type: "button",
          clase: "boton boton-grande boton-principal",
          texto: "CONTINUAR →",
          onclick: () => pintarPregunta(paso),
        }),
      ),
    );
  }

  function pintarPregunta(paso) {
    const { pregunta, escenario } = paso;
    const indice = estado.indice;
    const ultima = indice === estado.preguntas.length - 1;
    const elegida = estado.respuestas.get(pregunta.id);
    const confirmacion = h("p", { clase: "confirmacion", "aria-live": "polite" });

    const botonesOpcion = ordenar(pregunta.opciones).map((opcion, i) => {
      const boton = h(
        "button",
        {
          type: "button",
          clase: "opcion" + (opcion.id === elegida ? " elegida" : ""),
          "aria-pressed": String(opcion.id === elegida),
          onclick: () => responder(paso, opcion.id, botonesOpcion, confirmacion),
        },
        h("span", { clase: "opcion-letra", "aria-hidden": "true" }, LETRAS[i] || "•"),
        h("span", { clase: "opcion-texto" }, opcion.texto),
        h("span", { clase: "opcion-check", "aria-hidden": "true" }, "✓"),
      );
      boton.dataset.opcionId = opcion.id;
      return boton;
    });
    if (elegida) confirmacion.textContent = "✓ Respuesta guardada";

    const anterior = h("button", {
      type: "button",
      clase: "boton boton-fantasma",
      texto: "← Anterior",
      disabled: indice === 0,
      onclick: () => irA(indice - 1),
    });
    const siguiente = ultima
      ? h("button", { type: "button", clase: "boton boton-principal boton-finalizar", texto: "FINALIZAR", onclick: pedirFinalizar })
      : h("button", { type: "button", clase: "boton boton-principal", texto: "Siguiente →", onclick: () => irA(indice + 1, { portada: true }) });

    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "pregunta aparece" },
        h("p", { clase: "kicker" }, `Capítulo ${paso.numeroEscenario} · ${escenario.titulo}`),
        h(
          "details",
          { clase: "detalles detalles-contexto" },
          h("summary", {}, "📖 Releer el contexto"),
          h("p", { clase: "texto-historia" }, escenario.contexto),
        ),
        h("h2", { clase: "enunciado" }, pregunta.enunciado),
        h("div", { clase: "opciones", role: "group", "aria-label": "Opciones de respuesta" }, botonesOpcion),
        confirmacion,
        h("div", { clase: "navegacion" }, anterior, siguiente),
      ),
    );
  }

  async function responder(paso, opcionId, botones, confirmacion) {
    if (estado.guardando || estado.finalizando) return;
    const previa = estado.respuestas.get(paso.pregunta.id);
    if (previa === opcionId) return;

    estado.guardando = true;
    marcar(botones, opcionId);
    confirmacion.textContent = "Guardando…";
    confirmacion.classList.remove("ok");
    try {
      const progreso = await Api.put(
        `/participations/${encodeURIComponent(estado.participacion.id)}/answers/${encodeURIComponent(paso.pregunta.id)}`,
        { opcion_id: opcionId },
      );
      estado.respuestas.set(paso.pregunta.id, opcionId);
      sincronizarProgreso(progreso);
      confirmacion.textContent = "✓ Respuesta guardada";
      confirmacion.classList.remove("ok");
      void confirmacion.offsetWidth; // reinicia la animación
      confirmacion.classList.add("ok");
    } catch (error) {
      marcar(botones, previa);
      confirmacion.textContent = previa ? "✓ Respuesta guardada" : "";
      Aviso.deError(error);
      if (error instanceof ErrorApi && [409, 422].includes(error.estado)) comprobarTiempo();
    } finally {
      estado.guardando = false;
    }
  }

  function marcar(botones, opcionId) {
    botones.forEach((boton) => {
      const activa = boton.dataset.opcionId === opcionId;
      boton.classList.toggle("elegida", activa);
      boton.setAttribute("aria-pressed", String(activa));
    });
  }

  function sincronizarProgreso(progreso) {
    const total = progreso.total || estado.preguntas.length;
    const porcentaje = total ? Math.round((progreso.respondidas / total) * 100) : 0;
    $("#progreso-relleno").style.width = `${porcentaje}%`;
    $("#progreso").setAttribute("aria-valuenow", String(porcentaje));
    anclarReloj(progreso.segundos_restantes);
  }

  /* ---------- reloj (siempre anclado al servidor) ---------- */

  function anclarReloj(segundos) {
    estado.reloj.finMs = performance.now() + segundos * 1000;
    estado.reloj.ultimoSync = performance.now();
    pintarReloj();
  }

  function arrancarReloj() {
    clearInterval(estado.reloj.intervalo);
    estado.reloj.intervalo = setInterval(tic, 250);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) resincronizar();
    });
  }

  function segundosRestantes() {
    return Math.max(0, Math.ceil((estado.reloj.finMs - performance.now()) / 1000));
  }

  function formatoReloj(total) {
    const horas = Math.floor(total / 3600);
    const minutos = Math.floor((total % 3600) / 60);
    const segundos = total % 60;
    const mm = String(minutos).padStart(2, "0");
    const ss = String(segundos).padStart(2, "0");
    return horas ? `${horas}:${mm}:${ss}` : `${mm}:${ss}`;
  }

  function pintarReloj() {
    const restante = segundosRestantes();
    $("#tiempo").textContent = formatoReloj(restante);
    const reloj = $("#temporizador");
    reloj.classList.toggle("alerta", restante <= UMBRAL_ALERTA_SEG);
    reloj.classList.toggle("critico", restante <= 60);
  }

  function tic() {
    if (estado.finalizando) return;
    pintarReloj();
    if (segundosRestantes() === 0) comprobarTiempo();
    else if (performance.now() - estado.reloj.ultimoSync > RESINCRONIZAR_CADA_MS) resincronizar();
  }

  async function resincronizar() {
    if (estado.finalizando || !estado.participacion) return;
    estado.reloj.ultimoSync = performance.now();
    try {
      const actual = await Api.get(`/participations/${encodeURIComponent(estado.participacion.id)}`);
      if (actual.estado !== "EN_PROGRESO") {
        irAResultado();
        return;
      }
      sincronizarProgreso(actual.progreso);
    } catch (_) {
      // Si falla, el reloj sigue con el último valor del servidor.
    }
  }

  // El servidor decide cuándo se acabó el tiempo; el cliente solo lo consulta.
  async function comprobarTiempo() {
    if (estado.finalizando) return;
    try {
      const actual = await Api.get(`/participations/${encodeURIComponent(estado.participacion.id)}`);
      if (actual.estado === "EN_PROGRESO" && actual.progreso.segundos_restantes > 0) {
        sincronizarProgreso(actual.progreso);
        return;
      }
    } catch (_) {
      if (segundosRestantes() > 0) return;
    }
    tiempoAgotado();
  }

  async function tiempoAgotado() {
    if (estado.finalizando) return;
    estado.finalizando = true;
    clearInterval(estado.reloj.intervalo);
    Dom.reemplazar(
      escena,
      h("section", { clase: "capitulo aparece centrado" },
        h("p", { clase: "emoji-grande", "aria-hidden": "true" }, "⏰"),
        h("h2", { clase: "titulo-capitulo" }, "¡Se acabó el tiempo!"),
        h("p", { clase: "texto-suave" }, "Estamos cerrando tu participación y calculando tu puntuación…"),
      ),
    );
    await cerrarParticipacion();
    irAResultado();
  }

  /* ---------- finalizar ---------- */

  async function cerrarParticipacion() {
    try {
      await Api.post(`/participations/${encodeURIComponent(estado.participacion.id)}/finish`);
    } catch (_) {
      // Si ya estaba cerrada por tiempo, el resultado sigue disponible.
    }
  }

  async function pedirFinalizar() {
    if (estado.guardando || estado.finalizando) return;
    const sinResponder = estado.preguntas.length - estado.respuestas.size;
    const confirmado = await Modal.confirmar({
      titulo: "¿Finalizar el caso?",
      mensaje: sinResponder
        ? `Te faltan ${sinResponder} ${sinResponder === 1 ? "pregunta" : "preguntas"} por responder. Después de finalizar no podrás cambiar tus respuestas.`
        : "Después de finalizar no podrás cambiar tus respuestas.",
      textoConfirmar: "Sí, finalizar",
      textoCancelar: "Seguir jugando",
      peligro: sinResponder > 0,
    });
    if (!confirmado) return;

    estado.finalizando = true;
    clearInterval(estado.reloj.intervalo);
    try {
      await Api.post(`/participations/${encodeURIComponent(estado.participacion.id)}/finish`);
    } catch (error) {
      // 409: ya estaba finalizada; en cualquier otro caso se reactiva el juego.
      if (!(error instanceof ErrorApi && error.estado === 409)) {
        estado.finalizando = false;
        estado.reloj.intervalo = setInterval(tic, 250);
        Aviso.deError(error);
        return;
      }
    }
    irAResultado();
  }

  function irAResultado() {
    estado.finalizando = true;
    clearInterval(estado.reloj.intervalo);
    window.location.href = `/app/resultado?participacion=${encodeURIComponent(estado.participacion.id)}`;
  }

  /* ---------- arranque ---------- */

  $("#boton-salir").addEventListener("click", () => Api.cerrarSesion());
  Campana.montar($("#campana"));
  iniciar();
})();
