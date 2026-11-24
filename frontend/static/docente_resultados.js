"use strict";

/*
 * Resultados de una sesión para el docente: seguimiento en vivo, estadísticas, detalle por
 * estudiante, retroalimentación, repetición autorizada y descarga de reportes CSV.
 */

const PanelResultados = (() => {
  const h = Dom.h.bind(Dom);
  const reemplazar = Dom.reemplazar;

  const ESTADOS = {
    NO_INICIO: ["Aún no inicia", "neutro"],
    EN_PROGRESO: ["Jugando ahora", "aviso"],
    FINALIZO: ["Finalizó", "ok"],
    EXPIRA: ["Se acabó el tiempo", "aviso"],
    CERRADA_POR_SESION: ["Cerrada con la sesión", "aviso"],
    AUSENTE: ["Ausente", "peligro"],
  };
  const INTERVALO_MS = 15000;

  const numero = (valor) => (valor === null || valor === undefined ? null : Number(valor));
  const decimales = (valor, cifras = 2) => (numero(valor) === null ? "—" : numero(valor).toFixed(cifras));
  const porcentaje = (valor) => (numero(valor) === null ? "—" : `${numero(valor).toFixed(0)} %`);

  function mensajeDeError(error) {
    return error instanceof ErrorApi ? Api.mensajeDe(error) : error.message;
  }

  async function descargar(ruta, nombre) {
    const respuesta = await fetch(BASE_API + ruta, {
      headers: { Authorization: `Bearer ${Api.token()}` },
    });
    if (!respuesta.ok) throw new Error("No se pudo descargar el reporte.");
    const url = URL.createObjectURL(await respuesta.blob());
    const enlace = h("a", { href: url, download: nombre });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function barra(etiqueta, valor, maximo, detalle) {
    const ancho = maximo > 0 ? Math.round((valor / maximo) * 100) : 0;
    return h(
      "div",
      { clase: "barra-fila" },
      h("span", { clase: "barra-etiqueta" }, etiqueta),
      h("div", { clase: "barra-pista" }, h("div", { clase: "barra-relleno", style: `width:${ancho}%` })),
      h("span", { clase: "barra-valor" }, detalle),
    );
  }

  function tarjetaDato(titulo, valor) {
    return h("div", { clase: "dato" }, h("strong", { clase: "dato-valor" }, valor), h("span", { clase: "dato-titulo" }, titulo));
  }

  /*
   * contenedor: nodo donde se pinta. contexto: { sesion, caso, aprobatoria }.
   * Devuelve { destruir } para detener la actualización automática.
   */
  function montar(contenedor, contexto) {
    const { sesion } = contexto;
    let temporizador = null;
    let destruido = false;
    let primeraVez = true;

    async function cargar() {
      let datos;
      try {
        datos = await Api.get(`/sessions/${sesion.id}/seguimiento`);
      } catch (error) {
        if (primeraVez) {
          reemplazar(contenedor, h("p", { clase: "texto-suave" }, "No se pudieron cargar los resultados."));
        }
        Aviso.deError(error);
        return;
      }
      if (destruido) return;
      primeraVez = false;
      pintar(datos);
    }

    function pintar(datos) {
      const { convocados, estadisticas } = datos;
      const enVivo = sesion.estado === "EN_CURSO";
      const resumen = h(
        "div",
        { clase: "rejilla-datos" },
        tarjetaDato("Convocados", String(estadisticas.total_convocados)),
        tarjetaDato("Participación", porcentaje(estadisticas.tasa_participacion)),
        tarjetaDato("Finalización", porcentaje(estadisticas.tasa_finalizacion)),
        tarjetaDato("Promedio", decimales(estadisticas.promedio)),
        tarjetaDato("Mediana", decimales(estadisticas.mediana)),
        tarjetaDato("Mín. – máx.", `${decimales(estadisticas.nota_minima, 1)} – ${decimales(estadisticas.nota_maxima, 1)}`),
      );

      const distribucion = estadisticas.distribucion_notas || [];
      const maximoDistribucion = Math.max(0, ...distribucion.map((rango) => rango.cantidad));
      const bloqueDistribucion =
        distribucion.length && maximoDistribucion > 0
          ? h(
              "section",
              { clase: "tarjeta espaciado" },
              h("h4", { clase: "titulo-tarjeta" }, "Distribución de notas"),
              distribucion.map((rango) =>
                barra(`${decimales(rango.desde, 1)}–${decimales(rango.hasta, 1)}`, rango.cantidad, maximoDistribucion, String(rango.cantidad)),
              ),
            )
          : null;

      const preguntas = estadisticas.preguntas || [];
      const conDatos = preguntas.filter((pregunta) => pregunta.respondieron > 0);
      const bloquePreguntas = conDatos.length
        ? h(
            "section",
            { clase: "tarjeta espaciado" },
            h("h4", { clase: "titulo-tarjeta" }, "Acierto por pregunta"),
            h("p", { clase: "ayuda" }, "Las más bajas son las que más les costaron a tus estudiantes."),
            preguntas.map((pregunta, i) =>
              barra(
                `P${i + 1}`,
                numero(pregunta.tasa_acierto) || 0,
                100,
                pregunta.respondieron ? `${porcentaje(pregunta.tasa_acierto)} (${pregunta.aciertos}/${pregunta.respondieron})` : "—",
              ),
            ),
          )
        : null;

      const criterios = estadisticas.criterios || [];
      const bloqueCriterios = criterios.length
        ? h(
            "section",
            { clase: "tarjeta espaciado" },
            h("h4", { clase: "titulo-tarjeta" }, "Acierto por criterio"),
            criterios.map((criterio) => barra(criterio.nombre, numero(criterio.tasa_acierto) || 0, 100, porcentaje(criterio.tasa_acierto))),
          )
        : null;

      reemplazar(
        contenedor,
        h(
          "div",
          { clase: "acciones acciones-compactas" },
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "↻ Actualizar",
            onclick: cargar,
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "⬇ Notas (CSV)",
            onclick: () =>
              descargar(`/sessions/${sesion.id}/reports/participation.csv`, "participacion.csv").catch((error) =>
                Aviso.error(mensajeDeError(error)),
              ),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "⬇ Respuestas (CSV)",
            onclick: () =>
              descargar(`/sessions/${sesion.id}/reports/answers.csv`, "respuestas.csv").catch((error) =>
                Aviso.error(mensajeDeError(error)),
              ),
          }),
        ),
        enVivo && h("p", { clase: "ayuda" }, "🟢 Sesión en curso: esta vista se actualiza sola cada 15 segundos."),
        resumen,
        bloqueDistribucion,
        bloquePreguntas,
        bloqueCriterios,
        h("h3", { clase: "titulo-seccion espaciado" }, `Estudiantes (${convocados.length})`),
        convocados.length
          ? h("div", { clase: "lista-convocados" }, convocados.map(tarjetaEstudiante))
          : h("div", { clase: "vacio tarjeta" }, h("p", { clase: "texto-suave" }, "Aún no hay estudiantes convocados.")),
      );
    }

    function tarjetaEstudiante(registro) {
      const [textoEstado, tipoEstado] = ESTADOS[registro.estado] || [registro.estado, "neutro"];
      const nota = numero(registro.nota_final);
      const aprobo = nota !== null && contexto.aprobatoria !== null ? nota >= contexto.aprobatoria : null;
      const verDetalle = registro.estado !== "NO_INICIO" && !(registro.estado === "EN_PROGRESO");
      return h(
        "article",
        { clase: "tarjeta fila-resultado" },
        h(
          "div",
          { clase: "fila-convocado-info" },
          h("strong", {}, registro.nombre || "Estudiante"),
          h("small", { clase: "texto-suave" }, registro.correo),
          h("span", { clase: `chip chip-${tipoEstado}` }, textoEstado),
          registro.parcial && h("span", { clase: "chip chip-aviso" }, "Parcial"),
        ),
        h(
          "div",
          { clase: "resultado-cifras" },
          h("span", { clase: "texto-suave" }, `${registro.respondidas}/${registro.total_preguntas} respondidas`),
          nota !== null &&
            h(
              "strong",
              { clase: `nota-fila ${aprobo === null ? "" : aprobo ? "nota-fila-ok" : "nota-fila-mal"}` },
              decimales(nota),
            ),
          registro.retroalimentacion && h("span", { clase: "chip chip-neutro" }, "💬 con retroalimentación"),
        ),
        verDetalle &&
          h("button", {
            type: "button",
            clase: "boton boton-info boton-chico",
            texto: "Ver detalle y retroalimentar",
            onclick: () => abrirDetalle(contexto, registro, cargar),
          }),
      );
    }

    reemplazar(contenedor, h("p", { clase: "texto-suave" }, h("span", { clase: "icono-carga" }), " Cargando resultados…"));
    cargar();
    if (sesion.estado === "EN_CURSO") {
      temporizador = setInterval(() => {
        if (!document.body.contains(contenedor)) return destruir();
        if (!contenedor.classList.contains("oculto") && !document.querySelector(".modal-fondo")) cargar();
      }, INTERVALO_MS);
    }

    function destruir() {
      destruido = true;
      clearInterval(temporizador);
    }
    return { destruir };
  }

  /* ---------- detalle por estudiante ---------- */

  function indiceOpciones(caso) {
    const mapa = {};
    if (!caso) return mapa;
    caso.escenarios.forEach((escenario) =>
      escenario.preguntas.forEach((pregunta) =>
        pregunta.opciones.forEach((opcion) => {
          mapa[opcion.id] = opcion.texto;
        }),
      ),
    );
    return mapa;
  }

  async function abrirDetalle(contexto, registro, alActualizar) {
    const { sesion } = contexto;
    const cuerpo = h("div", {}, h("p", { clase: "texto-suave" }, "Cargando…"));
    const hoja = Modal.hoja(registro.nombre || "Estudiante", cuerpo);

    let intentos = [];
    let resultado = null;
    let intentoFinal = null;
    try {
      intentos = await Api.get(`/participations/convocatorias/${registro.convocatoria_id}/intentos`);
      intentoFinal = [...intentos].filter((intento) => intento.finalizada_en).sort((a, b) => a.numero_intento - b.numero_intento).pop() || null;
      resultado = await Api.get(`/convocatorias/${registro.convocatoria_id}/result`);
    } catch (error) {
      if (!(error instanceof ErrorApi) || error.estado !== 404) {
        hoja.cerrar();
        Aviso.deError(error);
        return;
      }
    }

    const textos = indiceOpciones(contexto.caso);
    const retro = h("textarea", { rows: "4", maxlength: "4000", placeholder: "Escribe aquí tu retroalimentación para el estudiante…" });
    retro.value = registro.retroalimentacion || "";
    const botonRetro = h("button", { type: "button", clase: "boton boton-principal boton-bloque" }, "Guardar retroalimentación");
    botonRetro.addEventListener("click", async () => {
      const texto = retro.value.trim();
      if (!texto) {
        Aviso.error("Escribe la retroalimentación antes de guardar.");
        return;
      }
      botonRetro.disabled = true;
      try {
        const ruta = intentoFinal
          ? `/participations/${intentoFinal.id}/retroalimentacion`
          : `/convocatorias/${registro.convocatoria_id}/retroalimentacion`;
        await Api.post(ruta, { texto });
        registro.retroalimentacion = texto;
        Aviso.exito("Retroalimentación guardada. El estudiante la verá en su resultado.");
        alActualizar();
      } catch (error) {
        Aviso.deError(error);
      }
      botonRetro.disabled = false;
    });

    const motivo = h("input", { type: "text", maxlength: "500", placeholder: "Motivo (opcional), p. ej. se cayó la conexión" });
    const botonRepetir = h("button", { type: "button", clase: "boton boton-fantasma boton-bloque" }, "🔁 Autorizar un nuevo intento");
    botonRepetir.addEventListener("click", async () => {
      const confirmado = await Modal.confirmar({
        titulo: "¿Autorizar otro intento?",
        mensaje: `${registro.nombre || "El estudiante"} podrá volver a jugar el caso mientras la sesión siga en curso.`,
        textoConfirmar: "Autorizar",
      });
      if (!confirmado) return;
      botonRepetir.disabled = true;
      try {
        await Api.post(`/participations/convocatorias/${registro.convocatoria_id}/autorizar-repeticion`, {
          motivo: motivo.value.trim() || null,
        });
        Aviso.exito("Nuevo intento autorizado. El estudiante puede entrar de nuevo con su código.");
      } catch (error) {
        Aviso.deError(error);
      }
      botonRepetir.disabled = false;
    });

    const preguntas = resultado && resultado.preguntas ? resultado.preguntas : [];
    reemplazar(
      cuerpo,
      h("p", { clase: "texto-suave" }, registro.correo),
      resultado
        ? h(
            "div",
            { clase: "rejilla-datos" },
            tarjetaDato("Nota", decimales(resultado.nota_final)),
            tarjetaDato("Aciertos", `${resultado.aciertos}/${resultado.total_preguntas}`),
            tarjetaDato("Aprueba con", decimales(resultado.nota_aprobatoria)),
          )
        : h("p", { clase: "texto-suave" }, "Todavía no hay un resultado calculado."),
      resultado && resultado.es_ausencia && h("p", { clase: "advertencia" }, "Este estudiante no se presentó a la sesión."),
      preguntas.length ? h("h4", { clase: "titulo-tarjeta espaciado" }, "Respuestas") : null,
      preguntas.map((pregunta, i) =>
        h(
          "div",
          { clase: `detalle-pregunta ${pregunta.acertada ? "acierto" : "fallo"}` },
          h("strong", {}, `${pregunta.acertada ? "✔" : "✘"} ${i + 1}. ${pregunta.enunciado}`),
          h("small", { clase: "texto-suave" }, `Eligió: ${pregunta.opcion_elegida_id ? textos[pregunta.opcion_elegida_id] || "—" : "(sin responder)"}`),
          !pregunta.acertada && h("small", { clase: "texto-suave" }, `Correcta: ${textos[pregunta.opcion_correcta_id] || "—"}`),
          h("small", { clase: "texto-suave" }, `💡 ${pregunta.justificacion}`),
        ),
      ),
      intentos.length > 1
        ? h(
            "p",
            { clase: "ayuda" },
            `Intentos: ${intentos.map((intento) => `#${intento.numero_intento} ${intento.estado.toLowerCase()}`).join(" · ")}`,
          )
        : null,
      h("h4", { clase: "titulo-tarjeta espaciado" }, "Retroalimentación del docente"),
      h("label", { clase: "campo" }, retro),
      botonRetro,
      sesion.estado === "EN_CURSO"
        ? h("div", { clase: "espaciado" }, h("h4", { clase: "titulo-tarjeta" }, "Repetición"), h("label", { clase: "campo" }, motivo), botonRepetir)
        : null,
    );
  }

  return { montar };
})();
