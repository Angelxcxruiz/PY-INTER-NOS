"use strict";

/*
 * Editor de casos del docente: crear el caso, sus escenarios, preguntas y opciones, armar la
 * rúbrica, revisar la lista de verificación y publicarlo. Habla solo con la API de /cases;
 * las reglas de negocio (qué es publicable, que un caso publicado es inmutable) viven en el servidor.
 */

const EditorCasos = (() => {
  const h = Dom.h.bind(Dom);
  const reemplazar = Dom.reemplazar;

  const ESTADOS = {
    BORRADOR: ["Borrador", "aviso"],
    PUBLICADO: ["Publicado", "ok"],
    ARCHIVADO: ["Archivado", "neutro"],
  };
  const LETRAS = ["A", "B", "C", "D", "E", "F"];

  const chip = (texto, tipo) => h("span", { clase: `chip chip-${tipo}` }, texto);

  function mensajeDeError(error) {
    return error instanceof ErrorApi ? Api.mensajeDe(error) : error.message;
  }

  function guardado() {
    Aviso.mostrar("exito", "Guardado", 1500);
  }

  function campoTexto(valor, atributos = {}) {
    const control = h("input", { type: "text", ...atributos });
    control.value = valor ?? "";
    return control;
  }

  function campoArea(valor, filas, atributos = {}) {
    const control = h("textarea", { rows: String(filas), ...atributos });
    control.value = valor ?? "";
    return control;
  }

  /* ---------- formulario genérico dentro de una hoja ---------- */

  function formularioHoja({ titulo, intro, campos, textoEnviar, alEnviar }) {
    const controles = campos.map((campo) => {
      let control;
      if (campo.tipo === "textarea") {
        control = campoArea(campo.valor, campo.filas || 3, { placeholder: campo.ejemplo || "" });
      } else if (campo.tipo === "checkbox") {
        control = h("input", { type: "checkbox" });
        control.checked = Boolean(campo.valor);
      } else if (campo.tipo === "select") {
        control = h(
          "select",
          {},
          campo.opciones.map(([valor, texto]) => h("option", { value: valor }, texto)),
        );
        control.value = campo.valor ?? campo.opciones[0][0];
      } else {
        control = campoTexto(campo.valor, {
          type: campo.tipo || "text",
          placeholder: campo.ejemplo || "",
          min: campo.min,
          inputmode: campo.tipo === "number" ? "numeric" : undefined,
        });
      }
      return { campo, control };
    });

    const boton = h("button", { type: "submit", clase: "boton boton-principal boton-bloque" }, textoEnviar);
    const formulario = h(
      "form",
      { clase: "formulario", novalidate: true },
      intro && h("p", { clase: "ayuda" }, intro),
      controles.map(({ campo, control }) =>
        campo.tipo === "checkbox"
          ? h("label", { clase: "casilla" }, control, h("span", {}, campo.etiqueta))
          : h(
              "label",
              { clase: "campo" },
              h("span", {}, campo.etiqueta),
              control,
              campo.ayuda && h("small", { clase: "ayuda" }, campo.ayuda),
            ),
      ),
      boton,
    );
    const hoja = Modal.hoja(titulo, formulario);

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const valores = {};
      for (const { campo, control } of controles) {
        const valor = campo.tipo === "checkbox" ? control.checked : control.value.trim();
        if (campo.requerido && !valor) {
          Aviso.error(`Completa el campo «${campo.etiqueta}».`);
          control.focus();
          return;
        }
        valores[campo.id] = valor;
      }
      boton.disabled = true;
      try {
        await alEnviar(valores);
        hoja.cerrar();
      } catch (error) {
        Aviso.error(mensajeDeError(error));
        boton.disabled = false;
      }
    });
    if (controles[0] && controles[0].control.focus) controles[0].control.focus();
    return hoja;
  }

  /* ---------- crear un caso nuevo ---------- */

  function crearCaso(alCrear) {
    formularioHoja({
      titulo: "Nuevo caso",
      intro: "Empieza con los datos generales. Después agregarás los escenarios y las preguntas.",
      textoEnviar: "Crear y seguir editando",
      campos: [
        { id: "nombre", etiqueta: "Nombre del caso", requerido: true, ejemplo: "Conformidad en el aula" },
        {
          id: "tiempo",
          etiqueta: "Tiempo estimado (minutos)",
          tipo: "number",
          min: "1",
          valor: "30",
          requerido: true,
          ayuda: "Es el máximo que podrás dar a cada estudiante al agendar la sesión.",
        },
        {
          id: "contexto",
          etiqueta: "Contexto de la historia",
          tipo: "textarea",
          requerido: true,
          ejemplo: "¿Quiénes son los personajes y dónde ocurre todo?",
        },
        {
          id: "desarrollo",
          etiqueta: "Desarrollo situacional",
          tipo: "textarea",
          requerido: true,
          ejemplo: "¿Qué situación social deben analizar los estudiantes?",
        },
      ],
      alEnviar: async (valores) => {
        const tiempo = parseInt(valores.tiempo, 10);
        if (!tiempo || tiempo < 1) throw new Error("El tiempo estimado debe ser de al menos 1 minuto.");
        const caso = await Api.post("/cases", {
          nombre: valores.nombre,
          desarrollo_situacional: valores.desarrollo,
          contexto_historia: valores.contexto,
          tiempo_estimado_min: tiempo,
        });
        Aviso.exito("Caso creado. Ahora agrega sus escenarios.");
        alCrear(caso.id);
      },
    });
  }

  /* ---------- editor ---------- */

  async function abrir(contenedor, casoId, { alVolver, alAgendar, alCambiar }) {
    const abiertos = new Set();
    let primeraCarga = true;
    let caso = null;
    let validacion = { valido: false, errores: [] };
    let rubrica = null;
    let etiquetaPregunta = {};

    async function recargar() {
      const desplazamiento = window.scrollY;
      try {
        [caso, validacion] = await Promise.all([
          Api.get(`/cases/${casoId}`),
          Api.get(`/cases/${casoId}/validacion`),
        ]);
      } catch (error) {
        Aviso.deError(error);
        alVolver();
        return;
      }
      if (primeraCarga && caso.escenarios.length) abiertos.add(caso.escenarios[0].id);
      primeraCarga = false;
      etiquetaPregunta = {};
      caso.escenarios.forEach((escenario, i) =>
        escenario.preguntas.forEach((pregunta, j) => {
          etiquetaPregunta[pregunta.id] = `Escenario ${i + 1} · Pregunta ${j + 1}`;
        }),
      );
      rubrica = copiarRubrica(caso.rubrica);
      pintar();
      window.scrollTo(0, desplazamiento);
    }

    async function accion(tarea, mensaje) {
      try {
        await tarea();
        if (mensaje) Aviso.exito(mensaje);
      } catch (error) {
        Aviso.deError(error);
      }
      await recargar();
    }

    // Guardado al salir del campo: no repinta, para no quitarle el foco a quien escribe.
    async function autoguardar(tarea) {
      try {
        await tarea();
        guardado();
      } catch (error) {
        Aviso.deError(error);
        await recargar();
      }
    }

    function copiarRubrica(origen) {
      if (!origen) return null;
      return {
        nombre: origen.nombre,
        descripcion: origen.descripcion || "",
        escala_min: String(origen.escala_min),
        escala_max: String(origen.escala_max),
        nota_aprobatoria: String(origen.nota_aprobatoria),
        criterios: origen.criterios.map((criterio) => ({
          nombre: criterio.nombre,
          descripcion: criterio.descripcion || "",
          peso: String(criterio.peso),
          pregunta_ids: [...criterio.pregunta_ids],
        })),
      };
    }

    /* ----- lista de verificación y publicación ----- */

    function ubicacionLegible(ubicacion) {
      if (ubicacion.startsWith("pregunta:")) return etiquetaPregunta[ubicacion.slice(9)] || "Una pregunta";
      const fijas = { caso: "Caso", rubrica: "Rúbrica", tiempo_estimado_min: "Tiempo estimado" };
      if (fijas[ubicacion]) return fijas[ubicacion];
      return ubicacion
        .replace(/escenario\[(\d+)\]/, "Escenario $1")
        .replace(/\.pregunta\[(\d+)\]/, " · Pregunta $1")
        .replace(/\.opcion\[(\d+)\]/, " · Opción $1");
    }

    function panelPublicacion() {
      const errores = validacion.errores;
      const listo = errores.length === 0;
      return h(
        "section",
        { clase: `tarjeta espaciado ${listo ? "verificacion-ok" : "verificacion-pendiente"}` },
        h("h3", { clase: "titulo-tarjeta" }, listo ? "✔ Listo para publicar" : "Antes de publicar"),
        listo
          ? h(
              "p",
              { clase: "texto-suave" },
              "Al publicarlo, el caso queda fijo (no se podrá editar) y podrás asignarlo a tus estudiantes.",
            )
          : h(
              "ul",
              { clase: "lista-pendientes" },
              errores.map((error) =>
                h("li", {}, h("strong", {}, ubicacionLegible(error.ubicacion)), ` — ${error.mensaje}`),
              ),
            ),
        h(
          "div",
          { clase: "acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-principal",
            texto: "🚀 Publicar caso",
            disabled: !listo,
            onclick: publicar,
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma",
            texto: "🗑 Eliminar borrador",
            onclick: eliminarCaso,
          }),
        ),
      );
    }

    async function publicar() {
      const confirmado = await Modal.confirmar({
        titulo: "¿Publicar el caso?",
        mensaje: "Después de publicarlo no podrás editarlo; para cambiarlo crearás una nueva versión.",
        textoConfirmar: "Publicar",
      });
      if (!confirmado) return;
      await accion(() => Api.post(`/cases/${casoId}/publish`), "¡Caso publicado! Ya puedes asignarlo a tus estudiantes.");
      if (alCambiar) alCambiar();
    }

    async function eliminarCaso() {
      const confirmado = await Modal.confirmar({
        titulo: "¿Eliminar el borrador?",
        mensaje: "Se borrará el caso con todos sus escenarios y preguntas. No se puede deshacer.",
        textoConfirmar: "Eliminar",
        peligro: true,
      });
      if (!confirmado) return;
      try {
        await Api.eliminar(`/cases/${casoId}`);
        Aviso.exito("Borrador eliminado.");
        alVolver();
      } catch (error) {
        Aviso.deError(error);
      }
    }

    /* ----- datos generales ----- */

    function tarjetaDatos() {
      const nombre = campoTexto(caso.nombre, { maxlength: "200" });
      const tiempo = campoTexto(caso.tiempo_estimado_min, { type: "number", min: "1", inputmode: "numeric" });
      const contexto = campoArea(caso.contexto_historia, 4);
      const desarrollo = campoArea(caso.desarrollo_situacional, 4);
      const guardar = h("button", { type: "submit", clase: "boton boton-principal" }, "Guardar datos del caso");
      const formulario = h(
        "form",
        {
          clase: "formulario",
          novalidate: true,
          onsubmit: async (evento) => {
            evento.preventDefault();
            const minutos = parseInt(tiempo.value, 10);
            if (!nombre.value.trim() || !contexto.value.trim() || !desarrollo.value.trim() || !minutos) {
              Aviso.error("Completa nombre, tiempo, contexto y desarrollo.");
              return;
            }
            await accion(
              () =>
                Api.put(`/cases/${casoId}`, {
                  nombre: nombre.value.trim(),
                  tiempo_estimado_min: minutos,
                  contexto_historia: contexto.value.trim(),
                  desarrollo_situacional: desarrollo.value.trim(),
                }),
              "Datos guardados.",
            );
            if (alCambiar) alCambiar();
          },
        },
        h("label", { clase: "campo" }, h("span", {}, "Nombre del caso"), nombre),
        h("label", { clase: "campo" }, h("span", {}, "Tiempo estimado (minutos)"), tiempo),
        h("label", { clase: "campo" }, h("span", {}, "Contexto de la historia"), contexto),
        h("label", { clase: "campo" }, h("span", {}, "Desarrollo situacional"), desarrollo),
        guardar,
      );
      return h(
        "section",
        { clase: "tarjeta espaciado" },
        h("h3", { clase: "titulo-seccion" }, "1 · Datos del caso"),
        formulario,
      );
    }

    /* ----- escenarios, preguntas y opciones ----- */

    function modalEscenario() {
      formularioHoja({
        titulo: "Nuevo escenario",
        intro: "Un escenario es un capítulo de la historia; contendrá varias preguntas.",
        textoEnviar: "Agregar escenario",
        campos: [
          { id: "titulo", etiqueta: "Título", requerido: true, ejemplo: "Capítulo 1: la reunión" },
          {
            id: "contexto",
            etiqueta: "Qué ocurre en este escenario",
            tipo: "textarea",
            filas: 4,
            requerido: true,
          },
        ],
        alEnviar: async (valores) => {
          const escenario = await Api.post(`/cases/${casoId}/escenarios`, {
            titulo: valores.titulo,
            contexto: valores.contexto,
          });
          abiertos.add(escenario.id);
          await recargar();
          Aviso.exito("Escenario agregado. Ahora agrégale preguntas.");
        },
      });
    }

    function modalPregunta(escenario) {
      const campos = [
        { id: "enunciado", etiqueta: "Pregunta", tipo: "textarea", filas: 2, requerido: true },
      ];
      for (let i = 0; i < 4; i += 1) {
        campos.push({
          id: `texto${i}`,
          etiqueta: `Opción ${LETRAS[i]}${i < 2 ? "" : " (opcional)"}`,
          ejemplo: "Lo que el estudiante podrá elegir",
        });
        campos.push({
          id: `just${i}`,
          etiqueta: `¿Por qué la opción ${LETRAS[i]} es correcta o incorrecta?`,
          tipo: "textarea",
          filas: 2,
          ejemplo: "Lo verá el estudiante al terminar",
        });
      }
      campos.push({
        id: "correcta",
        etiqueta: "¿Cuál es la opción correcta?",
        tipo: "select",
        opciones: [0, 1, 2, 3].map((i) => [String(i), `Opción ${LETRAS[i]}`]),
        valor: "0",
      });
      formularioHoja({
        titulo: "Nueva pregunta",
        intro: "Escribe la pregunta con sus opciones. Debe haber una sola correcta y todas necesitan justificación.",
        textoEnviar: "Agregar pregunta",
        campos,
        alEnviar: async (valores) => {
          const opciones = [0, 1, 2, 3]
            .map((i) => ({ i, texto: valores[`texto${i}`], justificacion: valores[`just${i}`] }))
            .filter((opcion) => opcion.texto || opcion.justificacion);
          if (opciones.length < 2) throw new Error("Escribe al menos dos opciones.");
          if (opciones.some((opcion) => !opcion.texto || !opcion.justificacion)) {
            throw new Error("Cada opción necesita su texto y su justificación.");
          }
          const correcta = parseInt(valores.correcta, 10);
          if (!opciones.some((opcion) => opcion.i === correcta)) {
            throw new Error("La opción correcta debe ser una de las que escribiste.");
          }
          const pregunta = await Api.post(`/cases/${casoId}/escenarios/${escenario.id}/preguntas`, {
            enunciado: valores.enunciado,
          });
          for (const opcion of opciones) {
            await Api.post(`/cases/${casoId}/preguntas/${pregunta.id}/opciones`, {
              texto: opcion.texto,
              justificacion: opcion.justificacion,
              es_correcta: opcion.i === correcta,
            });
          }
          abiertos.add(escenario.id);
          await recargar();
          Aviso.exito("Pregunta agregada.");
        },
      });
    }

    function modalOpcion(pregunta) {
      formularioHoja({
        titulo: "Nueva opción",
        textoEnviar: "Agregar opción",
        campos: [
          { id: "texto", etiqueta: "Texto de la opción", requerido: true },
          {
            id: "justificacion",
            etiqueta: "¿Por qué es correcta o incorrecta?",
            tipo: "textarea",
            requerido: true,
          },
          { id: "correcta", etiqueta: "Esta es la opción correcta", tipo: "checkbox" },
        ],
        alEnviar: async (valores) => {
          if (valores.correcta) await quitarCorrectas(pregunta, null);
          await Api.post(`/cases/${casoId}/preguntas/${pregunta.id}/opciones`, {
            texto: valores.texto,
            justificacion: valores.justificacion,
            es_correcta: valores.correcta,
          });
          await recargar();
        },
      });
    }

    async function quitarCorrectas(pregunta, exceptoId) {
      for (const opcion of pregunta.opciones) {
        if (opcion.es_correcta && opcion.id !== exceptoId) {
          await Api.put(`/cases/${casoId}/opciones/${opcion.id}`, {
            texto: opcion.texto,
            justificacion: opcion.justificacion,
            es_correcta: false,
          });
        }
      }
    }

    function filaOpcion(pregunta, opcion, indice) {
      const radio = h("input", {
        type: "radio",
        name: `correcta-${pregunta.id}`,
        "aria-label": `Marcar la opción ${LETRAS[indice] || indice + 1} como correcta`,
      });
      radio.checked = opcion.es_correcta;
      const texto = campoArea(opcion.texto, 2, { "aria-label": "Texto de la opción" });
      const justificacion = campoArea(opcion.justificacion, 2, {
        placeholder: "¿Por qué es correcta o incorrecta? El estudiante lo lee al terminar.",
        "aria-label": "Justificación",
      });
      const cuerpo = () => ({
        texto: texto.value.trim(),
        justificacion: justificacion.value.trim(),
        es_correcta: radio.checked,
      });
      const guardar = () => autoguardar(() => Api.put(`/cases/${casoId}/opciones/${opcion.id}`, cuerpo()));
      texto.addEventListener("change", guardar);
      justificacion.addEventListener("change", guardar);
      radio.addEventListener("change", async () => {
        if (!radio.checked) return;
        await accion(async () => {
          await quitarCorrectas(pregunta, opcion.id);
          await Api.put(`/cases/${casoId}/opciones/${opcion.id}`, cuerpo());
        }, "Opción correcta actualizada.");
      });
      return h(
        "div",
        { clase: `fila-opcion ${opcion.es_correcta ? "es-correcta" : ""}` },
        h(
          "label",
          { clase: "opcion-marca" },
          radio,
          h("span", {}, `${LETRAS[indice] || indice + 1}${opcion.es_correcta ? " · correcta" : ""}`),
        ),
        h("div", { clase: "opcion-campos" }, texto, justificacion),
        h("button", {
          type: "button",
          clase: "boton boton-fantasma boton-chico",
          "aria-label": "Eliminar opción",
          texto: "🗑",
          onclick: () => accion(() => Api.eliminar(`/cases/${casoId}/opciones/${opcion.id}`)),
        }),
      );
    }

    function bloquePregunta(escenario, pregunta, indice) {
      const enunciado = campoArea(pregunta.enunciado, 2, { "aria-label": "Enunciado de la pregunta" });
      enunciado.addEventListener("change", () =>
        autoguardar(() =>
          Api.put(`/cases/${casoId}/preguntas/${pregunta.id}`, { enunciado: enunciado.value.trim() }),
        ),
      );
      const correctas = pregunta.opciones.filter((opcion) => opcion.es_correcta).length;
      const avisos = [];
      if (pregunta.opciones.length < 2) avisos.push("Necesita al menos dos opciones.");
      if (correctas !== 1) avisos.push("Debe tener exactamente una opción correcta.");
      return h(
        "div",
        { clase: "bloque-pregunta" },
        h("label", { clase: "campo" }, h("span", {}, `Pregunta ${indice + 1}`), enunciado),
        pregunta.opciones.map((opcion, i) => filaOpcion(pregunta, opcion, i)),
        avisos.length ? h("p", { clase: "advertencia" }, `⚠ ${avisos.join(" ")}`) : null,
        h(
          "div",
          { clase: "acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "+ Agregar opción",
            onclick: () => modalOpcion(pregunta),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "🗑 Eliminar pregunta",
            onclick: async () => {
              const confirmado = await Modal.confirmar({
                titulo: "¿Eliminar la pregunta?",
                mensaje: "Se borrará con todas sus opciones.",
                textoConfirmar: "Eliminar",
                peligro: true,
              });
              if (confirmado) await accion(() => Api.eliminar(`/cases/${casoId}/preguntas/${pregunta.id}`));
            },
          }),
        ),
      );
    }

    /* ----- puzzles del escenario (Fase 13): opcionales, no puntúan ----- */

    function idsDePuzzlesConCambio(escenario, puzzle, direccion) {
      const lista = (escenario.puzzles || []).map((p) => p.id);
      const origen = lista.indexOf(puzzle.id);
      const destino = origen + direccion;
      if (destino < 0 || destino >= lista.length) return null;
      [lista[origen], lista[destino]] = [lista[destino], lista[origen]];
      return caso.escenarios.flatMap((e) => (e.id === escenario.id ? lista : (e.puzzles || []).map((p) => p.id)));
    }

    function filaPuzzle(escenario, puzzle, i, total) {
      return h(
        "div",
        { clase: "fila-puzzle" },
        h(
          "div",
          { clase: "fila-puzzle-info" },
          h("span", { clase: "chip chip-neutro" }, EditorPuzzles.nombreDe(puzzle.tipo)),
          h("span", { clase: "fila-puzzle-texto" }, puzzle.enunciado),
          h("small", { clase: "texto-suave" }, `⏱ ${puzzle.contenido.tiempo_seg} s`),
        ),
        h(
          "div",
          { clase: "fila-convocado-acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-info boton-chico",
            texto: "👁 Vista previa",
            onclick: () => EditorPuzzles.vistaPrevia(casoId, puzzle),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            "aria-label": "Subir puzzle",
            texto: "▲",
            disabled: i === 0,
            onclick: () => moverPuzzle(escenario, puzzle, -1),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            "aria-label": "Bajar puzzle",
            texto: "▼",
            disabled: i === total - 1,
            onclick: () => moverPuzzle(escenario, puzzle, 1),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "✏ Editar",
            onclick: () =>
              EditorPuzzles.formulario({
                puzzle,
                alGuardar: async (cuerpo) => {
                  await Api.put(`/cases/${casoId}/puzzles/${puzzle.id}`, cuerpo);
                  abiertos.add(escenario.id);
                  await recargar();
                  Aviso.exito("Puzzle guardado.");
                },
              }),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            "aria-label": "Eliminar puzzle",
            texto: "🗑",
            onclick: async () => {
              const confirmado = await Modal.confirmar({
                titulo: "¿Eliminar el puzzle?",
                mensaje: "Se borrará de este escenario.",
                textoConfirmar: "Eliminar",
                peligro: true,
              });
              if (confirmado) await accion(() => Api.eliminar(`/cases/${casoId}/puzzles/${puzzle.id}`));
            },
          }),
        ),
      );
    }

    async function moverPuzzle(escenario, puzzle, direccion) {
      const ids = idsDePuzzlesConCambio(escenario, puzzle, direccion);
      if (!ids) return;
      await accion(() => Api.put(`/cases/${casoId}/orden/puzzles`, { ids }));
    }

    function bloquePuzzles(escenario) {
      const lista = escenario.puzzles || [];
      return h(
        "div",
        { clase: "bloque-puzzles" },
        h("h4", { clase: "puzle-subtitulo" }, `🧩 Puzzles antes de las preguntas (${lista.length} de 3)`),
        h(
          "p",
          { clase: "ayuda" },
          "Opcionales: el estudiante los juega antes de las preguntas de este escenario. No cuentan para la nota y puede saltarlos.",
        ),
        lista.map((puzzle, i) => filaPuzzle(escenario, puzzle, i, lista.length)),
        h("button", {
          type: "button",
          clase: "boton boton-info boton-chico",
          texto: "+ Agregar puzzle",
          disabled: lista.length >= 3,
          onclick: () =>
            EditorPuzzles.formulario({
              puzzle: null,
              alGuardar: async (cuerpo) => {
                await Api.post(`/cases/${casoId}/escenarios/${escenario.id}/puzzles`, cuerpo);
                abiertos.add(escenario.id);
                await recargar();
                Aviso.exito("Puzzle agregado.");
              },
            }),
        }),
      );
    }

    function bloqueComposicion(escenario) {
      const composicion = escenario.composicion;
      return h(
        "div",
        { clase: "bloque-composicion" },
        h("h4", { clase: "puzle-subtitulo" }, "🎨 Imagen del escenario"),
        h(
          "p",
          { clase: "ayuda" },
          composicion
            ? `Composición con ${composicion.capas.length} capa(s). El estudiante la ve de fondo mientras responde las preguntas.`
            : "Opcional: arma la imagen del escenario con el editor visual. Sin ella, el estudiante ve solo el texto del contexto.",
        ),
        h("button", {
          type: "button",
          clase: "boton boton-info boton-chico",
          texto: composicion ? "🎨 Editar composición" : "🎨 Crear composición",
          onclick: () =>
            EditorVisual.abrir({
              casoId,
              escenario,
              alGuardar: () => recargar(),
            }),
        }),
      );
    }

    function bloqueEscenario(escenario, indice) {
      const titulo = campoTexto(escenario.titulo, { "aria-label": "Título del escenario" });
      const contexto = campoArea(escenario.contexto, 3, { "aria-label": "Contexto del escenario" });
      const guardar = () =>
        autoguardar(() =>
          Api.put(`/cases/${casoId}/escenarios/${escenario.id}`, {
            titulo: titulo.value.trim(),
            contexto: contexto.value.trim(),
          }),
        );
      titulo.addEventListener("change", guardar);
      contexto.addEventListener("change", guardar);
      return h(
        "details",
        {
          clase: "bloque-escenario tarjeta",
          open: abiertos.has(escenario.id),
          ontoggle: (evento) => {
            if (evento.target.open) abiertos.add(escenario.id);
            else abiertos.delete(escenario.id);
          },
        },
        h(
          "summary",
          {},
          `🎬 Escenario ${indice + 1}: ${escenario.titulo} · ${escenario.preguntas.length} pregunta(s)`,
        ),
        h("label", { clase: "campo" }, h("span", {}, "Título"), titulo),
        h("label", { clase: "campo" }, h("span", {}, "Qué ocurre en este escenario"), contexto),
        bloqueComposicion(escenario),
        escenario.preguntas.map((pregunta, j) => bloquePregunta(escenario, pregunta, j)),
        bloquePuzzles(escenario),
        h(
          "div",
          { clase: "acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-principal boton-chico",
            texto: "+ Agregar pregunta",
            onclick: () => modalPregunta(escenario),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "🗑 Eliminar escenario",
            onclick: async () => {
              const confirmado = await Modal.confirmar({
                titulo: "¿Eliminar el escenario?",
                mensaje: "Se borrará con todas sus preguntas.",
                textoConfirmar: "Eliminar",
                peligro: true,
              });
              if (confirmado) await accion(() => Api.eliminar(`/cases/${casoId}/escenarios/${escenario.id}`));
            },
          }),
        ),
      );
    }

    function seccionEscenarios() {
      return h(
        "section",
        { clase: "espaciado" },
        h("h3", { clase: "titulo-seccion" }, "2 · Escenarios y preguntas"),
        caso.escenarios.length
          ? caso.escenarios.map((escenario, i) => bloqueEscenario(escenario, i))
          : h(
              "div",
              { clase: "vacio tarjeta" },
              h("p", { clase: "texto-suave" }, "Aún no hay escenarios. Agrega el primero para empezar."),
            ),
        h("button", {
          type: "button",
          clase: "boton boton-principal boton-bloque espaciado",
          texto: "+ Agregar escenario",
          onclick: modalEscenario,
        }),
      );
    }

    /* ----- rúbrica ----- */

    function rubricaAutomatica() {
      const conPreguntas = caso.escenarios.filter((escenario) => escenario.preguntas.length);
      const total = 10000;
      const base = Math.floor(total / conPreguntas.length);
      return {
        nombre: `Rúbrica de ${caso.nombre}`.slice(0, 200),
        descripcion: "",
        escala_min: "0.00",
        escala_max: "5.00",
        nota_aprobatoria: "3.00",
        criterios: conPreguntas.map((escenario, i) => {
          const centesimas = i === conPreguntas.length - 1 ? total - base * i : base;
          return {
            nombre: escenario.titulo,
            descripcion: "",
            peso: (centesimas / 100).toFixed(2),
            pregunta_ids: escenario.preguntas.map((pregunta) => pregunta.id),
          };
        }),
      };
    }

    function cuerpoRubrica(trabajo) {
      return {
        nombre: trabajo.nombre,
        descripcion: trabajo.descripcion || null,
        escala_min: trabajo.escala_min,
        escala_max: trabajo.escala_max,
        nota_aprobatoria: trabajo.nota_aprobatoria,
        publicada: false,
        criterios: trabajo.criterios.map((criterio) => ({
          nombre: criterio.nombre,
          descripcion: criterio.descripcion || null,
          peso: criterio.peso,
          pregunta_ids: criterio.pregunta_ids,
        })),
      };
    }

    async function generarRubrica() {
      if (!caso.escenarios.some((escenario) => escenario.preguntas.length)) {
        Aviso.error("Primero agrega al menos una pregunta.");
        return;
      }
      if (rubrica) {
        const confirmado = await Modal.confirmar({
          titulo: "¿Generar de nuevo la rúbrica?",
          mensaje: "Se reemplazarán los criterios actuales por uno por escenario, con pesos iguales.",
          textoConfirmar: "Generar",
        });
        if (!confirmado) return;
      }
      await accion(
        () => Api.put(`/cases/${casoId}/rubrica`, cuerpoRubrica(rubricaAutomatica())),
        "Rúbrica generada: un criterio por escenario.",
      );
    }

    const centesimas = (valor) => Math.round((parseFloat(valor) || 0) * 100);

    function tarjetaRubrica() {
      const explicacion = h(
        "p",
        { clase: "texto-suave" },
        "La rúbrica reparte la nota entre criterios (los pesos suman 100) y cada pregunta debe pertenecer a un criterio. Lo más fácil es generarla automáticamente y ajustar los pesos si quieres.",
      );
      if (!rubrica) {
        return h(
          "section",
          { clase: "tarjeta espaciado" },
          h("h3", { clase: "titulo-seccion" }, "3 · Rúbrica de evaluación"),
          explicacion,
          h("button", {
            type: "button",
            clase: "boton boton-principal boton-bloque",
            texto: "⚙ Generar rúbrica automática",
            onclick: generarRubrica,
          }),
        );
      }

      const total = h("strong", {});
      const actualizarTotal = () => {
        const suma = rubrica.criterios.reduce((acumulado, criterio) => acumulado + centesimas(criterio.peso), 0);
        total.textContent = `Suma de pesos: ${(suma / 100).toFixed(2)} / 100`;
        total.className = suma === 10000 ? "texto-ok" : "advertencia";
      };

      const vincular = (control, objeto, clave) => {
        control.addEventListener("input", () => {
          objeto[clave] = control.value;
          actualizarTotal();
        });
        return control;
      };

      const criterios = rubrica.criterios.map((criterio, indice) => {
        const casillas = caso.escenarios.flatMap((escenario) =>
          escenario.preguntas.map((pregunta) => {
            const marca = h("input", { type: "checkbox" });
            marca.checked = criterio.pregunta_ids.includes(pregunta.id);
            marca.addEventListener("change", () => {
              criterio.pregunta_ids = marca.checked
                ? [...criterio.pregunta_ids, pregunta.id]
                : criterio.pregunta_ids.filter((id) => id !== pregunta.id);
            });
            return h(
              "label",
              { clase: "casilla casilla-chica" },
              marca,
              h("span", {}, etiquetaPregunta[pregunta.id]),
            );
          }),
        );
        return h(
          "div",
          { clase: "criterio tarjeta" },
          h(
            "div",
            { clase: "campo-doble" },
            h(
              "label",
              { clase: "campo" },
              h("span", {}, "Criterio"),
              vincular(campoTexto(criterio.nombre), criterio, "nombre"),
            ),
            h(
              "label",
              { clase: "campo" },
              h("span", {}, "Peso (%)"),
              vincular(campoTexto(criterio.peso, { type: "number", step: "0.01", min: "0", inputmode: "decimal" }), criterio, "peso"),
            ),
          ),
          h("p", { clase: "ayuda" }, "Preguntas que evalúa este criterio:"),
          h("div", { clase: "lista-casillas" }, casillas),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "Quitar criterio",
            onclick: () => {
              rubrica.criterios.splice(indice, 1);
              pintar();
            },
          }),
        );
      });

      const guardar = async () => {
        if (!rubrica.nombre.trim()) {
          Aviso.error("Ponle un nombre a la rúbrica.");
          return;
        }
        if (!rubrica.criterios.length) {
          Aviso.error("Agrega al menos un criterio.");
          return;
        }
        const suma = rubrica.criterios.reduce((acumulado, criterio) => acumulado + centesimas(criterio.peso), 0);
        if (suma !== 10000) {
          Aviso.error("Los pesos de los criterios deben sumar exactamente 100.");
          return;
        }
        await accion(() => Api.put(`/cases/${casoId}/rubrica`, cuerpoRubrica(rubrica)), "Rúbrica guardada.");
      };

      const tarjeta = h(
        "section",
        { clase: "tarjeta espaciado" },
        h("h3", { clase: "titulo-seccion" }, "3 · Rúbrica de evaluación"),
        explicacion,
        h("label", { clase: "campo" }, h("span", {}, "Nombre"), vincular(campoTexto(rubrica.nombre), rubrica, "nombre")),
        h(
          "div",
          { clase: "campo-triple" },
          h("label", { clase: "campo" }, h("span", {}, "Nota mínima"), vincular(campoTexto(rubrica.escala_min, { type: "number", step: "0.01", inputmode: "decimal" }), rubrica, "escala_min")),
          h("label", { clase: "campo" }, h("span", {}, "Nota máxima"), vincular(campoTexto(rubrica.escala_max, { type: "number", step: "0.01", inputmode: "decimal" }), rubrica, "escala_max")),
          h("label", { clase: "campo" }, h("span", {}, "Aprueba con"), vincular(campoTexto(rubrica.nota_aprobatoria, { type: "number", step: "0.01", inputmode: "decimal" }), rubrica, "nota_aprobatoria")),
        ),
        criterios,
        h("p", {}, total),
        h(
          "div",
          { clase: "acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "+ Agregar criterio",
            onclick: () => {
              rubrica.criterios.push({ nombre: "Nuevo criterio", descripcion: "", peso: "0.00", pregunta_ids: [] });
              pintar();
            },
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "⚙ Regenerar automática",
            onclick: generarRubrica,
          }),
          h("button", { type: "button", clase: "boton boton-principal", texto: "Guardar rúbrica", onclick: guardar }),
        ),
      );
      actualizarTotal();
      return tarjeta;
    }

    /* ----- caso ya publicado o archivado: solo lectura ----- */

    function vistaLectura() {
      const acciones = [];
      if (caso.estado === "PUBLICADO") {
        if (alAgendar) {
          acciones.push(
            h("button", {
              type: "button",
              clase: "boton boton-principal",
              texto: "👥 Asignar a estudiantes",
              onclick: () => alAgendar(caso.id),
            }),
          );
        }
        acciones.push(
          h("button", {
            type: "button",
            clase: "boton boton-fantasma",
            texto: "🗄 Archivar",
            onclick: async () => {
              const confirmado = await Modal.confirmar({
                titulo: "¿Archivar el caso?",
                mensaje: "Dejará de poder agendarse. Las sesiones ya hechas se conservan.",
                textoConfirmar: "Archivar",
                peligro: true,
              });
              if (!confirmado) return;
              await accion(() => Api.post(`/cases/${casoId}/archive`), "Caso archivado.");
              if (alCambiar) alCambiar();
            },
          }),
        );
      }
      acciones.push(
        h("button", {
          type: "button",
          clase: "boton boton-fantasma",
          texto: "📝 Crear nueva versión",
          onclick: async () => {
            try {
              const nueva = await Api.post(`/cases/${casoId}/new-version`);
              Aviso.exito("Nueva versión creada como borrador.");
              if (alCambiar) alCambiar();
              abrir(contenedor, nueva.id, { alVolver, alAgendar, alCambiar });
            } catch (error) {
              Aviso.deError(error);
            }
          },
        }),
      );

      return [
        h(
          "section",
          { clase: "tarjeta espaciado" },
          h(
            "p",
            { clase: "texto-suave" },
            "Este caso ya no se puede editar porque pudo haberse usado con estudiantes. Para cambiarlo, crea una nueva versión.",
          ),
          h("div", { clase: "acciones" }, acciones),
        ),
        h("section", { clase: "tarjeta espaciado" }, h("h3", { clase: "titulo-tarjeta" }, "Contexto"), h("p", {}, caso.contexto_historia), h("h3", { clase: "titulo-tarjeta" }, "Desarrollo situacional"), h("p", {}, caso.desarrollo_situacional)),
        caso.escenarios.map((escenario, i) =>
          h(
            "section",
            { clase: "tarjeta espaciado" },
            h("h3", { clase: "titulo-tarjeta" }, `🎬 Escenario ${i + 1}: ${escenario.titulo}`),
            h("p", { clase: "texto-suave" }, escenario.contexto),
            escenario.composicion &&
              h("button", {
                type: "button",
                clase: "boton boton-info boton-chico",
                texto: "🎨 Ver composición del escenario",
                onclick: () => EditorVisual.abrir({ casoId, escenario, soloLectura: true }),
              }),
            (escenario.puzzles || []).map((puzzle) =>
              h(
                "div",
                { clase: "fila-puzzle" },
                h(
                  "div",
                  { clase: "fila-puzzle-info" },
                  h("span", { clase: "chip chip-neutro" }, EditorPuzzles.nombreDe(puzzle.tipo)),
                  h("span", { clase: "fila-puzzle-texto" }, puzzle.enunciado),
                ),
                h("button", {
                  type: "button",
                  clase: "boton boton-info boton-chico",
                  texto: "👁 Vista previa",
                  onclick: () => EditorPuzzles.vistaPrevia(casoId, puzzle),
                }),
              ),
            ),
            escenario.preguntas.map((pregunta, j) =>
              h(
                "div",
                { clase: "bloque-pregunta" },
                h("strong", {}, `${j + 1}. ${pregunta.enunciado}`),
                h(
                  "ul",
                  { clase: "lista-opciones" },
                  pregunta.opciones.map((opcion) =>
                    h(
                      "li",
                      { clase: opcion.es_correcta ? "es-correcta" : "" },
                      `${opcion.es_correcta ? "✔ " : ""}${opcion.texto}`,
                      h("small", { clase: "texto-suave" }, ` — ${opcion.justificacion}`),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
        caso.rubrica &&
          h(
            "section",
            { clase: "tarjeta espaciado" },
            h("h3", { clase: "titulo-tarjeta" }, "Rúbrica"),
            h(
              "p",
              { clase: "texto-suave" },
              `Escala ${caso.rubrica.escala_min}–${caso.rubrica.escala_max}, aprueba con ${caso.rubrica.nota_aprobatoria}.`,
            ),
            h(
              "ul",
              { clase: "meta meta-vertical" },
              caso.rubrica.criterios.map((criterio) =>
                h("li", {}, `${criterio.nombre}: ${criterio.peso}% (${criterio.pregunta_ids.length} pregunta/s)`),
              ),
            ),
          ),
      ];
    }

    /* ----- pintar ----- */

    function pintar() {
      const editable = caso.estado === "BORRADOR";
      const [textoEstado, tipoEstado] = ESTADOS[caso.estado] || [caso.estado, "neutro"];
      const preguntas = caso.escenarios.reduce((total, escenario) => total + escenario.preguntas.length, 0);
      reemplazar(
        contenedor,
        h("button", {
          type: "button",
          clase: "boton boton-fantasma boton-chico",
          texto: "← Volver a mis casos",
          onclick: alVolver,
        }),
        h(
          "section",
          { clase: "tarjeta elevada aparece espaciado" },
          h(
            "div",
            { clase: "tarjeta-fila" },
            h("h2", { clase: "titulo-tarjeta" }, caso.nombre),
            chip(textoEstado, tipoEstado),
          ),
          h(
            "ul",
            { clase: "meta" },
            h("li", {}, `⏱ ${caso.tiempo_estimado_min} min`),
            h("li", {}, `🎬 ${caso.escenarios.length} escenarios`),
            h("li", {}, `❓ ${preguntas} preguntas`),
            h("li", {}, `v${caso.version}`),
          ),
        ),
        editable
          ? [panelPublicacion(), tarjetaDatos(), seccionEscenarios(), tarjetaRubrica()]
          : vistaLectura(),
      );
    }

    reemplazar(contenedor, h("p", { clase: "texto-suave" }, h("span", { clase: "icono-carga" }), " Cargando caso…"));
    window.scrollTo({ top: 0 });
    await recargar();
  }

  return { abrir, crearCaso };
})();
