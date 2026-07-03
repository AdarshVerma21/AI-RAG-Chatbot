# models/__init__.py
# Import all models here so that Base.metadata knows about them
# before create_all() is called.
from models.document import Document  # noqa: F401
from models.user import User  # noqa: F401
