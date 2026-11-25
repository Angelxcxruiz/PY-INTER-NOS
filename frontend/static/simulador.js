"use strict";

/*
 * Simulador del estudiante.
 * Regla RF-14: durante el juego solo se usan los datos de la vista de estudiante
 * (sin es_correcta ni justificación). La corrección aparece únicamente en /app/resultado.
 * El tiempo restante SIEMPRE viene del servidor (segundos_restantes); el cliente solo
 * lo cuenta hacia atrás entre una respuesta del servidor y la siguiente.
 *
 * Flujo (Fase 13): briefing → capítulos (uno por escenario). Al entrar a un capítulo:
 * tarjeta narrativa → puzzles pendientes (opcionales, no puntúan) → preguntas.
 *   - 4 preguntas o menos: flujo lineal.
 *   - de 5 a 8: mapa de capítulos que se desbloquean en orden.
 *   - 9 o más: mapa con progreso por capítulo.
 * RF-10: se puede volver a cualquier pregunta ya vista y cambiar la respuesta hasta finalizar;
 * ningún puzzle bloquea eso (se puede saltar o volver sin resolverlo) y los resueltos no se repiten.
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
  const MAX_PREGUNTAS_LINEAL = 4;
  const MAX_PREGUNTAS_MAPA = 8;

  const estado = {
    caso: null,
    capitulos: [], // { indice, escenario, puzzles, preguntaIdx: [índices en `preguntas`] }
    preguntas: [], // lista plana: { escenario, capitulo, numeroEscenario, primeraDelEscenario, pregunta }
    modo: "lineal", // "lineal" | "mapa" | "mapa-progreso"
    participacion: null,
    respuestas: new Map(), // pregunta_id -> opcion_id confirmada por el servidor
    local: { puzzles: {}, alcanzado: 0 }, // puzzles ya jugados y capítulo más lejano alcanzado
    puzle: null, // puzzle montado en pantalla (para detenerlo al cambiar de pantalla)
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
    return [...(lista || [])].sort((a, b) => a.orden - b.orden);
  }

  function armarCapitulos(caso) {
    estado.capitulos = ordenar(caso.escenarios).map((escenario, indice) => ({
      indice,
      escenario,
      puzzles: ordenar(escenario.puzzles),
      preguntaIdx: [],
    }));
    estado.preguntas = [];
    estado.capitulos.forEach((capitulo) => {
      ordenar(capitulo.escenario.preguntas).forEach((pregunta, i) => {
        capitulo.preguntaIdx.push(estado.preguntas.length);
        estado.preguntas.push({
          escenario: capitulo.escenario,
          capitulo: capitulo.indice,
          numeroEscenario: capitulo.indice + 1,
          primeraDelEscenario: i === 0,
          pregunta,
        });
      });
    });
    const total = estado.preguntas.length;
    if (estado.capitulos.length < 2 || total <= MAX_PREGUNTAS_LINEAL) estado.modo = "lineal";
    else if (total <= MAX_PREGUNTAS_MAPA) estado.modo = "mapa";
    else estado.modo = "mapa-progreso";
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
    armarCapitulos(estado.caso);

    const convocatoria = encodeURIComponent(claims.convocatoria_id);
    const [enCurso, resultadoPrevio] = await Promise.all([
      intentar(Api.get(`/participations/by-convocatoria/${convocatoria}`)),
      intentar(Api.get(`/convocatorias/${convocatoria}/result`)),
    ]);
    mostrarBriefing(enCurso, resultadoPrevio);
  }

  /* ---------- estado local de la interfaz (solo puzzles jugados y capítulo alcanzado) ---------- */

  function claveLocal() {
    return `inn_juego_${estado.participacion.id}`;
  }

  function cargarLocal() {
    try {
      const guardado = JSON.parse(sessionStorage.getItem(claveLocal()) || "{}");
      estado.local = { puzzles: guardado.puzzles || {}, alcanzado: guardado.alcanzado || 0 };
    } catch (_) {
      estado.local = { puzzles: {}, alcanzado: 0 };
    }
    // Lo respondido manda: no se bloquea un capítulo donde ya hay respuestas.
    estado.preguntas.forEach((paso) => {
      if (estado.respuestas.has(paso.pregunta.id)) {
        estado.local.alcanzado = Math.max(estado.local.alcanzado, paso.capitulo);
      }
    });
  }

  function guardarLocal() {
    try {
      sessionStorage.setItem(claveLocal(), JSON.stringify(estado.local));
    } catch (_) {
      // Sin almacenamiento: los puzzles podrían repetirse, nada más.
    }
  }

  function marcarAlcanzado(indiceCapitulo) {
    if (indiceCapitulo > estado.local.alcanzado) {
      estado.local.alcanzado = indiceCapitulo;
      guardarLocal();
    }
  }

  const respondidasDe = (capitulo) =>
    capitulo.preguntaIdx.filter((i) => estado.respuestas.has(estado.preguntas[i].pregunta.id)).length;

  const primeraSinResponder = (capitulo) =>
    capitulo.preguntaIdx.find((i) => !estado.respuestas.has(estado.preguntas[i].pregunta.id));

  const desbloqueado = (capitulo) => capitulo.indice <= estado.local.alcanzado;

  function limpiarPuzle() {
    if (estado.puzle) estado.puzle.destruir();
    estado.puzle = null;
  }

  /* ---------- fondo del escenario (composición del editor visual) ---------- */

  let fondoActual = null; // { escenarioId, destruir }

  function quitarFondo() {
    if (fondoActual) fondoActual.destruir();
    fondoActual = null;
    document.body.classList.remove("con-escena");
    document.body.style.removeProperty("--velo-escena");
  }

  /* Pone la composición del escenario detrás del contenido; sin composición, quita el fondo. */
  function fondoEscena(escenario) {
    const composicion = escenario && escenario.composicion;
    if (!composicion) {
      quitarFondo();
      return;
    }
    if (fondoActual && fondoActual.escenarioId === escenario.id) return;
    quitarFondo();
    const montado = Composicion.montarFondo(composicion);
    document.body.prepend(montado.el);
    document.body.classList.add("con-escena");
    fondoActual = { escenarioId: escenario.id, destruir: montado.destruir };
    // Panel oscuro y legible siempre; más opaco si el fondo es claro (o si hay imágenes, que no se miden).
    const claridad = Composicion.claridad(composicion);
    const velo = claridad === null ? 0.84 : claridad > 0.45 ? 0.92 : claridad > 0.3 ? 0.82 : 0.68;
    document.body.style.setProperty("--velo-escena", String(velo));
  }

  /* ---------- briefing ---------- */

  function mostrarBriefing(enCurso, resultadoPrevio) {
    quitarFondo();
    hud.classList.add("oculto");
    barraBriefing.classList.remove("oculto");
    const caso = estado.caso;
    const nombreEstudiante = (Api.usuario() || {}).nombre;
    const escenarios = caso.escenarios.length;
    const hayPuzzles = estado.capitulos.some((capitulo) => capitulo.puzzles.length > 0);

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
        hayPuzzles &&
          h(
            "p",
            { clase: "ayuda centrado info-puzzles" },
            "🧩 Antes de cada capítulo puede haber puzles para entrenar la mente. Son opcionales y no cuentan para tu nota.",
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
    cargarLocal();
    barraBriefing.classList.add("oculto");
    hud.classList.remove("oculto");
    document.body.classList.add("jugando");

    sincronizarProgreso(participacion.progreso);
    arrancarReloj();

    const sinResponder = estado.preguntas.findIndex((p) => !estado.respuestas.has(p.pregunta.id));
    const indice = sinResponder === -1 ? estado.preguntas.length - 1 : sinResponder;
    if (estado.respuestas.size === 0) {
      entrarCapitulo(0);
    } else if (estado.modo !== "lineal") {
      mostrarMapa();
    } else if (estado.preguntas[indice].primeraDelEscenario && sinResponder !== -1) {
      entrarCapitulo(estado.preguntas[indice].capitulo);
    } else {
      irA(indice);
    }
  }

  function contador(texto) {
    $("#hud-contador").textContent = texto;
    window.scrollTo({ top: 0 });
  }

  function irA(indice) {
    limpiarPuzle();
    estado.indice = indice;
    contador(`Pregunta ${indice + 1} de ${estado.preguntas.length}`);
    pintarPregunta(estado.preguntas[indice]);
  }

  /* Entrar a un capítulo: narrativa (si es la primera vez) → puzzles pendientes → preguntas. */
  function entrarCapitulo(indiceCapitulo) {
    const capitulo = estado.capitulos[indiceCapitulo];
    marcarAlcanzado(indiceCapitulo);
    const pendientes = capitulo.puzzles.filter((puzzle) => !estado.local.puzzles[puzzle.id]);

    const irAPreguntas = () => {
      const destino = primeraSinResponder(capitulo);
      irA(destino === undefined ? capitulo.preguntaIdx[0] : destino);
    };
    const jugar = (k) => {
      if (k >= pendientes.length) {
        irAPreguntas();
        return;
      }
      pintarPuzzle(capitulo, pendientes[k], k, pendientes.length, () => jugar(k + 1), () => volverDesde(capitulo));
    };

    if (respondidasDe(capitulo) === 0) pintarCapitulo(capitulo, () => jugar(0));
    else jugar(0);
  }

  /* Volver sin resolver: al mapa, o a la última pregunta del capítulo anterior. */
  function volverDesde(capitulo) {
    if (estado.modo !== "lineal") {
      mostrarMapa();
      return;
    }
    const anterior = estado.capitulos[capitulo.indice - 1];
    if (anterior) irA(anterior.preguntaIdx[anterior.preguntaIdx.length - 1]);
  }

  function pintarCapitulo(capitulo, continuar) {
    limpiarPuzle();
    fondoEscena(capitulo.escenario);
    contador(`Capítulo ${capitulo.indice + 1} de ${estado.capitulos.length}`);
    const hayAtras = estado.modo !== "lineal" || capitulo.indice > 0;
    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "capitulo aparece" },
        h("p", { clase: "kicker" }, `Capítulo ${capitulo.indice + 1}`),
        h("h2", { clase: "titulo-capitulo" }, capitulo.escenario.titulo),
        h("div", { clase: "tarjeta elevada tarjeta-historia" }, h("p", { clase: "texto-historia" }, capitulo.escenario.contexto)),
        capitulo.puzzles.length > 0 &&
          h("p", { clase: "ayuda centrado info-puzzles" }, `🧩 Antes de las preguntas: ${capitulo.puzzles.length === 1 ? "1 puzle opcional" : `${capitulo.puzzles.length} puzles opcionales`}.`),
        h("button", {
          type: "button",
          clase: "boton boton-grande boton-principal",
          texto: "CONTINUAR →",
          onclick: continuar,
        }),
        hayAtras &&
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: estado.modo !== "lineal" ? "🗺 Mapa de capítulos" : "← Volver a la pregunta anterior",
            onclick: () => volverDesde(capitulo),
          }),
      ),
    );
  }

  function pintarPuzzle(capitulo, puzzle, k, total, continuar, volver) {
    limpiarPuzle();
    fondoEscena(capitulo.escenario);
    contador(total > 1 ? `🧩 Puzle ${k + 1} de ${total}` : "🧩 Puzle");
    const hayAtras = estado.modo !== "lineal" || capitulo.indice > 0;
    estado.puzle = Puzzles.montar(escena, puzzle, {
      verificar: (respuesta) =>
        Api.post(`/puzzles/${encodeURIComponent(puzzle.id)}/verificar`, { respuesta }),
      alTerminar: (resultado) => {
        estado.local.puzzles[puzzle.id] = resultado;
        guardarLocal();
        continuar();
      },
      alVolver: hayAtras ? volver : null,
      textoVolver: estado.modo !== "lineal" ? "🗺 Volver al mapa" : "← Volver a la pregunta anterior",
    });
  }

  /* ---------- mapa de capítulos ---------- */

  function mostrarMapa() {
    limpiarPuzle();
    quitarFondo();
    contador("🗺 Mapa de capítulos");
    const conProgreso = estado.modo === "mapa-progreso";
    const siguiente = estado.capitulos.find(
      (capitulo) => desbloqueado(capitulo) && respondidasDe(capitulo) < capitulo.preguntaIdx.length,
    );

    const tarjetas = estado.capitulos.map((capitulo) => {
      const total = capitulo.preguntaIdx.length;
      const respondidas = respondidasDe(capitulo);
      const abierto = desbloqueado(capitulo);
      const completo = respondidas === total;
      const etiqueta = !abierto
        ? ["🔒 Bloqueado", "neutro"]
        : completo
          ? ["✓ Completo", "ok"]
          : respondidas > 0
            ? ["En curso", "aviso"]
            : capitulo === siguiente
              ? ["Siguiente", "aviso"]
              : ["Disponible", "neutro"];
      return h(
        "article",
        { clase: `tarjeta capitulo-mapa ${abierto ? "" : "bloqueado"} ${capitulo === siguiente ? "siguiente" : ""}` },
        h(
          "div",
          { clase: "tarjeta-fila" },
          h("h3", { clase: "titulo-tarjeta" }, `Capítulo ${capitulo.indice + 1} · ${capitulo.escenario.titulo}`),
          h("span", { clase: `chip chip-${etiqueta[1]}` }, etiqueta[0]),
        ),
        h(
          "p",
          { clase: "texto-suave" },
          `${respondidas} de ${total} ${total === 1 ? "pregunta respondida" : "preguntas respondidas"}` +
            (capitulo.puzzles.length ? ` · 🧩 ${capitulo.puzzles.length}` : ""),
        ),
        conProgreso &&
          h(
            "div",
            { clase: "progreso", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round((respondidas / total) * 100)) },
            h("div", { clase: "progreso-relleno", style: `width:${Math.round((respondidas / total) * 100)}%` }),
          ),
        h("button", {
          type: "button",
          clase: `boton boton-bloque ${capitulo === siguiente ? "boton-principal" : "boton-fantasma"}`,
          texto: !abierto ? "Completa el capítulo anterior" : completo ? "Repasar" : respondidas > 0 ? "Continuar" : "Entrar",
          disabled: !abierto,
          onclick: () => entrarCapitulo(capitulo.indice),
        }),
      );
    });

    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "mapa aparece" },
        h("p", { clase: "kicker" }, "Tu recorrido"),
        h("h2", { clase: "titulo-capitulo" }, estado.caso.nombre),
        h("p", { clase: "ayuda" }, "Los capítulos se abren en orden. Puedes volver a cualquiera para cambiar tus respuestas hasta finalizar."),
        h("div", { clase: "mapa-lista" }, tarjetas),
        h("button", {
          type: "button",
          clase: "boton boton-fantasma boton-bloque",
          texto: "FINALIZAR CASO",
          onclick: pedirFinalizar,
        }),
      ),
    );
  }

  /* ---------- preguntas ---------- */

  function avanzar(indice) {
    const actual = estado.preguntas[indice];
    const siguiente = estado.preguntas[indice + 1];
    if (siguiente.capitulo === actual.capitulo) {
      irA(indice + 1);
      return;
    }
    marcarAlcanzado(siguiente.capitulo);
    if (estado.modo === "lineal") entrarCapitulo(siguiente.capitulo);
    else mostrarMapa();
  }

  function pintarPregunta(paso) {
    const { pregunta, escenario } = paso;
    fondoEscena(escenario);
    const indice = estado.indice;
    const ultima = indice === estado.preguntas.length - 1;
    const enMapa = estado.modo !== "lineal";
    const finDeCapitulo = !ultima && estado.preguntas[indice + 1].capitulo !== paso.capitulo;
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
    const alMapa = h("button", {
      type: "button",
      clase: "boton boton-fantasma",
      texto: "🗺 Mapa",
      onclick: mostrarMapa,
    });
    const siguiente = ultima
      ? h("button", { type: "button", clase: "boton boton-principal boton-finalizar", texto: "FINALIZAR", onclick: pedirFinalizar })
      : h("button", {
          type: "button",
          clase: "boton boton-principal",
          texto: enMapa && finDeCapitulo ? "Terminar capítulo →" : "Siguiente →",
          onclick: () => avanzar(indice),
        });

    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "pregunta aparece" },
        h(
          "div",
          { clase: "fila-capitulo" },
          h("p", { clase: "kicker" }, `Capítulo ${paso.numeroEscenario} · ${escenario.titulo}`),
          enMapa &&
            h("button", {
              type: "button",
              clase: "boton boton-fantasma boton-chico",
              texto: "🗺 Mapa",
              onclick: mostrarMapa,
            }),
        ),
        h(
          "details",
          { clase: "detalles detalles-contexto" },
          h("summary", {}, "📖 Releer el contexto"),
          h("p", { clase: "texto-historia" }, escenario.contexto),
        ),
        h("h2", { clase: "enunciado" }, pregunta.enunciado),
        h("div", { clase: "opciones", role: "group", "aria-label": "Opciones de respuesta" }, botonesOpcion),
        confirmacion,
        h("div", { clase: "navegacion" }, enMapa && paso.primeraDelEscenario ? alMapa : anterior, siguiente),
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
    limpiarPuzle();
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
    limpiarPuzle();
    clearInterval(estado.reloj.intervalo);
    window.location.href = `/app/resultado?participacion=${encodeURIComponent(estado.participacion.id)}`;
  }

  /* ---------- arranque ---------- */

  $("#boton-salir").addEventListener("click", () => Api.cerrarSesion());
  Campana.montar($("#campana"));
  iniciar();
})();
