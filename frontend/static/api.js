"use strict";

/*
 * Cliente de la API de Inter Nos.
 * - Guarda el JWT en sessionStorage (se borra al cerrar la pestaña).
 * - Traduce los errores {"error": {codigo, mensaje, detalles}} a ErrorApi.
 * - Ante un 401 limpia la sesión y vuelve al login.
 */

const CLAVES_SESION = {
  token: "inn_token",
  rol: "inn_rol",
  usuario: "inn_usuario",
  aviso: "inn_aviso",
};

const RUTA_LOGIN = "/app/";
const BASE_API = "/api/v1";

class ErrorApi extends Error {
  constructor(estado, codigo, mensaje, detalles = {}) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
    this.codigo = codigo;
    this.detalles = detalles;
  }
}

function decodificarJwt(token) {
  try {
    const carga = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const binario = atob(carga + "=".repeat((4 - (carga.length % 4)) % 4));
    const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch (_) {
    return null;
  }
}

const Api = {
  token() {
    return sessionStorage.getItem(CLAVES_SESION.token);
  },

  rol() {
    return sessionStorage.getItem(CLAVES_SESION.rol);
  },

  usuario() {
    const crudo = sessionStorage.getItem(CLAVES_SESION.usuario);
    return crudo ? JSON.parse(crudo) : null;
  },

  // Datos firmados dentro del JWT (rol, convocatoria_id, sesion_id, caso_id...).
  claims() {
    const token = this.token();
    return token ? decodificarJwt(token) : null;
  },

  guardarSesion(token, usuario) {
    const claims = decodificarJwt(token) || {};
    sessionStorage.setItem(CLAVES_SESION.token, token);
    sessionStorage.setItem(CLAVES_SESION.rol, claims.rol || (usuario && usuario.rol) || "");
    sessionStorage.setItem(CLAVES_SESION.usuario, JSON.stringify(usuario || {}));
  },

  limpiarSesion() {
    Object.values(CLAVES_SESION).forEach((clave) => {
      if (clave !== CLAVES_SESION.aviso) sessionStorage.removeItem(clave);
    });
  },

  cerrarSesion(aviso) {
    this.limpiarSesion();
    if (aviso) sessionStorage.setItem(CLAVES_SESION.aviso, aviso);
    window.location.href = RUTA_LOGIN;
  },

  rutaInicioDelRol(rol) {
    return rol === "ESTUDIANTE" ? "/app/simulador" : "/app/docente";
  },

  /* Protege una pantalla: devuelve los claims o redirige al login. */
  exigirRol(...rolesPermitidos) {
    const claims = this.claims();
    if (!claims) {
      this.cerrarSesion("Inicia sesión para continuar.");
      return null;
    }
    if (!rolesPermitidos.includes(claims.rol)) {
      window.location.href = this.rutaInicioDelRol(claims.rol);
      return null;
    }
    if (claims.exp && claims.exp * 1000 <= Date.now()) {
      this.cerrarSesion("Tu sesión expiró. Vuelve a ingresar.");
      return null;
    }
    return claims;
  },

  async solicitar(metodo, ruta, { cuerpo, consulta, credenciales = false, formulario } = {}) {
    let url = BASE_API + ruta;
    if (consulta) {
      const parametros = new URLSearchParams();
      Object.entries(consulta).forEach(([clave, valor]) => {
        if (valor !== undefined && valor !== null && valor !== "") parametros.set(clave, valor);
      });
      const texto = parametros.toString();
      if (texto) url += "?" + texto;
    }

    const cabeceras = { Accept: "application/json" };
    const token = this.token();
    if (token) cabeceras.Authorization = "Bearer " + token;
    if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";

    let respuesta;
    try {
      respuesta = await fetch(url, {
        method: metodo,
        headers: cabeceras,
        body: formulario !== undefined ? formulario : cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
      });
    } catch (_) {
      throw new ErrorApi(
        0,
        "SIN_CONEXION",
        "No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.",
      );
    }

    let datos = null;
    if (respuesta.status !== 204) {
      try {
        datos = await respuesta.json();
      } catch (_) {
        datos = null;
      }
    }

    if (respuesta.ok) return datos;

    const info = (datos && datos.error) || {};
    const error = new ErrorApi(
      respuesta.status,
      info.codigo || "ERROR",
      info.mensaje || "Ocurrió un error inesperado.",
      info.detalles || {},
    );
    // Un 401 en el login significa credenciales malas, no sesión vencida.
    if (respuesta.status === 401 && !credenciales) {
      this.cerrarSesion("Tu sesión expiró. Vuelve a ingresar.");
    }
    throw error;
  },

  get: (ruta, consulta) => Api.solicitar("GET", ruta, { consulta }),
  post: (ruta, cuerpo, opciones = {}) => Api.solicitar("POST", ruta, { cuerpo, ...opciones }),
  put: (ruta, cuerpo) => Api.solicitar("PUT", ruta, { cuerpo }),
  eliminar: (ruta) => Api.solicitar("DELETE", ruta),

  /* Sube un archivo como multipart/form-data (campo "archivo"). */
  subirArchivo(ruta, archivo) {
    const formulario = new FormData();
    formulario.append("archivo", archivo);
    return Api.solicitar("POST", ruta, { formulario });
  },

  /* Primera línea de un error de validación (422) legible para humanos. */
  mensajeDe(error) {
    if (!(error instanceof ErrorApi)) return "Ocurrió un error inesperado.";
    const errores = error.detalles && error.detalles.errores;
    if (error.codigo === "VALIDACION_FALLIDA" && Array.isArray(errores) && errores.length) {
      const primero = errores[0];
      const campo = Array.isArray(primero.loc) ? primero.loc.slice(1).join(" › ") : "";
      return campo ? `${campo}: ${primero.msg}` : primero.msg;
    }
    return error.message;
  },
};
