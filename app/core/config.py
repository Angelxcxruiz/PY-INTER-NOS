from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="mysql+pymysql://inter_nos:inter_nos@127.0.0.1:3306/inter_nos?charset=utf8mb4",
    )
    test_database_url: str | None = None
    jwt_secreto: str = Field(default="cambiar-en-entorno", validation_alias="JWT_SECRET")
    jwt_expira_min: int = Field(default=60, validation_alias="JWT_EXPIRA_MIN")
    fernet_key: str = Field(
        default="7qpD1AuRHDuYeo1DewnaXPtepYHy5zJc1oBk5ve_pAQ=",
        validation_alias="FERNET_KEY",
    )
    dominio_institucional: str = Field(
        default="unal.edu.co",
        validation_alias="DOMINIO_INSTITUCIONAL",
    )
    frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")
    email_backend: str = Field(default="consola", validation_alias="EMAIL_BACKEND")
    smtp_host: str = Field(default="127.0.0.1", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")
    escala_nota_max: str = Field(default="5.00", validation_alias="ESCALA_NOTA_MAX")
    nota_aprobatoria: str = Field(default="3.00", validation_alias="NOTA_APROBATORIA")
    fraccion_ingreso_tardio: str = Field(
        default="0.5",
        validation_alias="FRACCION_INGRESO_TARDIO",
    )
    csv_separador: str = Field(default=";", validation_alias="CSV_SEPARADOR")
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origins_lista(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()
