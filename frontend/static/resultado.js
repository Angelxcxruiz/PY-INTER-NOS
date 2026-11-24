"use strict";

/*
 * Pantalla de puntuación final. Aquí SÍ se muestra la corrección y las justificaciones
 * (RF-14 solo prohíbe mostrarlas mientras el estudiante está jugando).
 */

(function () {
  const claims = Api.exigirRol("ESTUDIANTE");
  if (!claims) return;
  if (!claims.convocatoria_id) {
    window.location.replace("/app/simulador");
    return;
  }

  const h = Dom.h.bind(Dom);
  const $ = Dom.$;
  const escena = $("#escena");

  function textosDelCaso(caso) {
    const preguntas = new Map();
    caso.escenarios.forEach((escenario) => {
      escenario.preguntas.forEach((pregunta) => {
        preguntas.set(pregunta.id, {
          opciones: new Map(pregunta.opciones.map((o) => [o.id, o.texto])),
        });
      });
    });
    return preguntas;
  }

  function animarNota(elemento, notaTexto) {
    const destino = parseFloat(notaTexto);
    const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (sinMovimiento || Number.isNaN(destino)) {
      elemento.textContent = notaTexto;
      return;
    }
    const duracion = 1600;
    const inicio = performance.now();
    const paso = (ahora) => {
      const t = Math.min(1, (ahora - inicio) / duracion);
      const suavizado = 1 - Math.pow(1 - t, 3);
      elemento.textContent = (destino * suavizado).toFixed(2);
      if (t < 1) requestAnimationFrame(paso);
      else elemento.textContent = notaTexto; // valor exacto que entregó el servidor
    };
    requestAnimationFrame(paso);
  }

  function tarjetaPregunta(detalle, indice, textos) {
    const info = textos.get(detalle.pregunta_id);
    const textoOpcion = (id) => (info && info.opciones.get(id)) || "—";
    const sinResponder = !detalle.opcion_elegida_id;
    const estado = sinResponder ? "sin" : detalle.acertada ? "ok" : "mal";
    const etiqueta = { ok: "✓ Acierto", mal: "✗ Error", sin: "— Sin responder" }[estado];

    return h(
      "article",
      { clase: `tarjeta resultado-pregunta resultado-${estado}` },
      h(
        "div",
        { clase: "tarjeta-fila" },
        h("span", { clase: "kicker" }, `Pregunta ${indice + 1}`),
        h("span", { clase: `chip chip-${estado === "ok" ? "ok" : estado === "mal" ? "peligro" : "neutro"}` }, etiqueta),
      ),
      h("h3", { clase: "enunciado enunciado-chico" }, detalle.enunciado),
      !sinResponder &&
        h("p", { clase: "linea-respuesta" }, h("strong", {}, "Tu respuesta: "), textoOpcion(detalle.opcion_elegida_id)),
      estado !== "ok" &&
        h("p", { clase: "linea-respuesta correcta" }, h("strong", {}, "Respuesta correcta: "), textoOpcion(detalle.opcion_correcta_id)),
      h("div", { clase: "justificacion" }, h("strong", {}, "💡 Por qué"), h("p", {}, detalle.justificacion)),
    );
  }

  async function cargarResultado() {
    const participacion = new URLSearchParams(window.location.search).get("participacion");
    const ruta = participacion
      ? `/participations/${encodeURIComponent(participacion)}/result`
      : `/convocatorias/${encodeURIComponent(claims.convocatoria_id)}/result`;

    let resultado;
    try {
      resultado = await Api.get(ruta);
    } catch (error) {
      Aviso.deError(error);
      Dom.reemplazar(
        escena,
        h(
          "div",
          { clase: "tarjeta centrado" },
          h("p", {}, Api.mensajeDe(error)),
          h("a", { clase: "boton boton-principal", href: "/app/simulador" }, "Volver al simulador"),
        ),
      );
      return;
    }

    // Los textos de las opciones solo están en la vista de estudiante del caso.
    let textos = new Map();
    if (claims.caso_id) {
      try {
        textos = textosDelCaso(await Api.get(`/cases/${encodeURIComponent(claims.caso_id)}/vista-estudiante`));
      } catch (_) {
        Aviso.info("No se pudieron cargar los textos de las opciones.");
      }
    }
    pintar(resultado, textos);
  }

  function pintar(resultado, textos) {
    const aprobado = parseFloat(resultado.nota_final) >= parseFloat(resultado.nota_aprobatoria);
    const cifra = h("span", { clase: "nota-cifra" }, "0.00");
    const veredicto = h(
      "p",
      { clase: `veredicto ${aprobado ? "veredicto-ok" : "veredicto-mal"}` },
      aprobado ? "¡Caso superado! 🎉" : "Aún no alcanzas la nota aprobatoria",
    );

    Dom.reemplazar(
      escena,
      h(
        "section",
        { clase: "puntuacion aparece" },
        h("p", { clase: "kicker" }, "Puntuación final"),
        h("div", { clase: `nota ${aprobado ? "nota-ok" : "nota-mal"}` }, cifra),
        veredicto,
        h("p", { clase: "texto-suave" }, `Nota aprobatoria: ${resultado.nota_aprobatoria}`),
        resultado.es_ausencia &&
          h("p", { clase: "banner banner-aviso" }, "No registraste participación en esta sesión."),
        resultado.es_parcial &&
          h("p", { clase: "banner banner-aviso" }, "Resultado parcial: la participación se cerró antes de responder todas las preguntas."),
        resultado.retroalimentacion &&
          h(
            "div",
            { clase: "tarjeta retroalimentacion-docente" },
            h("strong", {}, "💬 Retroalimentación de tu docente"),
            h("p", {}, resultado.retroalimentacion),
          ),
        h(
          "ul",
          { clase: "datos-briefing datos-resultado" },
          h("li", { clase: "dato-ok" }, h("strong", {}, String(resultado.aciertos)), h("span", {}, "aciertos")),
          h("li", { clase: "dato-mal" }, h("strong", {}, String(resultado.errores)), h("span", {}, "errores")),
          h("li", {}, h("strong", {}, String(resultado.total_preguntas)), h("span", {}, "preguntas")),
        ),
        resultado.preguntas.length > 0 &&
          h(
            "div",
            { clase: "revision" },
            h("h2", { clase: "titulo-seccion" }, "Revisión por pregunta"),
            resultado.preguntas.map((detalle, i) => tarjetaPregunta(detalle, i, textos)),
          ),
      ),
    );
    animarNota(cifra, resultado.nota_final);
  }

  $("#boton-salir").addEventListener("click", () => Api.cerrarSesion());
  Campana.montar($("#campana"));
  cargarResultado();
})();
