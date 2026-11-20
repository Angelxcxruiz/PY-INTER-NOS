from app.modules.notifications.adapters import FakeAdapter
from app.modules.notifications.plantillas import renderizar
from app.modules.notifications.procesador import calcular_backoff_minutos
from app.modules.sessions.events import publicar


def test_backoff_exponencial() -> None:
    assert [calcular_backoff_minutos(intentos) for intentos in range(1, 5)] == [1, 2, 4, 8]


def test_fake_adapter_acumula_sin_red() -> None:
    adapter = FakeAdapter()

    adapter.enviar(
        "estudiante@unal.edu.co",
        "Prueba",
        "<p>HTML</p>",
        "Texto",
    )

    assert len(adapter.envios) == 1
    assert adapter.envios[0]["destinatario"] == "estudiante@unal.edu.co"


def test_plantillas_renderizan_sin_datos_opcionales() -> None:
    html, texto = renderizar(
        "invitacion.html",
        "invitacion.txt",
        {
            "estudiante_nombre": "Ana",
            "caso_nombre": "Caso ejemplo",
            "mensaje_personalizado": None,
            "inicio": "20/11/2026 12:00",
            "fin": "20/11/2026 14:00",
            "lugar_fisico": None,
            "tiempo_maximo_min": 30,
            "codigo": "ABC23456",
            "frontend_url": "http://localhost:3000",
        },
    )

    assert "Ana" in html
    assert "Por definir" in html
    assert "ABC23456" in texto


def test_payload_sensible_es_rechazado() -> None:
    try:
        publicar(
            object(),
            "CONVOCATORIA_CREADA",
            "convocatoria",
            "convocatoria-1",
            {"convocatoria_id": "convocatoria-1", "codigo": "ABC23456"},
        )
    except ValueError as exc:
        assert "sensibles" in str(exc)
    else:
        raise AssertionError("Debe rechazar payload sensible")
