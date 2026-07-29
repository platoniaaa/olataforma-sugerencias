"""Fixtures de pytest: base de datos SQLite en memoria + cliente de prueba con datos."""
import json
import os

# La suite corre siempre contra SQLite en memoria, pero `src.db` crea su engine al
# importarse y `src.config` lee el .env del repo. Sin esto, en un PC con el .env de
# produccion los tests se quedan colgados intentando abrir una conexion al Postgres
# remoto (o fallan si no esta instalado su driver). Se setea ANTES de importar src
# porque la variable de entorno le gana al .env en pydantic-settings; con setdefault,
# quien quiera apuntar a otra base igual puede exportarla.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.db import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.models import (  # noqa: E402
    DimProducto,
    DimSucursal,
    Sugerido,
    Usuario,
    VentaHistorica,
)
from src.services.auth import hash_password, requiere_auth  # noqa: E402


@pytest.fixture()
def db_session():
    # StaticPool + una sola conexion compartida: necesario para que la DB en memoria
    # sea visible desde el thread del endpoint (FastAPI corre en un threadpool).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    _seed(session)
    try:
        yield session
    finally:
        session.close()


def _seed(session):
    # El usuario de los tests es admin: los endpoints /api/admin/* verifican
    # es_admin en la BD (requiere_admin), no solo el token.
    session.add(Usuario(
        email="test@curifor.com", password_hash=hash_password("123456"),
        nombre="Test", es_admin=True,
    ))
    session.add(Usuario(
        email="noadmin@curifor.com", password_hash=hash_password("123456"),
        nombre="No Admin", es_admin=False,
    ))
    session.add(DimSucursal(sucursal_id="LINDEROS", tenant_id="curifor", nombre="Linderos"))
    session.add(DimProducto(
        producto="20 BXO5W30AA", tenant_id="curifor", descripcion="ACEITE 5W30 LITRO FORD",
        filtro1_final="FORD", costo_unitario=5000, proveedor="Ford Motor Company Chile",
    ))
    session.add(Sugerido(
        tenant_id="curifor", producto="20 BXO5W30AA", descripcion="ACEITE 5W30 LITRO FORD",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", clasificacion_abc="A",
        proveedor="Ford Motor Company Chile", filtro1_final="FORD", tipo_origen="Importado",
        pedir="Si", costo_unitario=5000, total_sugerido_suc=10, total_valor_sugerido_clp=50000,
        sugerido_traslado=4, sugerido_compra_neto=6, pedir_flag="Si",
    ))
    for mes, cant in [("202503", 12), ("202504", 8), ("202505", 15)]:
        session.add(VentaHistorica(
            tenant_id="curifor", producto="20 BXO5W30AA", sucursal="LINDEROS",
            periodo=mes, cantidad=cant,
        ))
    session.commit()


@pytest.fixture()
def client(db_session):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    # Bypass de autenticacion en los tests (los endpoints de datos estan protegidos).
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
