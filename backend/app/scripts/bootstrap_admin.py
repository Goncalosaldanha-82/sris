import argparse, re
from app.core.db import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.models import User, Organization, Membership

def main():
    p=argparse.ArgumentParser();p.add_argument("--email",required=True);p.add_argument("--password",required=True);p.add_argument("--organization",required=True);a=p.parse_args()
    Base.metadata.create_all(engine);db=SessionLocal()
    try:
        user=db.query(User).filter_by(email=a.email.lower()).first() or User(email=a.email.lower(),full_name="Platform Administrator",password_hash=hash_password(a.password),is_platform_admin=True)
        db.add(user);db.flush()
        slug=re.sub(r"[^a-z0-9]+","-",a.organization.lower()).strip("-")
        org=db.query(Organization).filter_by(slug=slug).first() or Organization(name=a.organization,slug=slug)
        db.add(org);db.flush()
        if not db.query(Membership).filter_by(organization_id=org.id,user_id=user.id).first(): db.add(Membership(organization_id=org.id,user_id=user.id,role="owner"))
        db.commit();print(f"Created {a.email} / {org.id}")
    finally:db.close()
if __name__=="__main__":main()
