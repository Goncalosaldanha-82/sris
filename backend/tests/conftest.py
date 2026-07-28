import os
os.environ["DATABASE_URL"]="sqlite:///./test_sris.db"
os.environ["SECRET_KEY"]="test-secret-"*10
os.environ["ENCRYPTION_MASTER_KEY"]=""
import pytest
from fastapi.testclient import TestClient
from app.core.db import Base, engine, SessionLocal
from app.main import app
from app.core.security import hash_password
from app.models.models import User, Organization, Membership
@pytest.fixture(autouse=True)
def reset():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    db=SessionLocal();u=User(email="admin@example.com",full_name="Admin",password_hash=hash_password("Password123!"));o1=Organization(name="Org One",slug="org-one");o2=Organization(name="Org Two",slug="org-two");db.add_all([u,o1,o2]);db.flush();db.add(Membership(organization_id=o1.id,user_id=u.id,role="owner"));db.commit();yield {"user":u,"org1":o1,"org2":o2};db.close()
@pytest.fixture
def client(): return TestClient(app)
@pytest.fixture
def auth(client,reset):
    t=client.post('/api/auth/login',json={"email":"admin@example.com","password":"Password123!"}).json();return {"Authorization":"Bearer "+t["access_token"],"X-Organization-ID":reset["org1"].id}
