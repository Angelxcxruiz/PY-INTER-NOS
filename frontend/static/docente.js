"use strict";

(function () {
  const claims = Api.exigirRol("DOCENTE", "ADMINISTRADOR");
  if (!claims) return;

  const h = Dom.h.bind(Dom);
  const $ = Dom.$;
  const reemplazar = Dom.reemplazar;

  const ESTADOS_CASO = {
    BORRADOR: "Borrador",
    PUBLICADO: "Publicado",
    ARCHIVADO: "Archivado",
  };
  const ESTADOS_SESION = {
    SIN_INICIAR: "Sin iniciar",
    EN_CURSO: "En curso",
    FINALIZADO: "Finalizado",
  };
  const CLAVE_CONVOCADOS = "inn_convocados";

  const estado = { casos: [], sesiones: [], espacios: null, usuarios: null };

  /* ---------- utilidades ---------- */

  const chip = (texto, tipo) => h("span", { clase: `chip chip-${tipo}` }, texto);

  const tipoChipCaso = (e) => ({ PUBLICADO: "ok", BORRADOR: "aviso", ARCHIVADO: "neutro" })[e] || "neutro";
  const tipoChipSesion = (e) =>
    ({ EN_CURSO: "ok", SIN_INICIAR: "aviso", FINALIZADO: "neutro" })[e] || "neutro";

  function vacio(texto) {
    return h("div", { clase: "vacio tarjeta" }, h("p", { clase: "texto-suave" }, texto));
  }

  function nombreCaso(casoId) {
    const caso = estado.casos.find((c) => c.id === casoId);
    return caso ? caso.nombre : "Caso";
  }

  function leerMapaConvocados() {
    try {
      return JSON.parse(sessionStorage.getItem(CLAVE_CONVOCADOS) || "{}");
    } catch (_) {
      return {};
    }
  }

  function recordarConvocados(convocatorias, convocados) {
    const mapa = leerMapaConvocados();
    convocatorias.forEach((convocatoria, indice) => {
      const dato = convocados[indice];
      if (dato) mapa[convocatoria.estudiante_id] = { correo: dato.correo, nombre: dato.nombre };
    });
    sessionStorage.setItem(CLAVE_CONVOCADOS, JSON.stringify(mapa));
  }

  async function cargarUsuariosSiAdmin() {
    if (claims.rol !== "ADMINISTRADOR" || estado.usuarios) return;
    try {
      const usuarios = await Api.get("/admin/users", { limite: 100 });
      estado.usuarios = Object.fromEntries(
        usuarios.map((u) => [u.id, { correo: u.correo, nombre: u.nombre }]),
      );
    } catch (_) {
      estado.usuarios = {};
    }
  }

  function datosEstudiante(estudianteId) {
    const mapa = { ...leerMapaConvocados(), ...(estado.usuarios || {}) };
    return mapa[estudianteId] || null;
  }

  async function asegurarCasos() {
    if (!estado.casos.length) estado.casos = await Api.get("/cases", { limite: 100 });
  }

  /* ---------- casos ---------- */

  async function cargarCasos() {
    const lista = $("#lista-casos");
    try {
      estado.casos = await Api.get("/cases", { limite: 100 });
    } catch (error) {
      Aviso.deError(error);
      reemplazar(lista, vacio("No se pudieron cargar los casos."));
      return;
    }
    if (!estado.casos.length) {
      reemplazar(lista, vacio("Todavía no tienes casos creados."));
      return;
    }
    reemplazar(
      lista,
      estado.casos.map((caso) => {
        const publicado = caso.estado === "PUBLICADO";
        const preguntas = caso.escenarios.reduce((total, e) => total + e.preguntas.length, 0);
        return h(
          "article",
          { clase: "tarjeta tarjeta-caso aparece" },
          h(
            "div",
            { clase: "tarjeta-fila" },
            h("h3", { clase: "titulo-tarjeta" }, caso.nombre),
            chip(ESTADOS_CASO[caso.estado] || caso.estado, tipoChipCaso(caso.estado)),
          ),
          h("p", { clase: "texto-suave recorte" }, caso.contexto_historia),
          h(
            "ul",
            { clase: "meta" },
            h("li", {}, `⏱ ${caso.tiempo_estimado_min} min`),
            h("li", {}, `🎬 ${caso.escenarios.length} escenarios`),
            h("li", {}, `❓ ${preguntas} preguntas`),
            h("li", {}, `v${caso.version}`),
          ),
          h("button", {
            type: "button",
            clase: "boton boton-principal boton-bloque",
            texto: publicado ? "Agendar" : "Publica el caso para agendarlo",
            disabled: !publicado,
            onclick: () => abrirFormularioAgendar(caso.id),
          }),
        );
      }),
    );
  }

  /* ---------- sesiones ---------- */

  async function cargarSesiones() {
    const lista = $("#lista-sesiones");
    try {
      await asegurarCasos();
      estado.sesiones = await Api.get("/sessions", { limite: 100 });
    } catch (error) {
      Aviso.deError(error);
      reemplazar(lista, vacio("No se pudieron cargar las sesiones."));
      return;
    }
    if (!estado.sesiones.length) {
      reemplazar(lista, vacio("Aún no hay sesiones. Usa «Agendar» para crear la primera."));
      return;
    }
    reemplazar(
      lista,
      estado.sesiones.map((sesion) =>
        h(
          "article",
          { clase: "tarjeta tarjeta-sesion aparece" },
          h(
            "div",
            { clase: "tarjeta-fila" },
            h("h3", { clase: "titulo-tarjeta" }, nombreCaso(sesion.caso_id)),
            chip(ESTADOS_SESION[sesion.estado] || sesion.estado, tipoChipSesion(sesion.estado)),
          ),
          h(
            "ul",
            { clase: "meta" },
            h("li", {}, `🗓 ${Fechas.formatear(sesion.inicio_programado)}`),
            h("li", {}, `⏱ ${sesion.tiempo_maximo_min} min`),
            sesion.lugar_fisico && h("li", {}, `📍 ${sesion.lugar_fisico}`),
          ),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-bloque",
            texto: "Abrir sesión",
            onclick: () => abrirDetalle(sesion.id),
          }),
        ),
      ),
    );
  }

  /* ---------- formulario "Agendar" ---------- */

  async function abrirFormularioAgendar(casoIdInicial) {
    try {
      await asegurarCasos();
      if (!estado.espacios) estado.espacios = await Api.get("/espacios-academicos");
    } catch (error) {
      Aviso.deError(error);
      return;
    }
    const publicados = estado.casos.filter((c) => c.estado === "PUBLICADO");
    if (!publicados.length) {
      Aviso.info("Necesitas al menos un caso publicado para agendar una sesión.");
      return;
    }

    const selectorCaso = h(
      "select",
      { id: "f-caso", required: true },
      publicados.map((c) =>
        h("option", { value: c.id, selected: c.id === casoIdInicial }, c.nombre),
      ),
    );
    const selectorEspacio = h(
      "select",
      { id: "f-espacio" },
      estado.espacios.map((e) => h("option", { value: e.id }, e.codigo ? `${e.nombre} (${e.codigo})` : e.nombre)),
      h("option", { value: "__nuevo__" }, "➕ Crear un espacio nuevo…"),
    );
    const bloqueNuevoEspacio = h(
      "div",
      { clase: "campo-doble oculto", id: "bloque-espacio-nuevo" },
      h("label", { clase: "campo" }, h("span", {}, "Nombre del espacio"), h("input", { id: "f-espacio-nombre", type: "text" })),
      h("label", { clase: "campo" }, h("span", {}, "Código (opcional)"), h("input", { id: "f-espacio-codigo", type: "text" })),
    );
    const entradaInicio = h("input", { id: "f-inicio", type: "datetime-local", required: true, value: Fechas.bogotaEn(10) });
    const entradaFin = h("input", { id: "f-fin", type: "datetime-local", required: true, value: Fechas.bogotaEn(70) });
    const entradaTiempo = h("input", { id: "f-tiempo", type: "number", min: "1", inputmode: "numeric", required: true });
    const ayudaTiempo = h("small", { clase: "ayuda" });

    const alCambiarCaso = () => {
      const caso = publicados.find((c) => c.id === selectorCaso.value);
      entradaTiempo.max = String(caso.tiempo_estimado_min);
      entradaTiempo.value = String(caso.tiempo_estimado_min);
      ayudaTiempo.textContent = `Máximo permitido para este caso: ${caso.tiempo_estimado_min} min.`;
    };
    selectorCaso.addEventListener("change", alCambiarCaso);
    selectorEspacio.addEventListener("change", () => {
      bloqueNuevoEspacio.classList.toggle("oculto", selectorEspacio.value !== "__nuevo__");
    });
    if (!estado.espacios.length) {
      selectorEspacio.value = "__nuevo__";
      bloqueNuevoEspacio.classList.remove("oculto");
    }
    alCambiarCaso();

    const botonEnviar = h("button", { type: "submit", clase: "boton boton-principal boton-bloque" }, "Agendar sesión");
    const formulario = h(
      "form",
      { clase: "formulario", novalidate: true },
      h("label", { clase: "campo" }, h("span", {}, "Caso"), selectorCaso),
      h("div", { clase: "campo-doble" },
        h("label", { clase: "campo" }, h("span", {}, "Inicio (hora de Bogotá)"), entradaInicio),
        h("label", { clase: "campo" }, h("span", {}, "Fin (hora de Bogotá)"), entradaFin),
      ),
      h("label", { clase: "campo" }, h("span", {}, "Tiempo máximo por estudiante (min)"), entradaTiempo, ayudaTiempo),
      h("label", { clase: "campo" }, h("span", {}, "Espacio académico"), selectorEspacio),
      bloqueNuevoEspacio,
      h("label", { clase: "campo" }, h("span", {}, "Lugar físico (opcional)"), h("input", { id: "f-lugar", type: "text" })),
      h("label", { clase: "campo" }, h("span", {}, "Mensaje para los estudiantes (opcional)"), h("textarea", { id: "f-mensaje", rows: "2" })),
      h("label", { clase: "campo" },
        h("span", {}, "Convocados"),
        h("textarea", {
          id: "f-convocados",
          rows: "4",
          placeholder: "correo@universidad.edu, Nombre Apellido\nuno por línea",
        }),
        h("small", { clase: "ayuda" }, "Un estudiante por línea: correo y nombre separados por coma."),
      ),
      botonEnviar,
    );

    const hoja = Modal.hoja("Agendar sesión", formulario);

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      let cuerpo, convocados;
      try {
        ({ cuerpo, convocados } = leerFormulario());
      } catch (error) {
        Aviso.error(error.message);
        return;
      }
      botonEnviar.disabled = true;
      try {
        const sesion = await Api.post("/sessions", cuerpo);
        let aviso = "Sesión agendada.";
        if (convocados.length) {
          try {
            const creadas = await Api.post(`/sessions/${sesion.id}/convocatorias`, convocados);
            recordarConvocados(creadas, convocados);
          } catch (error) {
            aviso = "Sesión agendada, pero no se pudo convocar a los estudiantes: " + Api.mensajeDe(error);
          }
        }
        estado.espacios = null;
        hoja.cerrar();
        Aviso.exito(aviso);
        activarSeccion("sesiones");
        await cargarSesiones();
      } catch (error) {
        Aviso.deError(error);
        botonEnviar.disabled = false;
      }
    });

    function leerFormulario() {
      const inicio = entradaInicio.value;
      const fin = entradaFin.value;
      if (!inicio || !fin) throw new Error("Indica la fecha y hora de inicio y de fin.");
      if (fin <= inicio) throw new Error("El fin debe ser posterior al inicio.");
      const tiempo = parseInt(entradaTiempo.value, 10);
      if (!tiempo || tiempo < 1) throw new Error("Indica el tiempo máximo en minutos.");
      if (tiempo > parseInt(entradaTiempo.max, 10)) {
        throw new Error("El tiempo máximo no puede superar el tiempo estimado del caso.");
      }

      const cuerpo = {
        caso_id: selectorCaso.value,
        inicio_programado: Fechas.deBogotaAIso(inicio),
        fin_programado: Fechas.deBogotaAIso(fin),
        tiempo_maximo_min: tiempo,
        lugar_fisico: $("#f-lugar", formulario).value.trim() || null,
        mensaje_personalizado: $("#f-mensaje", formulario).value.trim() || null,
        convocados: [],
      };
      if (selectorEspacio.value === "__nuevo__") {
        const nombre = $("#f-espacio-nombre", formulario).value.trim();
        if (!nombre) throw new Error("Escribe el nombre del espacio académico.");
        cuerpo.espacio_academico = {
          nombre,
          codigo: $("#f-espacio-codigo", formulario).value.trim() || null,
        };
      } else {
        cuerpo.espacio_academico_id = selectorEspacio.value;
      }

      const vistos = new Set();
      const convocados = [];
      $("#f-convocados", formulario).value.split("\n").forEach((linea) => {
        const texto = linea.trim();
        if (!texto) return;
        const [correoCrudo, ...resto] = texto.split(/[,;\t]/);
        const correo = correoCrudo.trim().toLowerCase();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
          throw new Error(`El correo «${correoCrudo.trim()}» no es válido.`);
        }
        if (vistos.has(correo)) return;
        vistos.add(correo);
        const nombre = resto.join(" ").trim() || correo.split("@")[0];
        convocados.push({ correo, nombre });
      });
      return { cuerpo, convocados };
    }
  }

  /* ---------- detalle de sesión ---------- */

  async function abrirDetalle(sesionId) {
    const vista = $("#vista-detalle");
    $("#vista-lista").classList.add("oculto");
    vista.classList.remove("oculto");
    reemplazar(vista, h("p", { clase: "texto-suave" }, "Cargando sesión…"));
    window.scrollTo({ top: 0 });
    await pintarDetalle(sesionId);
  }

  function volverALista() {
    $("#vista-detalle").classList.add("oculto");
    $("#vista-lista").classList.remove("oculto");
    cargarSesiones();
  }

  async function pintarDetalle(sesionId) {
    const vista = $("#vista-detalle");
    let sesion, convocatorias;
    try {
      await asegurarCasos();
      await cargarUsuariosSiAdmin();
      [sesion, convocatorias] = await Promise.all([
        Api.get(`/sessions/${sesionId}`),
        Api.get(`/sessions/${sesionId}/convocatorias`),
      ]);
    } catch (error) {
      Aviso.deError(error);
      volverALista();
      return;
    }

    const acciones = [];
    if (sesion.estado === "SIN_INICIAR") {
      acciones.push(
        h("button", {
          type: "button",
          clase: "boton boton-principal boton-grande",
          texto: "▶ Iniciar sesión",
          onclick: () => cambiarEstado(sesion, "start", {
            titulo: "¿Iniciar la sesión?",
            mensaje: "Los estudiantes convocados podrán entrar y comenzar el caso.",
            textoConfirmar: "Iniciar",
          }),
        }),
      );
    }
    if (sesion.estado === "EN_CURSO") {
      acciones.push(
        h("button", {
          type: "button",
          clase: "boton boton-peligro boton-grande",
          texto: "■ Finalizar sesión",
          onclick: () => cambiarEstado(sesion, "finish", {
            titulo: "¿Finalizar la sesión?",
            mensaje: "Se cerrarán las participaciones en curso y los estudiantes ya no podrán entrar.",
            textoConfirmar: "Finalizar",
            peligro: true,
          }),
        }),
      );
    }

    const entradaCorreo = h("input", { type: "email", placeholder: "correo@universidad.edu", required: true, inputmode: "email" });
    const entradaNombre = h("input", { type: "text", placeholder: "Nombre", required: true });
    const formularioConvocar = h(
      "form",
      {
        clase: "formulario formulario-en-linea",
        onsubmit: async (evento) => {
          evento.preventDefault();
          const correo = entradaCorreo.value.trim().toLowerCase();
          const nombre = entradaNombre.value.trim() || correo.split("@")[0];
          if (!correo) return;
          try {
            const creadas = await Api.post(`/sessions/${sesion.id}/convocatorias`, [{ correo, nombre }]);
            recordarConvocados(creadas, [{ correo, nombre }]);
            Aviso.exito("Estudiante convocado.");
            await pintarDetalle(sesion.id);
          } catch (error) {
            Aviso.deError(error);
          }
        },
      },
      entradaCorreo,
      entradaNombre,
      h("button", { type: "submit", clase: "boton boton-fantasma" }, "Convocar"),
    );

    reemplazar(
      vista,
      h("button", { type: "button", clase: "boton boton-fantasma boton-chico", texto: "← Volver", onclick: volverALista }),
      h(
        "section",
        { clase: "tarjeta elevada aparece espaciado" },
        h(
          "div",
          { clase: "tarjeta-fila" },
          h("h2", { clase: "titulo-tarjeta" }, nombreCaso(sesion.caso_id)),
          chip(ESTADOS_SESION[sesion.estado] || sesion.estado, tipoChipSesion(sesion.estado)),
        ),
        h(
          "ul",
          { clase: "meta meta-vertical" },
          h("li", {}, `🗓 Inicio: ${Fechas.formatear(sesion.inicio_programado)}`),
          h("li", {}, `🏁 Fin: ${Fechas.formatear(sesion.fin_programado)}`),
          h("li", {}, `⏱ Tiempo máximo: ${sesion.tiempo_maximo_min} min`),
          sesion.lugar_fisico && h("li", {}, `📍 ${sesion.lugar_fisico}`),
          sesion.mensaje_personalizado && h("li", {}, `💬 ${sesion.mensaje_personalizado}`),
        ),
        h("div", { clase: "acciones" }, acciones),
      ),
      h(
        "section",
        { clase: "espaciado" },
        h("h3", { clase: "titulo-seccion" }, `Convocados (${convocatorias.length})`),
        convocatorias.length
          ? h("div", { clase: "lista-convocados" }, convocatorias.map((c) => filaConvocado(sesion, c)))
          : vacio("Aún no hay estudiantes convocados."),
        h("div", { clase: "tarjeta espaciado" }, h("h4", { clase: "titulo-tarjeta" }, "Convocar a otro estudiante"), formularioConvocar),
      ),
    );
  }

  function filaConvocado(sesion, convocatoria) {
    const datos = datosEstudiante(convocatoria.estudiante_id);
    const activa = !convocatoria.revocada_en;
    return h(
      "article",
      { clase: "tarjeta fila-convocado" },
      h(
        "div",
        { clase: "fila-convocado-info" },
        h("strong", {}, datos ? datos.nombre : `Estudiante …${convocatoria.estudiante_id.slice(-6)}`),
        datos && h("small", { clase: "texto-suave" }, datos.correo),
        chip(
          !activa ? "Retirado" : convocatoria.codigo_vigente ? "Código vigente" : "Código vencido",
          !activa ? "neutro" : convocatoria.codigo_vigente ? "ok" : "aviso",
        ),
      ),
      activa &&
        h(
          "div",
          { clase: "fila-convocado-acciones" },
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "🔑 Ver código",
            onclick: () => mostrarCodigo(sesion, convocatoria, datos),
          }),
          h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "Quitar",
            onclick: () => retirar(sesion, convocatoria, datos),
          }),
        ),
    );
  }

  async function mostrarCodigo(sesion, convocatoria, datos) {
    let codigo;
    try {
      ({ codigo } = await Api.get(`/sessions/${sesion.id}/convocatorias/${convocatoria.id}/codigo`));
    } catch (error) {
      Aviso.deError(error);
      return;
    }
    const caja = h("output", { clase: "codigo-grande" }, codigo);
    const contenido = h(
      "div",
      { clase: "centrado" },
      h("p", { clase: "texto-suave" }, datos ? `Código de ${datos.nombre}` : "Código de la convocatoria"),
      caja,
      h(
        "div",
        { clase: "acciones" },
        h("button", {
          type: "button",
          clase: "boton boton-principal",
          texto: "Copiar",
          onclick: async () => {
            try {
              await navigator.clipboard.writeText(caja.textContent);
              Aviso.exito("Código copiado.");
            } catch (_) {
              const rango = document.createRange();
              rango.selectNodeContents(caja);
              const seleccion = window.getSelection();
              seleccion.removeAllRanges();
              seleccion.addRange(rango);
              Aviso.info("Código seleccionado: cópialo manualmente.");
            }
          },
        }),
        h("button", {
          type: "button",
          clase: "boton boton-fantasma",
          texto: "Regenerar",
          onclick: async () => {
            const confirmado = await Modal.confirmar({
              titulo: "¿Regenerar el código?",
              mensaje: "El código anterior dejará de funcionar.",
              textoConfirmar: "Regenerar",
              peligro: true,
            });
            if (!confirmado) return;
            try {
              const nuevo = await Api.post(
                `/sessions/${sesion.id}/convocatorias/${convocatoria.id}/codigo/regenerar`,
              );
              caja.textContent = nuevo.codigo;
              Aviso.exito("Código regenerado.");
            } catch (error) {
              Aviso.deError(error);
            }
          },
        }),
      ),
    );
    Modal.hoja("Código de acceso", contenido);
  }

  async function retirar(sesion, convocatoria, datos) {
    const confirmado = await Modal.confirmar({
      titulo: "¿Quitar de la sesión?",
      mensaje: `${datos ? datos.nombre : "Este estudiante"} ya no podrá entrar con su código.`,
      textoConfirmar: "Quitar",
      peligro: true,
    });
    if (!confirmado) return;
    try {
      await Api.eliminar(`/sessions/${sesion.id}/convocatorias/${convocatoria.id}`);
      Aviso.exito("Estudiante retirado.");
      await pintarDetalle(sesion.id);
    } catch (error) {
      Aviso.deError(error);
    }
  }

  async function cambiarEstado(sesion, accion, textos) {
    if (!(await Modal.confirmar(textos))) return;
    try {
      await Api.post(`/sessions/${sesion.id}/${accion}`);
      Aviso.exito(accion === "start" ? "Sesión iniciada." : "Sesión finalizada.");
      await pintarDetalle(sesion.id);
    } catch (error) {
      Aviso.deError(error);
    }
  }

  /* ---------- navegación del panel ---------- */

  function activarSeccion(nombre) {
    document.querySelectorAll(".pestanas-panel .pestana").forEach((pestana) => {
      const activa = pestana.dataset.seccion === nombre;
      pestana.classList.toggle("activa", activa);
      pestana.setAttribute("aria-selected", String(activa));
    });
    $("#seccion-casos").classList.toggle("oculto", nombre !== "casos");
    $("#seccion-sesiones").classList.toggle("oculto", nombre !== "sesiones");
  }

  document.querySelectorAll(".pestanas-panel .pestana").forEach((pestana) =>
    pestana.addEventListener("click", () => {
      activarSeccion(pestana.dataset.seccion);
      if (pestana.dataset.seccion === "sesiones") cargarSesiones();
    }),
  );
  $("#boton-agendar").addEventListener("click", () => abrirFormularioAgendar());
  $("#boton-salir").addEventListener("click", () => Api.cerrarSesion());

  const usuario = Api.usuario();
  $("#nombre-usuario").textContent = (usuario && usuario.nombre) || "";
  Campana.montar($("#campana"));
  cargarCasos();
})();
