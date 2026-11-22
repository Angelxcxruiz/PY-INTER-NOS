"""Flujos de correo de autenticación contra MySQL real, con FakeAdapter (sin SMTP)."""

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, update

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.security import hash_contrasena
from app.modules.auth.models import TokenCorreo, Usuario
from app.modules.notifications.adapters import FakeAdapter
from app.modules.notifications.dependencies import construir_despachador
from app.modules.notifications.models import EventoOutbox
from app.modules.notifications.procesador import ProcesadorOutbox
from app.modules.sessions.events import publicar

TIPOS_TOKEN = ("RESTABLECIMIENTO_CONTRASENA_SOLICITADO",)
CLAVE = "ClaveVieja123"


def procesar_outbox(db, adapter: FakeAdapter) -> None:
    ProcesadorOutbox(db, construir_despachador(adapter)).procesar_lote(100)


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def adapter():
    return FakeAdapter()


def _crear_usuario(db, rol="DOCENTE", con_contrasena=True) -> Usuario:
    ahora_ = ahora()
    usuario = Usuario(
        nombre="Docente de prueba",
        correo=f"{uuid.uuid4().hex[:12]}@prueba.edu",
        hash_contrasena=hash_contrasena(CLAVE) if con_contrasena else None,
        rol=rol,
        activo=True,
        creado_en=ahora_,
        actualizado_en=ahora_,
    )
    db.add(usuario)
    db.commit()
    return usuario


@pytest.fixture
def docente(db):
    usuario = _crear_usuario(db)
    yield usuario
    db.rollback()
    db.execute(delete(EventoOutbox).where(EventoOutbox.tipo.in_(TIPOS_TOKEN)))
    db.execute(delete(Usuario).where(Usuario.id == usuario.id))
    db.commit()


def _token_del_correo(adapter: FakeAdapter) -> str:
    coincidencia = re.search(r"token=([\w-]+)", adapter.envios[-1]["texto"])
    assert coincidencia, "el correo no trae el enlace con token"
    return coincidencia.group(1)


def _login(cliente, correo: str, contrasena: str):
    return cliente.post("/api/v1/auth/login", json={"correo": correo, "contrasena": contrasena})


def test_restablecer_contrasena_de_punta_a_punta(cliente, db, docente, adapter) -> None:
    respuesta = cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})
    assert respuesta.status_code == 202

    procesar_outbox(db, adapter)
    assert [envio["destinatario"] for envio in adapter.envios] == [docente.correo]
    token = _token_del_correo(adapter)

    cambio = cliente.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "nueva_contrasena": "ClaveNueva456"},
    )
    assert cambio.status_code == 200
    assert _login(cliente, docente.correo, "ClaveNueva456").status_code == 200
    assert _login(cliente, docente.correo, CLAVE).status_code == 401

    reuso = cliente.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "nueva_contrasena": "OtraClave789"},
    )
    assert reuso.status_code == 422
    assert reuso.json()["error"]["codigo"] == "TOKEN_INVALIDO"


def test_correo_inexistente_responde_igual_y_no_envia(cliente, db, docente, adapter) -> None:
    existente = cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})
    inexistente = cliente.post("/api/v1/auth/forgot-password", json={"correo": "nadie@prueba.edu"})

    assert inexistente.status_code == existente.status_code == 202
    assert inexistente.json() == existente.json()

    procesar_outbox(db, adapter)
    assert [envio["destinatario"] for envio in adapter.envios] == [docente.correo]


def test_estudiante_sin_contrasena_no_recibe_enlace(cliente, db, adapter) -> None:
    estudiante = _crear_usuario(db, rol="ESTUDIANTE", con_contrasena=False)
    try:
        respuesta = cliente.post("/api/v1/auth/forgot-password", json={"correo": estudiante.correo})
        assert respuesta.status_code == 202
        procesar_outbox(db, adapter)
        assert adapter.envios == []
    finally:
        db.execute(delete(Usuario).where(Usuario.id == estudiante.id))
        db.commit()


def test_token_expirado_es_rechazado(cliente, db, docente, adapter) -> None:
    cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})
    procesar_outbox(db, adapter)
    token = _token_del_correo(adapter)

    db.execute(
        update(TokenCorreo)
        .where(TokenCorreo.usuario_id == docente.id)
        .values(expira_en=ahora() - timedelta(minutes=1))
    )
    db.commit()

    respuesta = cliente.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "nueva_contrasena": "ClaveNueva456"},
    )
    assert respuesta.status_code == 422
    assert _login(cliente, docente.correo, CLAVE).status_code == 200


def test_solicitudes_seguidas_no_inundan_de_correos(cliente, db, docente, adapter) -> None:
    for _ in range(3):
        cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})

    cantidad = db.scalar(
        select(func.count()).select_from(TokenCorreo).where(TokenCorreo.usuario_id == docente.id)
    )
    assert cantidad == 1
    procesar_outbox(db, adapter)
    assert len(adapter.envios) == 1


def test_un_enlace_nuevo_invalida_el_anterior(cliente, db, docente, adapter, monkeypatch) -> None:
    monkeypatch.setattr(obtener_configuracion(), "token_cooldown_seg", 0)
    cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})
    cliente.post("/api/v1/auth/forgot-password", json={"correo": docente.correo})

    procesar_outbox(db, adapter)

    # El primer enlace ya estaba invalidado cuando el worker llegó: solo sale el vigente.
    assert len(adapter.envios) == 1
    cambio = cliente.post(
        "/api/v1/auth/reset-password",
        json={"token": _token_del_correo(adapter), "nueva_contrasena": "ClaveNueva456"},
    )
    assert cambio.status_code == 200


def test_evento_de_convocatoria_cabe_en_la_clave_de_idempotencia(db) -> None:
    """Regresión: la clave en claro superaba los 128 caracteres y MySQL rechazaba el INSERT."""
    convocatoria_id, sesion_id = str(uuid.uuid4()), str(uuid.uuid4())
    publicar(
        db,
        "CONVOCATORIA_CREADA",
        "convocatoria",
        convocatoria_id,
        {"convocatoria_id": convocatoria_id, "sesion_id": sesion_id},
    )
    db.rollback()


def test_si_la_transaccion_de_negocio_falla_el_evento_desaparece(db) -> None:
    agregado_id = str(uuid.uuid4())
    publicar(db, "SESION_INICIADA", "sesion", agregado_id, {"sesion_id": agregado_id})
    visible_en_la_transaccion = db.scalar(
        select(func.count())
        .select_from(EventoOutbox)
        .where(EventoOutbox.agregado_id == agregado_id)
    )
    assert visible_en_la_transaccion == 1

    db.rollback()

    restantes = db.scalar(
        select(func.count())
        .select_from(EventoOutbox)
        .where(EventoOutbox.agregado_id == agregado_id)
    )
    assert restantes == 0
