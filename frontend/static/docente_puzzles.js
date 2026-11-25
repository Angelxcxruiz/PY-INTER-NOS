"use strict";

/*
 * Editor de puzzles del docente (Fase 13): un formulario por tipo, sin escribir JSON.
 * El servidor valida el contenido (límites, repetidos, coherencia); aquí solo se ayuda a armarlo.
 * La vista previa juega el puzzle exactamente como lo verá el estudiante (barajado, sin solución).
 */

const EditorPuzzles = (() => {
  const h = Dom.h.bind(Dom);

  const TIPOS = [
    ["ORDENAR_SECUENCIA", "🔢 Ordenar la secuencia"],
    ["EMPAREJAR_CONCEPTOS", "🔗 Emparejar conceptos"],
    ["PIEZA_FALTANTE", "🧩 La pieza que falta"],
    ["CLASIFICAR", "🗂️ Clasificar"],
  ];
  const nombreDe = (tipo) => (TIPOS.find(([valor]) => valor === tipo) || [tipo, tipo])[1];

  function campoTexto(valor, placeholder, etiqueta) {
    const entrada = h("input", { type: "text", maxlength: "200", placeholder: placeholder || "", "aria-label": etiqueta || placeholder || "Texto" });
    entrada.value = valor || "";
    return entrada;
  }

  /*
   * Lista con filas que se agregan y quitan. `crearCampos(valor)` devuelve
   * { elemento, leer() } y la lista respeta mínimo y máximo de filas.
   */
  function listaEditable({ titulo, ayuda, minimo, maximo, iniciales, crearCampos, textoAgregar }) {
    const filas = [];
    const cuerpo = h("div", { clase: "lista-filas" });
    const agregar = h("button", { type: "button", clase: "boton boton-fantasma boton-chico", texto: textoAgregar });

    function refrescar() {
      agregar.classList.toggle("oculto", filas.length >= maximo);
      filas.forEach((fila) => {
        fila.quitar.disabled = filas.length <= minimo;
      });
    }
    function anadir(valor) {
      if (filas.length >= maximo) return;
      const campos = crearCampos(valor);
      const quitar = h("button", {
        type: "button",
        clase: "boton boton-fantasma boton-icono",
        "aria-label": "Quitar fila",
        texto: "🗑",
        onclick: () => {
          if (filas.length <= minimo) return;
          filas.splice(filas.indexOf(fila), 1);
          fila.nodo.remove();
          refrescar();
        },
      });
      const fila = { campos, quitar, nodo: h("div", { clase: "fila-editable" }, campos.elemento, quitar) };
      filas.push(fila);
      cuerpo.append(fila.nodo);
      refrescar();
    }
    agregar.addEventListener("click", () => anadir());
    (iniciales && iniciales.length ? iniciales : Array.from({ length: minimo }, () => undefined)).forEach(anadir);

    return {
      elemento: h(
        "div",
        { clase: "lista-editable" },
        h("p", { clase: "puzle-subtitulo" }, titulo),
        ayuda && h("p", { clase: "ayuda" }, ayuda),
        cuerpo,
        agregar,
      ),
      leer: () => filas.map((fila) => fila.campos.leer()),
    };
  }

  /* ---------- un constructor de sub-formulario por tipo ---------- */

  function formOrdenar(contenido) {
    const pasos = listaEditable({
      titulo: "Pasos en el orden CORRECTO",
      ayuda: "Escríbelos en el orden correcto: el estudiante los verá barajados. Entre 3 y 8 pasos.",
      minimo: 3,
      maximo: 8,
      iniciales: contenido && contenido.pasos,
      textoAgregar: "+ Agregar paso",
      crearCampos: (valor) => {
        const entrada = campoTexto(valor, "Paso", "Paso");
        return { elemento: entrada, leer: () => entrada.value.trim() };
      },
    });
    return { elemento: pasos.elemento, leer: () => ({ pasos: pasos.leer() }) };
  }

  function formEmparejar(contenido) {
    const pares = listaEditable({
      titulo: "Parejas término ↔ definición",
      ayuda: "Entre 3 y 6 parejas. El estudiante verá los términos y las definiciones por separado y barajados.",
      minimo: 3,
      maximo: 6,
      iniciales: contenido && contenido.pares,
      textoAgregar: "+ Agregar pareja",
      crearCampos: (valor) => {
        const termino = campoTexto(valor && valor.termino, "Término", "Término");
        const definicion = campoTexto(valor && valor.definicion, "Definición", "Definición");
        return {
          elemento: h("div", { clase: "campo-doble" }, termino, definicion),
          leer: () => ({ termino: termino.value.trim(), definicion: definicion.value.trim() }),
        };
      },
    });
    return { elemento: pares.elemento, leer: () => ({ pares: pares.leer() }) };
  }

  function formPieza(contenido) {
    const nombreRadio = `falta-${Math.random().toString(36).slice(2)}`;
    const inicial = contenido
      ? contenido.serie.map((texto, i) => ({ texto, falta: i === contenido.faltante }))
      : undefined;
    const serie = listaEditable({
      titulo: "La serie completa",
      ayuda: "Entre 3 y 8 elementos. Marca con el círculo cuál se ocultará: esa es la pieza que falta.",
      minimo: 3,
      maximo: 8,
      iniciales: inicial,
      textoAgregar: "+ Agregar elemento",
      crearCampos: (valor) => {
        const entrada = campoTexto(valor && valor.texto, "Elemento", "Elemento de la serie");
        const radio = h("input", { type: "radio", name: nombreRadio, "aria-label": "Es la pieza que falta" });
        radio.checked = Boolean(valor && valor.falta);
        return {
          elemento: h("div", { clase: "campo-radio" }, radio, entrada),
          leer: () => ({ texto: entrada.value.trim(), falta: radio.checked }),
        };
      },
    });
    const distractores = listaEditable({
      titulo: "Opciones incorrectas (distractores)",
      ayuda: "De 1 a 4. Se mezclan con la pieza correcta.",
      minimo: 1,
      maximo: 4,
      iniciales: contenido && contenido.distractores,
      textoAgregar: "+ Agregar distractor",
      crearCampos: (valor) => {
        const entrada = campoTexto(valor, "Opción incorrecta", "Distractor");
        return { elemento: entrada, leer: () => entrada.value.trim() };
      },
    });
    return {
      elemento: h("div", {}, serie.elemento, distractores.elemento),
      leer: () => {
        const filas = serie.leer();
        const indice = filas.findIndex((fila) => fila.falta);
        if (indice === -1) throw new Error("Marca cuál es la pieza que falta en la serie.");
        return { serie: filas.map((fila) => fila.texto), faltante: indice, distractores: distractores.leer() };
      },
    };
  }

  function formClasificar(contenido) {
    const categorias = listaEditable({
      titulo: "Categorías",
      ayuda: "De 2 a 4. Cada una necesita al menos un elemento.",
      minimo: 2,
      maximo: 4,
      iniciales: contenido && contenido.categorias,
      textoAgregar: "+ Agregar categoría",
      crearCampos: (valor) => {
        const entrada = campoTexto(valor, "Categoría", "Categoría");
        return { elemento: entrada, leer: () => entrada.value.trim() };
      },
    });
    const elementos = listaEditable({
      titulo: "Elementos y su categoría correcta",
      ayuda: "De 3 a 10 elementos. El estudiante los verá sin categoría y deberá ubicarlos.",
      minimo: 3,
      maximo: 10,
      iniciales: contenido && contenido.elementos,
      textoAgregar: "+ Agregar elemento",
      crearCampos: (valor) => {
        const texto = campoTexto(valor && valor.texto, "Elemento", "Elemento");
        const selector = h("select", { "aria-label": "Categoría correcta" });
        const llenar = () => {
          const actual = selector.value || (valor && valor.categoria) || "";
          const nombres = categorias.leer().filter(Boolean);
          selector.replaceChildren(...nombres.map((nombre) => h("option", { value: nombre }, nombre)));
          if (nombres.includes(actual)) selector.value = actual;
        };
        llenar();
        selector.addEventListener("focus", llenar);
        selector.addEventListener("pointerdown", llenar);
        return {
          elemento: h("div", { clase: "campo-doble" }, texto, selector),
          leer: () => ({ texto: texto.value.trim(), categoria: selector.value }),
        };
      },
    });
    return {
      elemento: h("div", {}, categorias.elemento, elementos.elemento),
      leer: () => ({ categorias: categorias.leer(), elementos: elementos.leer() }),
    };
  }

  const FORMULARIOS = {
    ORDENAR_SECUENCIA: formOrdenar,
    EMPAREJAR_CONCEPTOS: formEmparejar,
    PIEZA_FALTANTE: formPieza,
    CLASIFICAR: formClasificar,
  };

  /*
   * Abre el formulario para crear (puzzle = null) o editar un puzzle.
   * `alGuardar(cuerpo)` recibe { tipo, enunciado, contenido } y debe lanzar si el servidor lo rechaza.
   */
  function formulario({ puzzle, alGuardar }) {
    const selectorTipo = h(
      "select",
      { "aria-label": "Tipo de puzzle" },
      TIPOS.map(([valor, nombre]) => h("option", { value: valor }, nombre)),
    );
    selectorTipo.value = puzzle ? puzzle.tipo : TIPOS[0][0];
    const enunciado = h("textarea", { rows: "2", maxlength: "300", placeholder: "Ej.: Ordena los pasos de los primeros auxilios psicológicos" });
    enunciado.value = puzzle ? puzzle.enunciado : "";
    const tiempo = h("input", { type: "number", min: "30", max: "60", inputmode: "numeric", "aria-label": "Tiempo en segundos" });
    tiempo.value = String(puzzle ? puzzle.contenido.tiempo_seg : 45);

    const zona = h("div", { clase: "puzle-subformulario" });
    const borradores = {};
    let actual = null;
    function pintarSubformulario() {
      const tipo = selectorTipo.value;
      const inicial = puzzle && puzzle.tipo === tipo ? puzzle.contenido : null;
      actual = borradores[tipo] || (borradores[tipo] = FORMULARIOS[tipo](inicial));
      Dom.reemplazar(zona, actual.elemento);
    }
    selectorTipo.addEventListener("change", pintarSubformulario);
    pintarSubformulario();

    const enviar = h("button", { type: "submit", clase: "boton boton-principal boton-bloque" }, puzzle ? "Guardar puzzle" : "Agregar puzzle");
    const formulario = h(
      "form",
      { clase: "formulario", novalidate: true },
      h("p", { clase: "ayuda" }, "Los puzzles son opcionales y no cuentan para la nota. El estudiante puede saltarlos."),
      h("label", { clase: "campo" }, h("span", {}, "Tipo"), selectorTipo),
      h("label", { clase: "campo" }, h("span", {}, "Enunciado"), enunciado),
      h("label", { clase: "campo" }, h("span", {}, "Tiempo para resolverlo (30 a 60 segundos)"), tiempo),
      zona,
      enviar,
    );
    const hoja = Modal.hoja(puzzle ? "Editar puzzle" : "Nuevo puzzle", formulario);

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      if (!enunciado.value.trim()) {
        Aviso.error("Escribe el enunciado del puzzle.");
        return;
      }
      let contenido;
      try {
        contenido = { tiempo_seg: parseInt(tiempo.value, 10) || 45, ...actual.leer() };
      } catch (error) {
        Aviso.error(error.message);
        return;
      }
      enviar.disabled = true;
      try {
        await alGuardar({ tipo: selectorTipo.value, enunciado: enunciado.value.trim(), contenido });
        hoja.cerrar();
      } catch (error) {
        Aviso.deError(error);
        enviar.disabled = false;
      }
    });
    return hoja;
  }

  /* Juega el puzzle como el estudiante: barajado, sin solución y verificado por el servidor. */
  async function vistaPrevia(casoId, puzzle) {
    let vista;
    try {
      vista = await Api.get(`/cases/${encodeURIComponent(casoId)}/puzzles/${encodeURIComponent(puzzle.id)}/vista-previa`);
    } catch (error) {
      Aviso.deError(error);
      return;
    }
    const contenedor = h("div", { clase: "puzle-previa" });
    const hoja = Modal.hoja("Vista previa: así lo verá el estudiante", contenedor);
    let juego = Puzzles.montar(contenedor, vista, {
      verificar: (respuesta) => Api.post(`/puzzles/${encodeURIComponent(puzzle.id)}/verificar`, { respuesta }),
      alTerminar: () => {
        juego.destruir();
        hoja.cerrar();
      },
    });
  }

  return { formulario, vistaPrevia, nombreDe, TIPOS };
})();
