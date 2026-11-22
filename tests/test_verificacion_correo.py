"""Verificación de correo del estudiante (Fase 9)."""

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.exceptions import ErrorDominio, NoAutenticado
from app.core.security import descifrar, hash_contrasena, hash_token
from app.modules.auth.models import Usuario, VerificacionCorreo
from app.modules.auth.service import ServicioUsuarios
from app.modules.cases.models import Caso
from app.modules.notifications.adapters import FakeAdapter
from app.modules.notifications.dependencies import construir_despachador
from app.modules.notifications.models import EventoOutbox
from app.modules.notifications.procesador import ProcesadorOutbox
from app.modules.sessions.models import EspacioAcademico, Sesion
from app.modules.sessions.schemas import ConvocadoEntrada
from app.modules.sessions.service import ServicioSesiones
from app.modules.sessions.validacion import validador_convocatoria_por_defecto

TIPOS_EVENTO = ("VERIFICACION_CORREO_SOLICITADA", "CONVOCATORIA_CREADA")


# --- Unitarias: sin base de datos -------------------------------------------------------------


class DbFalsa:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def flush(self) -> None:
        pass


class RepositorioFalso:
    def __init__(self, verificacion=None, usuario=None) -> None:
        self.verificacion = verificacion
        self.usuario = usuario

    def verificacion_por_hash(self, token_hash):
        v = self.verificacion
        return v if v is not None and v.token_hash == token_hash else None

    def verificacion_por_id(self, _id):
        return self.verificacion

    def por_id(self, _id):
        return self.usuario


def _servicio(verificacion=None, usuario=None):
    servicio = ServicioUsuarios(DbFalsa())
    servicio.repositorio = RepositorioFalso(verificacion, usuario)
    return servicio


def _usuario(verificado=False) -> Usuario:
    return Usuario(
        id=str(uuid.uuid4()),
        nombre="Ana",
        correo="ana@prueba.edu",
        rol="ESTUDIANTE",
        activo=True,
        correo_verificado=verificado,
        creado_en=ahora(),
        actualizado_en=ahora(),
    )


def _verificacion(token: str | None, expira_en, usada_en=None) -> VerificacionCorreo:
    return VerificacionCorreo(
        id=str(uuid.uuid4()),
        usuario_id="u",
        token_hash=hash_token(token) if token else None,
        expira_en=expira_en,
        usada_en=usada_en,
        creada_en=ahora(),
    )


def test_el_token_en_claro_nunca_se_guarda_solo_su_hash() -> None:
    verificacion = _verificacion(None, ahora() + timedelta(hours=1))
    servicio = _servicio(verificacion, _usuario())

    usuario, token = servicio.preparar_token_verificacion(verificacion.id)

    assert verificacion.token_hash == hash_token(token)
    assert len(verificacion.token_hash) == 64
    valores_guardados = [str(valor) for valor in vars(verificacion).values()]
    assert all(token not in valor for valor in valores_guardados)
    assert usuario.correo == "ana@prueba.edu"


def test_no_se_prepara_token_si_el_correo_ya_esta_verificado() -> None:
    verificacion = _verificacion(None, ahora() + timedelta(hours=1))
    assert (
        _servicio(verificacion, _usuario(verificado=True)).preparar_token_verificacion(
            verificacion.id
        )
        is None
    )


def test_token_vencido_se_rechaza() -> None:
    verificacion = _verificacion("tok-vencido", ahora() - timedelta(minutes=1))
    with pytest.raises(ErrorDominio) as error:
        _servicio(verificacion, _usuario()).confirmar_verificacion("tok-vencido")
    assert error.value.codigo == "TOKEN_INVALIDO"


def test_token_usado_se_rechaza() -> None:
    verificacion = _verificacion("tok-usado", ahora() + timedelta(hours=1), usada_en=ahora())
    with pytest.raises(ErrorDominio):
        _servicio(verificacion, _usuario()).confirmar_verificacion("tok-usado")


def test_token_desconocido_se_rechaza_con_el_mismo_error() -> None:
    with pytest.raises(ErrorDominio) as error:
        _servicio(None, _usuario()).confirmar_verificacion("no-existe")
    assert error.value.codigo == "TOKEN_INVALIDO"


def test_token_vigente_marca_el_correo_como_verificado() -> None:
    usuario = _usuario()
    verificacion = _verificacion("tok-ok", ahora() + timedelta(hours=1))
    servicio = _servicio(verificacion, usuario)

    servicio.confirmar_verificacion("tok-ok")

    assert usuario.correo_verificado is True
    assert usuario.verificado_en is not None
    assert verificacion.usada_en is not None
    assert servicio.db.commits == 1


# --- Integración: MySQL real, FakeAdapter, sin SMTP ----------------------------------------


def _dominio() -> str:
    return obtener_configuracion().dominio_institucional.split(",")[0].strip()


def _correo() -> str:
    return f"{uuid.uuid4().hex[:12]}@{_dominio()}"


def _procesar(db, adapter: FakeAdapter) -> None:
    ProcesadorOutbox(db, construir_despachador(adapter)).procesar_lote(100)


def _eventos_de(db, usuario_id: str) -> list[EventoOutbox]:
    eventos = db.scalars(
        select(EventoOutbox).where(EventoOutbox.tipo == "VERIFICACION_CORREO_SOLICITADA")
    ).all()
    return [e for e in eventos if e.payload.get("usuario_id") == usuario_id]


def _token_del_correo(adapter: FakeAdapter, indice: int = -1) -> str:
    coincidencia = re.search(r"verificar-correo\?token=([\w-]+)", adapter.envios[indice]["texto"])
    assert coincidencia, "el correo no trae el enlace de verificación"
    return coincidencia.group(1)


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def limpieza(db):
    ids_usuarios: list[str] = []
    yield ids_usuarios
    db.rollback()
    db.execute(delete(EventoOutbox).where(EventoOutbox.tipo.in_(TIPOS_EVENTO)))
    db.execute(delete(Sesion).where(Sesion.docente_id.in_(ids_usuarios)))
    db.execute(delete(EspacioAcademico).where(EspacioAcademico.docente_id.in_(ids_usuarios)))
    db.execute(delete(Caso).where(Caso.docente_creador_id.in_(ids_usuarios)))
    db.execute(delete(Usuario).where(Usuario.id.in_(ids_usuarios)))
    db.commit()


def _crear_usuario(db, limpieza, rol="ESTUDIANTE", verificado=False, contrasena=None) -> Usuario:
    usuario = Usuario(
        nombre="Usuario de prueba",
        correo=_correo(),
        hash_contrasena=hash_contrasena(contrasena) if contrasena else None,
        rol=rol,
        activo=True,
        correo_verificado=verificado,
        creado_en=ahora(),
        actualizado_en=ahora(),
    )
    db.add(usuario)
    db.commit()
    limpieza.append(usuario.id)
    return usuario


def test_alta_de_estudiante_envia_correo_y_se_verifica(cliente, db, adapter, limpieza) -> None:
    admin = _crear_usuario(
        db, limpieza, rol="ADMINISTRADOR", verificado=True, contrasena="Admin12345"
    )
    acceso = cliente.post(
        "/api/v1/auth/login", json={"correo": admin.correo, "contrasena": "Admin12345"}
    ).json()["token_acceso"]
    correo = _correo()

    alta = cliente.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {acceso}"},
        json={"nombre": "Estudiante Nuevo", "correo": correo, "rol": "ESTUDIANTE"},
    )
    assert alta.status_code == 201
    assert alta.json()["correo_verificado"] is False
    estudiante_id = alta.json()["id"]
    limpieza.append(estudiante_id)

    # El evento queda en el outbox, sin el token y sin datos personales.
    eventos = _eventos_de(db, estudiante_id)
    assert len(eventos) == 1
    assert eventos[0].estado == "PENDIENTE"
    assert set(eventos[0].payload) == {"usuario_id", "verificacion_id"}

    _procesar(db, adapter)
    assert [envio["destinatario"] for envio in adapter.envios] == [correo]
    token = _token_del_correo(adapter)

    db.rollback()  # cierra el snapshot REPEATABLE READ para ver lo que escribió la API
    verificacion = db.get(VerificacionCorreo, eventos[0].payload["verificacion_id"])
    assert verificacion.token_hash == hash_token(token)
    assert verificacion.token_hash != token

    respuesta = cliente.post("/api/v1/auth/verificar-correo", json={"token": token})
    assert respuesta.status_code == 200
    db.rollback()  # cierra el snapshot REPEATABLE READ para ver lo que escribió la API
    estudiante = db.get(Usuario, estudiante_id)
    assert estudiante.correo_verificado is True
    assert estudiante.verificado_en is not None

    reuso = cliente.post("/api/v1/auth/verificar-correo", json={"token": token})
    assert reuso.status_code == 400
    assert reuso.json()["error"]["codigo"] == "TOKEN_INVALIDO"
    assert cliente.post("/api/v1/auth/verificar-correo", json={"token": "x"}).status_code == 400


def test_docente_creado_por_el_admin_no_necesita_verificar(cliente, db, limpieza) -> None:
    admin = _crear_usuario(
        db, limpieza, rol="ADMINISTRADOR", verificado=True, contrasena="Admin12345"
    )
    acceso = cliente.post(
        "/api/v1/auth/login", json={"correo": admin.correo, "contrasena": "Admin12345"}
    ).json()["token_acceso"]

    alta = cliente.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {acceso}"},
        json={
            "nombre": "Docente Nuevo",
            "correo": _correo(),
            "rol": "DOCENTE",
            "contrasena": "Docente12345",
        },
    )
    assert alta.status_code == 201
    limpieza.append(alta.json()["id"])
    assert alta.json()["correo_verificado"] is True
    assert _eventos_de(db, alta.json()["id"]) == []


def test_reenviar_responde_igual_exista_o_no_el_correo(cliente, db, adapter, limpieza) -> None:
    estudiante = _crear_usuario(db, limpieza)

    existente = cliente.post(
        "/api/v1/auth/reenviar-verificacion", json={"correo": estudiante.correo}
    )
    inexistente = cliente.post(
        "/api/v1/auth/reenviar-verificacion", json={"correo": f"nadie-{_correo()}"}
    )

    assert existente.status_code == inexistente.status_code == 200
    assert existente.json() == inexistente.json()
    _procesar(db, adapter)
    assert [envio["destinatario"] for envio in adapter.envios] == [estudiante.correo]


def test_reenvio_limitado_a_uno_cada_cinco_minutos(cliente, db, adapter, limpieza) -> None:
    estudiante = _crear_usuario(db, limpieza)
    for _ in range(3):
        cliente.post("/api/v1/auth/reenviar-verificacion", json={"correo": estudiante.correo})

    assert len(_eventos_de(db, estudiante.id)) == 1
    _procesar(db, adapter)
    assert len(adapter.envios) == 1


def test_estudiante_ya_verificado_no_recibe_otro_enlace(cliente, db, adapter, limpieza) -> None:
    estudiante = _crear_usuario(db, limpieza, verificado=True)
    cliente.post("/api/v1/auth/reenviar-verificacion", json={"correo": estudiante.correo})

    assert _eventos_de(db, estudiante.id) == []
    _procesar(db, adapter)
    assert adapter.envios == []


@pytest.fixture
def sesion_en_curso(db, limpieza):
    docente = _crear_usuario(db, limpieza, rol="DOCENTE", verificado=True, contrasena="Docente123")
    momento = ahora()
    caso = Caso(
        docente_creador_id=docente.id,
        nombre="Caso de prueba",
        desarrollo_situacional="x",
        contexto_historia="x",
        tiempo_estimado_min=30,
        estado="PUBLICADO",
        version=1,
        creado_en=momento,
        actualizado_en=momento,
    )
    espacio = EspacioAcademico(nombre="Espacio", docente_id=docente.id, creado_en=momento)
    db.add_all([caso, espacio])
    db.flush()
    sesion = Sesion(
        caso_id=caso.id,
        docente_id=docente.id,
        espacio_academico_id=espacio.id,
        inicio_programado=momento,
        fin_programado=momento + timedelta(hours=2),
        tiempo_maximo_min=30,
        estado="EN_CURSO",
        iniciada_en=momento,
        creada_en=momento,
    )
    db.add(sesion)
    db.commit()
    return docente, sesion


def _convocar(db, docente, sesion, correo: str):
    servicio = ServicioSesiones(db)
    convocatoria = servicio.agregar_convocado(
        sesion,
        ConvocadoEntrada(correo=correo, nombre="Estudiante"),
        {"rol": "DOCENTE", "sub": docente.id},
    )
    return convocatoria, db.scalar(select(Usuario).where(Usuario.correo == correo))


def test_convocar_estudiante_nuevo_solicita_verificacion(db, limpieza, sesion_en_curso) -> None:
    docente, sesion = sesion_en_curso
    _, estudiante = _convocar(db, docente, sesion, _correo())
    limpieza.append(estudiante.id)

    assert len(_eventos_de(db, estudiante.id)) == 1


def test_convocar_estudiante_ya_verificado_no_reenvia(db, limpieza, sesion_en_curso) -> None:
    docente, sesion = sesion_en_curso
    verificado = _crear_usuario(db, limpieza, verificado=True)

    _convocar(db, docente, sesion, verificado.correo)

    assert _eventos_de(db, verificado.id) == []


def test_exigir_correo_verificado_bloquea_el_ingreso(db, limpieza, sesion_en_curso, monkeypatch):
    docente, sesion = sesion_en_curso
    correo = _correo()
    convocatoria, estudiante = _convocar(db, docente, sesion, correo)
    limpieza.append(estudiante.id)
    codigo = descifrar(convocatoria.codigo_cifrado)
    validar = validador_convocatoria_por_defecto(db)

    # Por defecto la verificación es informativa: entra igual.
    assert validar(correo, codigo)["valido"] is True

    monkeypatch.setattr(obtener_configuracion(), "exigir_correo_verificado", True)
    with pytest.raises(NoAutenticado, match="verificar tu correo"):
        validar(correo, codigo)
    db.rollback()

    # Un código incorrecto sigue dando el mensaje genérico: no se revela nada.
    with pytest.raises(NoAutenticado) as error:
        validar(correo, "CODIGOMALO")
    assert "verificar" not in str(error.value)
    db.rollback()

    estudiante.correo_verificado = True
    db.commit()
    assert validar(correo, codigo)["valido"] is True


def test_login_de_estudiante_muestra_el_aviso_de_verificacion(
    cliente, db, limpieza, sesion_en_curso, monkeypatch
) -> None:
    docente, sesion = sesion_en_curso
    correo = _correo()
    convocatoria, estudiante = _convocar(db, docente, sesion, correo)
    limpieza.append(estudiante.id)
    monkeypatch.setattr(obtener_configuracion(), "exigir_correo_verificado", True)

    respuesta = cliente.post(
        "/api/v1/auth/student-login",
        json={"correo": correo, "codigo": descifrar(convocatoria.codigo_cifrado)},
    )

    assert respuesta.status_code == 401
    assert "verificar tu correo" in respuesta.json()["error"]["mensaje"]


def test_reprocesar_el_evento_no_envia_dos_correos(cliente, db, adapter, limpieza) -> None:
    estudiante = _crear_usuario(db, limpieza)
    cliente.post("/api/v1/auth/reenviar-verificacion", json={"correo": estudiante.correo})
    _procesar(db, adapter)

    evento = _eventos_de(db, estudiante.id)[0]
    evento.estado = "PENDIENTE"
    db.commit()
    _procesar(db, adapter)

    assert len(adapter.envios) == 1
    cantidad = db.scalar(
        select(func.count())
        .select_from(VerificacionCorreo)
        .where(VerificacionCorreo.usuario_id == estudiante.id)
    )
    assert cantidad == 1
