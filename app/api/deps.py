from fastapi import Depends
from app.db.session import get_db_session
from app.services.container import ServiceContainer, build_container

container = build_container()


def get_container() -> ServiceContainer:
    return container


get_session = get_db_session


ContainerDep = Depends(get_container)
SessionDep = Depends(get_session)
