from sqlalchemy import Column, Boolean
from app.database import Base

class IsActiveMixin(Base):
    __abstract__ = True

    is_active = Column(Boolean, default=True, nullable=False)

    def deactivate(self):
        self.is_active = False

    def activate(self):
        self.is_active = True